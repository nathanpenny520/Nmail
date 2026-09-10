"""账号管理 API：添加（带连接测试）、列表、删除、手动同步、文件夹、服务商预设。"""
from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core import imap_client, sync as sync_engine
from app.core.providers import MANUAL_NOTE, PRESETS
from app.db.database import get_conn
from app.security import get_secret, set_secret

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


def _resolve_config(payload: AccountIn) -> tuple[imap_client.MailConfig, str | None]:
    """按预设自动补全服务器配置，返回 (MailConfig, 匹配到的预设名)。"""
    email = payload.email.strip()
    if not EMAIL_RE.match(email):
        raise HTTPException(400, "邮箱地址格式不正确")
    preset = None
    from app.core.providers import match_provider

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
        "ai_permission": row["ai_permission"] if "ai_permission" in row.keys() else "draft_review",
        "status": row["status"],
        "status_detail": row["status_detail"],
        "last_sync_at": row["last_sync_at"],
    }


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
    sync_result = sync_engine.sync_account({"id": account_id, **{k: account[k] for k in
                                            ("email", "imap_server", "imap_port")}})
    return {"account": _account_dict(account), "sync": sync_result}


@router.get("/accounts")
def list_accounts() -> dict:
    rows = get_conn().execute("SELECT * FROM accounts ORDER BY id").fetchall()
    return {"accounts": [_account_dict(r) for r in rows]}


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

    if payload.password is not None:
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
    conn.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
    conn.commit()
    set_secret(f"account_pwd:{account_id}", None)
    sync_engine.delete_account_files(account_id)
    return {"ok": True}


@router.post("/accounts/{account_id}/sync")
def sync_account_now(account_id: int) -> dict:
    row = get_conn().execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
    if not row:
        raise HTTPException(404, "账号不存在")
    return sync_engine.sync_account(
        {"id": row["id"], "email": row["email"],
         "imap_server": row["imap_server"], "imap_port": row["imap_port"]}
    )


@router.get("/accounts/{account_id}/folders")
def list_account_folders(account_id: int) -> dict:
    row = get_conn().execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
    if not row:
        raise HTTPException(404, "账号不存在")
    password = get_secret(f"account_pwd:{account_id}")
    if not password:
        raise HTTPException(400, "缺少密码凭证")
    cfg = imap_client.MailConfig(
        email=row["email"], password=password,
        imap_server=row["imap_server"], imap_port=int(row["imap_port"]),
    )
    try:
        with imap_client.connect_imap(cfg) as mb:
            return {"folders": imap_client.list_folders(mb)}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"获取文件夹失败：{exc}") from exc
