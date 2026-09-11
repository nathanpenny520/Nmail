"""AI 会话持久化：列表、消息读取、重命名/置顶、删除。

列表按 置顶 > updated_at 倒序 排列；删除会话级联清理消息。
标题默认「新对话」，首轮用户消息落库时自动截取生成，可手动重命名覆盖。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.db.database import get_conn

router = APIRouter(prefix="/api/ai", tags=["chats"])

TITLE_PLACEHOLDER = "新对话"
TITLE_MAX_LEN = 30


def _session_dict(row, message_count: int | None = None) -> dict:
    data = {
        "id": row["id"],
        "title": row["title"],
        "kind": row["kind"],
        "account_id": row["account_id"],
        "pinned": bool(row["pinned"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
    if message_count is not None:
        data["message_count"] = message_count
    return data


def require_session(session_id: int) -> None:
    """校验会话存在，否则 404（落库前的守卫，避免孤儿消息）。"""
    row = get_conn().execute(
        "SELECT id FROM chat_sessions WHERE id = ?", (session_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(404, "会话不存在")


def append_message(session_id: int, role: str, content: str, model: str = "") -> None:
    """落库一条消息并刷新会话 updated_at；首轮用户消息自动生成标题。"""
    conn = get_conn()
    conn.execute(
        "INSERT INTO chat_messages (session_id, role, content, model) VALUES (?, ?, ?, ?)",
        (session_id, role, content, model),
    )
    if role == "user":
        row = conn.execute(
            "SELECT title FROM chat_sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if row and (not row["title"] or row["title"] == TITLE_PLACEHOLDER):
            title = content.strip().replace("\n", " ")[:TITLE_MAX_LEN] or TITLE_PLACEHOLDER
            conn.execute(
                "UPDATE chat_sessions SET title = ?, updated_at = datetime('now') WHERE id = ?",
                (title, session_id),
            )
            conn.commit()
            return
    conn.execute(
        "UPDATE chat_sessions SET updated_at = datetime('now') WHERE id = ?",
        (session_id,),
    )
    conn.commit()


class ChatCreateIn(BaseModel):
    title: str = ""
    account_id: int | None = None


@router.get("/chats")
def list_chats() -> dict:
    rows = get_conn().execute(
        "SELECT s.*, COUNT(m.id) AS message_count"
        " FROM chat_sessions s LEFT JOIN chat_messages m ON m.session_id = s.id"
        " GROUP BY s.id"
        " ORDER BY s.pinned DESC, s.updated_at DESC, s.id DESC"
    ).fetchall()
    return {"sessions": [_session_dict(r, r["message_count"]) for r in rows]}


@router.post("/chats")
def create_chat(payload: ChatCreateIn) -> dict:
    conn = get_conn()
    title = payload.title.strip() or TITLE_PLACEHOLDER
    cur = conn.execute(
        "INSERT INTO chat_sessions (title, account_id) VALUES (?, ?)",
        (title, payload.account_id),
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM chat_sessions WHERE id = ?", (cur.lastrowid,)
    ).fetchone()
    return {"session": _session_dict(row)}


@router.get("/chats/{session_id}")
def read_chat(session_id: int) -> dict:
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM chat_sessions WHERE id = ?", (session_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(404, "会话不存在")
    msgs = conn.execute(
        "SELECT id, role, content, model, created_at"
        " FROM chat_messages WHERE session_id = ? ORDER BY id",
        (session_id,),
    ).fetchall()
    return {
        "session": _session_dict(row),
        "messages": [
            {
                "id": m["id"],
                "role": m["role"],
                "content": m["content"],
                "model": m["model"],
                "created_at": m["created_at"],
            }
            for m in msgs
        ],
    }


class ChatUpdateIn(BaseModel):
    title: str | None = Field(default=None, max_length=60)
    pinned: bool | None = None


@router.patch("/chats/{session_id}")
def update_chat(session_id: int, payload: ChatUpdateIn) -> dict:
    conn = get_conn()
    require_session(session_id)
    if payload.title is not None:
        title = payload.title.strip() or TITLE_PLACEHOLDER
        conn.execute("UPDATE chat_sessions SET title = ? WHERE id = ?", (title, session_id))
    if payload.pinned is not None:
        conn.execute(
            "UPDATE chat_sessions SET pinned = ? WHERE id = ?",
            (1 if payload.pinned else 0, session_id),
        )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM chat_sessions WHERE id = ?", (session_id,)
    ).fetchone()
    return {"session": _session_dict(row)}


@router.delete("/chats/{session_id}")
def delete_chat(session_id: int) -> dict:
    conn = get_conn()
    require_session(session_id)
    conn.execute("DELETE FROM chat_sessions WHERE id = ?", (session_id,))
    conn.commit()
    return {"ok": True}
