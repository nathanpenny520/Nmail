"""通讯录 API（v0.4 P4，REDESIGN_PLAN §5.3）：列表/搜索、手动增删改、写信联想。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core import contacts as contacts_core
from app.db.database import get_conn

router = APIRouter(prefix="/api/contacts", tags=["contacts"])


class ContactIn(BaseModel):
    email: str
    name: str = ""
    notes: str = ""


class ContactUpdateIn(BaseModel):
    name: str | None = None
    notes: str | None = None


def _dict(row) -> dict:  # noqa: ANN001
    return {
        "id": row["id"],
        "account_id": row["account_id"],
        "email": row["email"],
        "name": row["name"],
        "source": row["source"],
        "notes": row["notes"],
        "use_count": row["use_count"],
        "last_seen_at": row["last_seen_at"],
        "created_at": row["created_at"],
    }


@router.get("")
def list_contacts(q: str = "", limit: int = 200) -> dict:
    """通讯录列表/搜索（≥3 字走 email/name 子串；按使用频次与最近联系排序）。"""
    limit = max(1, min(limit, 500))
    where, params = "", []
    query = q.strip()
    if query:
        like = f"%{query}%"
        where = " WHERE email LIKE ? OR name LIKE ?"
        params = [like, like]
    rows = get_conn().execute(
        f"SELECT * FROM contacts{where}"
        " ORDER BY use_count DESC, last_seen_at DESC, id DESC LIMIT ?",
        [*params, limit],
    ).fetchall()
    return {"contacts": [_dict(r) for r in rows]}


@router.get("/suggest")
def suggest_contacts(q: str = "", limit: int = 8) -> dict:
    """写信联想（跨账号去重、按使用频次×最近排序）。"""
    return {"items": contacts_core.suggest(q, limit=max(1, min(limit, 20)))}


@router.post("")
def create_contact(payload: ContactIn) -> dict:
    """手动新增（全局作用域，source=manual：不被自动采集覆盖）。"""
    email = contacts_core.norm_email(payload.email)
    if not contacts_core.EMAIL_RE.match(email):
        raise HTTPException(400, "邮箱地址不合法")
    conn = get_conn()
    dup = conn.execute(
        "SELECT id FROM contacts WHERE email = ? AND account_id IS NULL", (email,)
    ).fetchone()
    if dup:
        raise HTTPException(400, "该地址已在通讯录中")
    cur = conn.execute(
        "INSERT INTO contacts (account_id, email, name, source, notes)"
        " VALUES (NULL, ?, ?, 'manual', ?)",
        (email, payload.name.strip(), payload.notes.strip()),
    )
    conn.commit()
    return {"contact": _dict(conn.execute("SELECT * FROM contacts WHERE id = ?", (cur.lastrowid,)).fetchone())}


@router.patch("/{contact_id}")
def update_contact(contact_id: int, payload: ContactUpdateIn) -> dict:
    row = get_conn().execute("SELECT * FROM contacts WHERE id = ?", (contact_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "联系人不存在")
    conn = get_conn()
    if payload.name is not None:
        # 手动改过姓名即转 manual：此后自动采集不再覆盖
        conn.execute(
            "UPDATE contacts SET name = ?, source = 'manual' WHERE id = ?",
            (payload.name.strip(), contact_id),
        )
    if payload.notes is not None:
        conn.execute("UPDATE contacts SET notes = ? WHERE id = ?", (payload.notes.strip(), contact_id))
    conn.commit()
    return {"contact": _dict(get_conn().execute("SELECT * FROM contacts WHERE id = ?", (contact_id,)).fetchone())}


@router.delete("/{contact_id}")
def delete_contact(contact_id: int) -> dict:
    conn = get_conn()
    if conn.execute("SELECT 1 FROM contacts WHERE id = ?", (contact_id,)).fetchone() is None:
        raise HTTPException(404, "联系人不存在")
    conn.execute("DELETE FROM contacts WHERE id = ?", (contact_id,))
    conn.commit()
    return {"ok": True}
