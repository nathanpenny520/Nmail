"""账号管理 API：添加（带连接测试）、列表、删除、手动同步、文件夹、服务商预设。"""
from __future__ import annotations

import json
import re
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core import imap_client, oauth, sync as sync_engine
from app.core.providers import MANUAL_NOTE, PRESETS, match_provider, probe_server
from app.db.database import get_conn
from app.security import set_secret

router = APIRouter(prefix="/api", tags=["accounts"])

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

COLOR_PALETTE = [
    "#6366f1", "#0ea5e9", "#10b981", "#f59e0b",
    "#ef4444", "#8b5cf6", "#ec4899", "#14b8a6",
]


class AccountIn(BaseModel):
    email: str
    password: str
    imap_server: str | None = None
    imap_port: int | None = None
    smtp_server: str | None = None
    smtp_port: int | None = None


class AccountPatchIn(BaseModel):
    password: str | None = None
    ai_permission: str | None = None  # readonly | draft_review
    style_prompt: str | None = Field(default=None, max_length=2000)  # None=不改；空串=清除
    use_proxy: bool | None = None  # 该账号 IMAP/SMTP 是否经全局代理地址连接


class ProbeIn(BaseModel):
    email: str


def _resolve_config(payload: AccountIn) -> tuple[imap_client.MailConfig, str | None]:
    """按预设自动补全服务器配置，返回 (MailConfig, 匹配到的预设名)。"""
    email = payload.email.strip()
    if not EMAIL_RE.match(email):
        raise HTTPException(400, "邮箱地址格式不正确")
    preset = match_provider(email)
    imap_server = payload.imap_server or (preset.imap_server if preset else "")
    smtp_server = payload.smtp_server or (preset.smtp_server if preset else "")
    if not imap_server:
        raise HTTPException(400, "无法识别服务商，请手动填写 IMAP 服务器。" + MANUAL_NOTE)
    return (
        imap_client.MailConfig(
            email=email,
            password=payload.password,
            imap_server=imap_server,
            imap_port=payload.imap_port or (preset.imap_port if preset else 993),
            smtp_server=smtp_server,
            smtp_port=payload.smtp_port or (preset.smtp_port if preset else 465),
        ),
        preset.name if preset else None,
    )


def _account_dict(row) -> dict[str, Any]:  # noqa: ANN001
    return {
        "id": row["id"],
        "email": row["email"],
        "provider_name": row["provider_name"],
        "imap_server": row["imap_server"],
        "imap_port": row["imap_port"],
        "smtp_server": row["smtp_server"],
        "smtp_port": row["smtp_port"],
        "color": row["color"],
        "auth_type": row["auth_type"] if "auth_type" in row.keys() else "password",  # noqa: SIM118 — sqlite3.Row 的 in 语义是值不是键
        "oauth_provider": row["oauth_provider"] if "oauth_provider" in row.keys() else "",  # noqa: SIM118 — 同上
        "use_proxy": bool(row["use_proxy"]) if "use_proxy" in row.keys() else False,  # noqa: SIM118 — 同上
        "ai_permission": row["ai_permission"] if "ai_permission" in row.keys() else "draft_review",  # noqa: SIM118 — 同上
        "ai_grants": _safe_grants(row["ai_grants"]) if "ai_grants" in row.keys() else None,  # noqa: SIM118 — 同上
        "is_ai_mailbox": bool(row["is_ai_mailbox"]) if "is_ai_mailbox" in row.keys() else False,  # noqa: SIM118 — 同上
        "style_prompt": row["style_prompt"] if "style_prompt" in row.keys() else None,  # noqa: SIM118 — 同上
        "status": row["status"],
        "status_detail": row["status_detail"],
        "last_sync_at": row["last_sync_at"],
    }


def _safe_grants(raw: str | None) -> dict | None:
    """ai_grants JSON 容错解析（坏值回退 None=按旧枚举映射，不让账号列表 500）。"""
    if not raw:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return None


@router.get("/providers")
def list_providers() -> dict:
    return {
        "providers": [
            {
                "name": p.name,
                "domains": list(p.domains),
                "note": p.note,
                "imap_server": p.imap_server,
                "imap_port": p.imap_port,
                "smtp_server": p.smtp_server,
                "smtp_port": p.smtp_port,
            }
            for p in PRESETS
        ],
        "manual_note": MANUAL_NOTE,
    }


@router.post("/accounts/test")
def test_account(payload: AccountIn) -> dict:
    cfg, preset_name = _resolve_config(payload)
    ok, detail = imap_client.test_connection(cfg)
    return {"ok": ok, "detail": detail, "provider": preset_name}


@router.post("/accounts/probe")
def probe_account_server(payload: ProbeIn) -> dict:
    """未命中预设时按邮箱域名探测 IMAP/SMTP（autoconfig → 常见主机名试连）。

    命中预设的域名直接返回 found=False（前端已有预填，无需探测）。
    """
    email = payload.email.strip()
    if not EMAIL_RE.match(email):
        raise HTTPException(400, "邮箱地址格式不正确")
    if match_provider(email):
        return {"found": False, "note": None}
    preset = probe_server(email)
    if preset is None:
        return {"found": False, "note": None}
    return {
        "found": True,
        "imap_server": preset.imap_server,
        "imap_port": preset.imap_port,
        "smtp_server": preset.smtp_server,
        "smtp_port": preset.smtp_port,
        "note": preset.note,
    }


@router.post("/accounts")
def add_account(payload: AccountIn) -> dict:
    cfg, preset_name = _resolve_config(payload)
    ok, detail = imap_client.test_connection(cfg)
    if not ok:
        raise HTTPException(400, detail)

    conn = get_conn()
    existing = conn.execute("SELECT id FROM accounts WHERE email = ?", (cfg.email,)).fetchone()
    if existing:
        raise HTTPException(400, "该邮箱已添加")

    count = conn.execute("SELECT COUNT(*) AS n FROM accounts").fetchone()["n"]
    color = COLOR_PALETTE[int(count) % len(COLOR_PALETTE)]
    cursor = conn.execute(
        "INSERT INTO accounts (email, provider_name, imap_server, imap_port,"
        " smtp_server, smtp_port, color, status)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, 'never_synced')",
        (cfg.email, preset_name or "自定义", cfg.imap_server, cfg.imap_port,
         cfg.smtp_server, cfg.smtp_port, color),
    )
    conn.commit()
    account_id = int(cursor.lastrowid)
    set_secret(f"account_pwd:{account_id}", payload.password)

    account = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
    # 首屏同步转后台：接口立即返回，进度经账号 status/status_detail 轮询可见
    sync_engine.start_sync({"id": account_id, **{k: account[k] for k in
                                            ("email", "imap_server", "imap_port")}})
    return {"account": _account_dict(account)}


@router.get("/accounts")
def list_accounts() -> dict:
    rows = get_conn().execute("SELECT * FROM accounts ORDER BY id").fetchall()
    return {"accounts": [_account_dict(r) for r in rows]}


GRANT_KEYS = ("read", "draft", "organize", "send", "delete")


class AiGrantsIn(BaseModel):
    read: bool = True
    draft: bool = False
    organize: bool = False
    send: bool = False
    delete: bool = False
    is_ai_mailbox: bool | None = None  # 顺带切换 AI 专属邮箱标记（二次确认在前端）


@router.patch("/accounts/{account_id}/ai-grants")
def update_ai_grants(account_id: int, payload: AiGrantsIn) -> dict:
    """账号级 AI 细粒度授权（v0.4 P6，REDESIGN_PLAN §6.4）：5 授权位 + AI 专属邮箱。"""
    row = get_conn().execute("SELECT id FROM accounts WHERE id = ?", (account_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "账号不存在")
    grants = {k: bool(getattr(payload, k)) for k in GRANT_KEYS}
    conn = get_conn()
    conn.execute("UPDATE accounts SET ai_grants = ? WHERE id = ?",
                 (json.dumps(grants), account_id))
    if payload.is_ai_mailbox is not None:
        conn.execute("UPDATE accounts SET is_ai_mailbox = ? WHERE id = ?",
                     (1 if payload.is_ai_mailbox else 0, account_id))
    conn.commit()
    return {"ok": True, "ai_grants": grants}


@router.patch("/accounts/{account_id}")
def update_account(account_id: int, payload: AccountPatchIn) -> dict:
    conn = get_conn()
    row = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
    if not row:
        raise HTTPException(404, "账号不存在")

    if payload.ai_permission is not None:
        if payload.ai_permission not in ("readonly", "draft_review"):
            raise HTTPException(400, "ai_permission 需为 readonly/draft_review")
        conn.execute(
            "UPDATE accounts SET ai_permission = ? WHERE id = ?",
            (payload.ai_permission, account_id),
        )
        conn.commit()

    if payload.style_prompt is not None:
        # 空串=清除（存 NULL）；非空=覆盖（前端已限 2000 字）
        text = payload.style_prompt.strip()
        conn.execute(
            "UPDATE accounts SET style_prompt = ? WHERE id = ?",
            (text or None, account_id),
        )
        conn.commit()

    if payload.use_proxy is not None:
        conn.execute(
            "UPDATE accounts SET use_proxy = ? WHERE id = ?",
            (int(payload.use_proxy), account_id),
        )
        conn.commit()

    if payload.password is not None:
        if row["auth_type"] == "oauth2":
            raise HTTPException(400, "OAuth2 授权账号无需密码，请在账号卡片点「重新授权」更新令牌")
        cfg = imap_client.MailConfig(
            email=row["email"], password=payload.password,
            imap_server=row["imap_server"], imap_port=int(row["imap_port"]),
        )
        ok, detail = imap_client.test_connection(cfg)
        if not ok:
            raise HTTPException(400, detail)
        set_secret(f"account_pwd:{account_id}", payload.password)
        sync_engine._set_account_status(account_id, "ok")  # noqa: SLF001 — 模块内复用

    updated = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
    return {"ok": True, "account": _account_dict(updated)}


@router.delete("/accounts/{account_id}")
def delete_account(account_id: int) -> dict:
    conn = get_conn()
    row = conn.execute("SELECT id FROM accounts WHERE id = ?", (account_id,)).fetchone()
    if not row:
        raise HTTPException(404, "账号不存在")
    conn.execute("DELETE FROM emails WHERE account_id = ?", (account_id,))
    conn.execute("DELETE FROM sync_state WHERE account_id = ?", (account_id,))
    conn.execute("DELETE FROM folders WHERE account_id = ?", (account_id,))
    conn.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
    conn.commit()
    set_secret(f"account_pwd:{account_id}", None)
    oauth.delete_token(account_id)
    sync_engine.delete_account_files(account_id)
    return {"ok": True}


@router.post("/accounts/{account_id}/sync")
def sync_account_now(account_id: int, folder: str = "INBOX") -> dict:
    """触发后台同步，立即返回；进度与结果经账号状态与通知中心呈现。"""
    row = get_conn().execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
    if not row:
        raise HTTPException(404, "账号不存在")
    return sync_engine.start_sync(
        {"id": row["id"], "email": row["email"],
         "imap_server": row["imap_server"], "imap_port": row["imap_port"]},
        folders=(folder,),
    )

# 文件夹端点（列表/创建/重命名/删除）已迁至 api/folders.py（v0.4 P2，路径不变）
