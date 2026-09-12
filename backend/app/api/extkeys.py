"""对外 API 密钥管理（v0.4 P7，REDESIGN_PLAN §7.2）：仅内部设置页使用
（走常规本机来源校验）。明文存 secrets.json 所见即所存（与 AI key 同惯例），
表内只留 sha256 哈希用于认证校验；吊销行保留供调用日志对账。
"""
from __future__ import annotations

import hashlib
import json
import secrets as pysecrets

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.api.ext import RATE_LIMIT_PER_MIN
from app.db.database import get_conn, get_setting, set_setting
from app.security import get_secret, set_secret

router = APIRouter(prefix="/api/extkeys", tags=["ext-api-keys"])


class KeyCreateIn(BaseModel):
    name: str = Field(default="", max_length=100)
    scopes: list[str] = Field(default_factory=lambda: ["read"])
    daily_limit: int | None = Field(default=None, ge=0, le=100000)  # 0/null=不限


class KeyUpdateIn(BaseModel):
    name: str | None = Field(default=None, max_length=100)
    scopes: list[str] | None = None
    daily_limit: int | None = Field(default=None, ge=0, le=100000)  # 0=不限
    reset: bool = False  # true=重置密钥值（生成新串，旧串立即失效）


def _norm_daily_limit(v: int | None) -> int | None:
    return v or None


class EnabledIn(BaseModel):
    enabled: bool
    log_enabled: bool | None = None


def _key_row_dict(row, with_plaintext: bool = True) -> dict:  # noqa: ANN001
    d = {
        "id": row["id"],
        "name": row["name"],
        "scopes": json.loads(row["scopes"] or "[]"),
        "daily_limit": row["daily_limit"],
        "last_used_at": row["last_used_at"],
        "revoked": bool(row["revoked"]),
        "created_at": row["created_at"],
    }
    if with_plaintext and not d["revoked"]:
        # 所见即所存：明文随行回显（secrets.json），前端默认遮蔽、点击可见
        d["key"] = get_secret(f"ext_api_key:{row['id']}") or ""
    return d


@router.get("")
def list_keys() -> dict:
    rows = get_conn().execute("SELECT * FROM api_keys ORDER BY id DESC").fetchall()
    return {
        "enabled": bool(get_setting("api_enabled", False)),
        "log_enabled": bool(get_setting("api_log_enabled", True)),
        "rate_limit_per_min": RATE_LIMIT_PER_MIN,
        "base_url": "/api/ext/v1",
        "keys": [_key_row_dict(r) for r in rows],
    }


@router.post("")
def create_key(payload: KeyCreateIn) -> dict:
    scopes = [s for s in payload.scopes if s in ("read", "write", "send", "agent")]
    if not scopes:
        raise HTTPException(400, "至少勾选一个 scope")
    plaintext = "nmail_" + pysecrets.token_urlsafe(24)
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO api_keys (name, key_hash, scopes, daily_limit) VALUES (?, ?, ?, ?)",
        (payload.name.strip(), hashlib.sha256(plaintext.encode()).hexdigest(),
         json.dumps(scopes), _norm_daily_limit(payload.daily_limit)),
    )
    conn.commit()
    set_secret(f"ext_api_key:{cur.lastrowid}", plaintext)
    row = conn.execute("SELECT * FROM api_keys WHERE id = ?", (cur.lastrowid,)).fetchone()
    return {"key": _key_row_dict(row)}


@router.patch("/{key_id}")
def update_key(key_id: int, payload: KeyUpdateIn) -> dict:
    row = get_conn().execute("SELECT * FROM api_keys WHERE id = ?", (key_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Key 不存在")
    sets, values = [], []
    new_plaintext = None
    if payload.name is not None:
        sets.append("name = ?")
        values.append(payload.name.strip())
    if payload.scopes is not None:
        scopes = [s for s in payload.scopes if s in ("read", "write", "send", "agent")]
        if not scopes:
            raise HTTPException(400, "至少勾选一个 scope")
        sets.append("scopes = ?")
        values.append(json.dumps(scopes))
    if payload.daily_limit is not None:
        sets.append("daily_limit = ?")
        values.append(_norm_daily_limit(payload.daily_limit))
    if payload.reset and not row["revoked"]:
        new_plaintext = "nmail_" + pysecrets.token_urlsafe(24)
        sets.append("key_hash = ?")
        values.append(hashlib.sha256(new_plaintext.encode()).hexdigest())
    if sets:
        conn = get_conn()
        conn.execute(f"UPDATE api_keys SET {', '.join(sets)} WHERE id = ?", [*values, key_id])  # noqa: S608 — 白名单字段拼接
        conn.commit()
        if new_plaintext:
            set_secret(f"ext_api_key:{key_id}", new_plaintext)
    fresh = get_conn().execute("SELECT * FROM api_keys WHERE id = ?", (key_id,)).fetchone()
    return {"key": _key_row_dict(fresh)}


@router.delete("/{key_id}")
def revoke_key(key_id: int) -> dict:
    row = get_conn().execute("SELECT * FROM api_keys WHERE id = ?", (key_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Key 不存在")
    conn = get_conn()
    conn.execute("UPDATE api_keys SET revoked = 1 WHERE id = ?", (key_id,))
    conn.commit()
    set_secret(f"ext_api_key:{key_id}", None)
    return {"ok": True}


@router.post("/enabled")
def set_enabled(payload: EnabledIn) -> dict:
    set_setting("api_enabled", payload.enabled)
    if payload.log_enabled is not None:
        set_setting("api_log_enabled", payload.log_enabled)
    return {"ok": True, "enabled": payload.enabled}


@router.get("/calls")
def list_calls(limit: int = 100) -> dict:
    """调用日志（设置页查看器；30 天保留，/health 不记）。"""
    limit = max(1, min(limit, 500))
    rows = get_conn().execute(
        "SELECT c.*, k.name AS key_name FROM api_calls c"
        " LEFT JOIN api_keys k ON k.id = c.key_id"
        " ORDER BY c.id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return {"calls": [
        {
            "id": r["id"], "key_id": r["key_id"],
            "key_name": r["key_name"] or ("（无密钥）" if not r["key_id"] else "（已删）"),
            "method": r["method"], "path": r["path"], "status": r["status"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]}
