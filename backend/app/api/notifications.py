"""应用内通知中心 API。"""
from __future__ import annotations

from fastapi import APIRouter

from app.db.database import get_conn

router = APIRouter(prefix="/api", tags=["notifications"])


@router.get("/notifications")
def list_notifications(unread_only: bool = False) -> dict:
    where = " WHERE is_read = 0" if unread_only else ""
    conn = get_conn()
    items = conn.execute(
        f"SELECT id, type, title, body, ref_id, is_read, created_at"
        f" FROM notifications{where} ORDER BY id DESC LIMIT 50"
    ).fetchall()
    unread = conn.execute(
        "SELECT COUNT(*) AS n FROM notifications WHERE is_read = 0"
    ).fetchone()["n"]
    return {
        "unread": unread,
        "items": [
            {
                "id": r["id"],
                "type": r["type"],
                "title": r["title"],
                "body": r["body"],
                "ref_id": r["ref_id"],
                "is_read": bool(r["is_read"]),
                "created_at": r["created_at"],
            }
            for r in items
        ],
    }


@router.post("/notifications/read-all")
def mark_all_read() -> dict:
    conn = get_conn()
    conn.execute("UPDATE notifications SET is_read = 1 WHERE is_read = 0")
    conn.commit()
    return {"ok": True}
