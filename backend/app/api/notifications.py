"""应用内通知中心 API。"""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException

from app.db.database import get_conn

router = APIRouter(prefix="/api", tags=["notifications"])


def _to_local_iso(value: str) -> str:
    """created_at 落库为 datetime('now')（UTC 裸串），出口转系统时区 ISO；自定义时区将来在此单点接入。"""
    try:
        dt = datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    except ValueError:
        return value
    return dt.astimezone().isoformat(timespec="seconds")


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
                "created_at": _to_local_iso(r["created_at"]),
            }
            for r in items
        ],
    }


@router.post("/notifications/{notification_id}/read")
def mark_notification_read(notification_id: int) -> dict:
    conn = get_conn()
    row = conn.execute("SELECT id FROM notifications WHERE id = ?", (notification_id,)).fetchone()
    if not row:
        raise HTTPException(404, "通知不存在")
    conn.execute("UPDATE notifications SET is_read = 1 WHERE id = ?", (notification_id,))
    conn.commit()
    return {"ok": True}


@router.post("/notifications/read-all")
def mark_all_read() -> dict:
    conn = get_conn()
    conn.execute("UPDATE notifications SET is_read = 1 WHERE is_read = 0")
    conn.commit()
    return {"ok": True}


@router.delete("/notifications/{notification_id}")
def delete_notification(notification_id: int) -> dict:
    conn = get_conn()
    row = conn.execute("SELECT id FROM notifications WHERE id = ?", (notification_id,)).fetchone()
    if not row:
        raise HTTPException(404, "通知不存在")
    conn.execute("DELETE FROM notifications WHERE id = ?", (notification_id,))
    conn.commit()
    return {"ok": True}


@router.post("/notifications/clear-read")
def clear_read_notifications() -> dict:
    conn = get_conn()
    cursor = conn.execute("DELETE FROM notifications WHERE is_read = 1")
    conn.commit()
    return {"ok": True, "deleted": cursor.rowcount}
