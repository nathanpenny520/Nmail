"""发件人白/黑名单 API。

条目为完整邮箱地址，或以 @ 开头的域名（如 @newsletter.example.com）。
白名单：永远留在收件箱并跳过 AI；黑名单：直接归档并跳过 AI。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.pipeline import get_sender_lists
from app.db.database import get_conn

router = APIRouter(prefix="/api/sender-lists", tags=["sender-lists"])


class SenderListIn(BaseModel):
    pattern: str
    list_type: str  # whitelist | blacklist


@router.get("")
def list_entries() -> dict:
    rows = get_conn().execute(
        "SELECT id, pattern, list_type, created_at FROM sender_lists ORDER BY id DESC"
    ).fetchall()
    lists = get_sender_lists()
    return {
        "entries": [dict(r) for r in rows],
        "whitelist": lists.get("whitelist", []),
        "blacklist": lists.get("blacklist", []),
    }


@router.post("")
def add_entry(payload: SenderListIn) -> dict:
    if payload.list_type not in ("whitelist", "blacklist"):
        raise HTTPException(400, "list_type 需为 whitelist/blacklist")
    pattern = payload.pattern.strip().lower()
    if not pattern or ("@" not in pattern):
        raise HTTPException(400, "请填写邮箱地址或以 @ 开头的域名")
    conn = get_conn()
    existing = conn.execute(
        "SELECT id, list_type FROM sender_lists WHERE pattern = ?", (pattern,)
    ).fetchone()
    if existing:
        if existing["list_type"] == payload.list_type:
            return {"ok": True, "id": existing["id"]}
        conn.execute(
            "UPDATE sender_lists SET list_type = ? WHERE id = ?",
            (payload.list_type, existing["id"]),
        )
        conn.commit()
        return {"ok": True, "id": existing["id"], "moved": True}
    cursor = conn.execute(
        "INSERT INTO sender_lists (pattern, list_type) VALUES (?, ?)",
        (pattern, payload.list_type),
    )
    conn.commit()
    return {"ok": True, "id": int(cursor.lastrowid)}


@router.delete("/{entry_id}")
def remove_entry(entry_id: int) -> dict:
    conn = get_conn()
    conn.execute("DELETE FROM sender_lists WHERE id = ?", (entry_id,))
    conn.commit()
    return {"ok": True}
