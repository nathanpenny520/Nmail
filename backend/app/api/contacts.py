"""通讯录 API（v0.4 P4 → 2026-09-12 改版，REDESIGN_PLAN §5.3/§5.4）：
聚合列表/搜索、按 email 作用域的增删改、联系组 CRUD 与成员管理、写信联想。

管理口径：同邮箱多账号聚合为一行——PATCH/DELETE 按行找到邮箱后作用于该邮箱的
全部行（改名/手机/备注全行生效并转 manual，改邮箱连带更新组成员表）。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core import contacts as contacts_core
from app.db.database import get_conn

router = APIRouter(prefix="/api/contacts", tags=["contacts"])


class ContactIn(BaseModel):
    email: str
    name: str = ""
    phone: str = ""
    notes: str = ""


class ContactUpdateIn(BaseModel):
    name: str | None = None
    email: str | None = None  # 改邮箱＝修正错别字；作用于该联系人的全部行
    phone: str | None = None
    notes: str | None = None


class GroupIn(BaseModel):
    name: str


class MembersIn(BaseModel):
    emails: list[str]


def _dict(row) -> dict:  # noqa: ANN001
    return {
        "id": row["id"],
        "account_id": row["account_id"],
        "email": row["email"],
        "name": row["name"],
        "phone": row["phone"],
        "source": row["source"],
        "notes": row["notes"],
        "use_count": row["use_count"],
        "last_seen_at": row["last_seen_at"],
        "created_at": row["created_at"],
    }


def _agg_dict(row) -> dict:  # noqa: ANN001
    return {
        "id": row["id"],
        "email": row["email"],
        "name": row["name"],
        "phone": row["phone"],
        "notes": row["notes"],
        "sources": (row["sources"] or "").split(","),
        "use_count": row["use_count"],
        "last_seen_at": row["last_seen_at"],
        "created_at": row["created_at"],
        "account_rows": row["account_rows"],
    }


@router.get("")
def list_contacts(
    q: str = "",
    source: str = "",
    group_id: int | None = None,
    ungrouped: bool = False,
    limit: int = 200,
) -> dict:
    """聚合列表/搜索 + 左侧树四视图计数（按使用频次与最近联系排序）。"""
    return {
        "contacts": contacts_core.list_contacts_agg(
            q=q,
            source=source or None,
            group_id=group_id,
            ungrouped=ungrouped,
            limit=limit,
        ),
        "counts": contacts_core.view_counts(),
    }


@router.get("/suggest")
def suggest_contacts(q: str = "", limit: int = 8) -> dict:
    """写信联想（跨账号去重、按使用频次×最近排序）。"""
    return {"items": contacts_core.suggest(q, limit=max(1, min(limit, 20)))}


@router.get("/groups")
def list_groups() -> dict:
    return {"groups": contacts_core.list_groups()}


@router.post("/groups")
def create_group(payload: GroupIn) -> dict:
    try:
        gid = contacts_core.create_group(payload.name)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"group": next(g for g in contacts_core.list_groups() if g["id"] == gid)}


@router.patch("/groups/{group_id}")
def rename_group(group_id: int, payload: GroupIn) -> dict:
    if get_conn().execute("SELECT 1 FROM contact_groups WHERE id = ?", (group_id,)).fetchone() is None:
        raise HTTPException(404, "联系组不存在")
    try:
        contacts_core.rename_group(group_id, payload.name)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"group": next(g for g in contacts_core.list_groups() if g["id"] == group_id)}


@router.delete("/groups/{group_id}")
def delete_group(group_id: int) -> dict:
    if get_conn().execute("SELECT 1 FROM contact_groups WHERE id = ?", (group_id,)).fetchone() is None:
        raise HTTPException(404, "联系组不存在")
    contacts_core.delete_group(group_id)
    return {"ok": True}


@router.post("/groups/{group_id}/members")
def add_members(group_id: int, payload: MembersIn) -> dict:
    if get_conn().execute("SELECT 1 FROM contact_groups WHERE id = ?", (group_id,)).fetchone() is None:
        raise HTTPException(404, "联系组不存在")
    added = contacts_core.set_members(group_id, payload.emails, add=True)
    return {"ok": True, "added": added}


@router.post("/groups/{group_id}/members/remove")
def remove_members(group_id: int, payload: MembersIn) -> dict:
    """移除成员用 POST 子路径：DELETE+body 在部分客户端（如 TestClient）不可用。"""
    if get_conn().execute("SELECT 1 FROM contact_groups WHERE id = ?", (group_id,)).fetchone() is None:
        raise HTTPException(404, "联系组不存在")
    removed = contacts_core.set_members(group_id, payload.emails, add=False)
    return {"ok": True, "removed": removed}


@router.get("/{contact_id}")
def get_contact(contact_id: int) -> dict:
    """详情：聚合行 + 各账号明细行（归属展示用）。"""
    row = get_conn().execute(
        f"{contacts_core.AGG_SELECT} WHERE id = ? GROUP BY email", (contact_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(404, "联系人不存在")
    return {"contact": _agg_dict(row), "rows": contacts_core.contact_rows(row["email"])}


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
        "INSERT INTO contacts (account_id, email, name, phone, source, notes)"
        " VALUES (NULL, ?, ?, ?, 'manual', ?)",
        (email, payload.name.strip(), payload.phone.strip(), payload.notes.strip()),
    )
    conn.commit()
    return {"contact": _dict(conn.execute("SELECT * FROM contacts WHERE id = ?", (cur.lastrowid,)).fetchone())}


@router.patch("/{contact_id}")
def update_contact(contact_id: int, payload: ContactUpdateIn) -> dict:
    row = get_conn().execute("SELECT * FROM contacts WHERE id = ?", (contact_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "联系人不存在")
    conn = get_conn()
    old_email = row["email"]
    scope = conn.execute("SELECT id FROM contacts WHERE email = ?", (old_email,)).fetchall()
    final_email = old_email
    if payload.email is not None:
        new_email = contacts_core.norm_email(payload.email)
        if not contacts_core.EMAIL_RE.match(new_email):
            raise HTTPException(400, "邮箱地址不合法")
        if new_email != old_email:
            scope_ids = {r["id"] for r in scope}
            dup = conn.execute(
                "SELECT id FROM contacts WHERE email = ?", (new_email,)
            ).fetchall()
            if any(r["id"] not in scope_ids for r in dup):
                raise HTTPException(400, "该地址已在通讯录中")
            # 作用到全部行，并连带组成员表（成员按 email 记）
            conn.execute("UPDATE contacts SET email = ? WHERE email = ?", (new_email, old_email))
            conn.execute(
                "UPDATE contact_group_members SET email = ? WHERE email = ?",
                (new_email, old_email),
            )
            final_email = new_email
    if payload.name is not None:
        # 手动改过姓名即转 manual：此后自动采集不再覆盖
        conn.execute(
            "UPDATE contacts SET name = ?, source = 'manual' WHERE email = ?",
            (payload.name.strip(), final_email),
        )
    if payload.phone is not None:
        conn.execute(
            "UPDATE contacts SET phone = ? WHERE email = ?", (payload.phone.strip(), final_email)
        )
    if payload.notes is not None:
        conn.execute(
            "UPDATE contacts SET notes = ? WHERE email = ?", (payload.notes.strip(), final_email)
        )
    conn.commit()
    agg = get_conn().execute(
        f"{contacts_core.AGG_SELECT} WHERE email = ? GROUP BY email", (final_email,)
    ).fetchone()
    return {"contact": _agg_dict(agg)}


@router.delete("/{contact_id}")
def delete_contact(contact_id: int) -> dict:
    """删除＝移除该邮箱的全部行（聚合口径下一个邮箱即一个联系人）+ 组成员清理。"""
    conn = get_conn()
    row = conn.execute("SELECT email FROM contacts WHERE id = ?", (contact_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "联系人不存在")
    conn.execute("DELETE FROM contacts WHERE email = ?", (row["email"],))
    contacts_core.cleanup_members()
    conn.commit()
    return {"ok": True}
