"""通讯录（v0.4 P4，REDESIGN_PLAN §5.3）：往来联系人自动采集与写信联想。

采集零操作：收信入库采集发件人、发送成功采集收件人（upsert，use_count 计数、
last_seen_at 刷新）；手动编辑过的行（source=manual）不被自动覆盖，仅累计计数。
account_id 作用域：每账号各自的往来（UNIQUE(COALESCE(account_id,0), email)），
手动新增为全局（account_id NULL）；联想时全局查（跨账号去重取最优行）。
"""
from __future__ import annotations

import re

from app.db.database import get_conn, get_setting

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def auto_collect_enabled() -> bool:
    """自动采集开关（设置页通讯录区可关）：默认开；关了只停自动入册，不动已有数据。"""
    return bool(get_setting("contacts_auto_collect", True))


def norm_email(email: str) -> str:
    return (email or "").strip().lower()


def split_addresses(raw: str) -> list[str]:
    """逗号分隔的地址串 → 规范化列表（去空）。"""
    return [p for p in (norm_email(x) for x in (raw or "").split(",")) if p]


def extract_addresses(raw: str) -> list[str]:
    """地址串 → 纯 email 列表（支持「Name <a@x>」，与 collect_addresses 同一解析口径）。

    split_addresses 只按逗号切分；带显示名的条目（如「张三 <z@x.com>」）需要
    提取纯地址后再比对（自动模式收件人约束，审查 S2）。
    """
    out: list[str] = []
    for part in (raw or "").split(","):
        part = part.strip()
        if not part:
            continue
        m = re.match(r"^(.*?)<([^<>]+)>$", part)
        addr = norm_email(m.group(2) if m else part)
        if addr and addr not in out:
            out.append(addr)
    return out


def collect_addresses(raw: str, account_id: int | None) -> int:
    """从逗号分隔地址串采集全部联系人（发送侧 To/Cc/Bcc，支持「Name <a@x>」）。"""
    if not auto_collect_enabled():
        return 0
    n = 0
    for part in (raw or "").split(","):
        part = part.strip()
        if not part:
            continue
        m = re.match(r"^(.*?)<([^<>]+)>$", part)
        if m:
            upsert_contact(m.group(2), m.group(1).strip().strip('"') or None, account_id)
        else:
            upsert_contact(part, None, account_id)
        n += 1
    return n


def upsert_contact(email: str, name: str | None = None, account_id: int | None = None) -> None:
    """采集一个联系人（SELECT-then-UPDATE/INSERT：表达式索引不支持 upsert 冲突目标，
    且 account_id 作用域含 NULL）。source=manual 的行只刷计数与时间，不覆盖姓名。"""
    email = norm_email(email)
    if not EMAIL_RE.match(email):
        return
    name = (name or "").strip()
    conn = get_conn()
    row = conn.execute(
        "SELECT id, source FROM contacts WHERE email = ? AND account_id IS ?",
        (email, account_id),
    ).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO contacts (account_id, email, name, source, use_count, last_seen_at)"
            " VALUES (?, ?, ?, 'auto', 1, datetime('now'))",
            (account_id, email, name),
        )
    elif row["source"] == "manual":
        conn.execute(
            "UPDATE contacts SET use_count = use_count + 1, last_seen_at = datetime('now')"
            " WHERE id = ?",
            (row["id"],),
        )
    else:
        conn.execute(
            "UPDATE contacts SET use_count = use_count + 1, last_seen_at = datetime('now'),"
            " name = CASE WHEN ? != '' THEN ? ELSE name END WHERE id = ?",
            (name, name, row["id"]),
        )
    conn.commit()


def collect_sender(sender_email: str, sender_name: str | None, account_id: int) -> None:
    """收信侧：采集发件人。"""
    if not auto_collect_enabled():
        return
    upsert_contact(sender_email, sender_name, account_id)


def suggest(q: str, limit: int = 8) -> list[dict]:
    """写信联想：use_count × 最近使用加权，email/name 子串匹配；全局去重取最优行。"""
    q = norm_email(q)
    if not q:
        rows = get_conn().execute(
            "SELECT email, MAX(name) AS name, MAX(account_id) AS account_id,"
            " SUM(use_count) AS use_count, MAX(last_seen_at) AS last_seen_at"
            " FROM contacts GROUP BY email"
            " ORDER BY use_count DESC, last_seen_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    else:
        like = f"%{q}%"
        rows = get_conn().execute(
            "SELECT email, MAX(name) AS name, MAX(account_id) AS account_id,"
            " SUM(use_count) AS use_count, MAX(last_seen_at) AS last_seen_at"
            " FROM contacts WHERE email LIKE ? OR name LIKE ?"
            " GROUP BY email ORDER BY use_count DESC, last_seen_at DESC LIMIT ?",
            (like, like, limit),
        ).fetchall()
    return [
        {"email": r["email"], "name": r["name"], "use_count": r["use_count"]}
        for r in rows
    ]


# ── 管理界面（REDESIGN_PLAN §5.4，2026-09-12 改版）：聚合列表 + 自定义联系组 ──

AGG_SELECT = (
    "SELECT MIN(id) AS id, email, MAX(name) AS name, MAX(phone) AS phone, MAX(notes) AS notes,"
    " GROUP_CONCAT(DISTINCT source) AS sources,"
    " SUM(use_count) AS use_count, MAX(last_seen_at) AS last_seen_at,"
    " MIN(created_at) AS created_at, COUNT(*) AS account_rows"
    " FROM contacts"
)


def _emails_in_group(group_id: int) -> str:
    return f"email IN (SELECT email FROM contact_group_members WHERE group_id = {int(group_id)})"


def _emails_not_grouped() -> str:
    return "email NOT IN (SELECT email FROM contact_group_members)"


def list_contacts_agg(
    q: str = "",
    source: str | None = None,
    group_id: int | None = None,
    ungrouped: bool = False,
    limit: int = 200,
) -> list[dict]:
    """管理列表：同邮箱多账号聚合为一行（次数合并、来源多值），与写信联想同口径。

    source/ungrouped 过滤放在 HAVING/GROUP BY 语义层（按「该邮箱存在 auto/manual 行」
    判定），q 与组过滤放 WHERE 行层。任一过滤组合都走同一聚合骨架。
    """
    where, having, params = [], [], []
    query = (q or "").strip()
    if query:
        where.append("(email LIKE ? OR name LIKE ?)")
        params += [f"%{query}%", f"%{query}%"]
    if group_id is not None:
        where.append(_emails_in_group(group_id))
    if ungrouped:
        where.append(_emails_not_grouped())
    if source in ("auto", "manual"):
        having.append(f"SUM(source = '{source}') > 0")
    sql = AGG_SELECT
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " GROUP BY email"
    if having:
        sql += " HAVING " + " AND ".join(having)
    sql += " ORDER BY use_count DESC, last_seen_at DESC, id DESC LIMIT ?"
    rows = get_conn().execute(sql, [*params, max(1, min(limit, 500))]).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["sources"] = (d["sources"] or "").split(",")
        out.append(d)
    return out


def view_counts() -> dict:
    """左侧树四个智能视图的计数（一次查询算齐）。"""
    row = get_conn().execute(
        "SELECT COUNT(DISTINCT email) AS all_,"
        " COUNT(DISTINCT CASE WHEN source = 'auto' THEN email END) AS auto_,"
        " COUNT(DISTINCT CASE WHEN source = 'manual' THEN email END) AS manual_,"
        " COUNT(DISTINCT CASE WHEN email NOT IN (SELECT email FROM contact_group_members)"
        " THEN email END) AS ungrouped_ FROM contacts"
    ).fetchone()
    return {
        "all": row["all_"],
        "auto": row["auto_"],
        "manual": row["manual_"],
        "ungrouped": row["ungrouped_"],
    }


def contact_rows(email: str) -> list[dict]:
    """某邮箱在各账号下的明细行（详情视图展示归属用）。"""
    rows = get_conn().execute(
        "SELECT id, account_id, email, name, phone, source, use_count, last_seen_at"
        " FROM contacts WHERE email = ? ORDER BY account_id IS NOT NULL, account_id",
        (norm_email(email),),
    ).fetchall()
    return [dict(r) for r in rows]


def list_groups() -> list[dict]:
    """联系组列表（带成员数与成员 email；孤儿成员行在读取侧天然不可见）。"""
    rows = get_conn().execute(
        "SELECT g.id, g.name, g.created_at,"
        " (SELECT COUNT(*) FROM contact_group_members m"
        "  WHERE m.group_id = g.id AND m.email IN (SELECT email FROM contacts)) AS member_count"
        " FROM contact_groups g ORDER BY g.id"
    ).fetchall()
    groups = [dict(r) for r in rows]
    members = get_conn().execute(
        "SELECT group_id, email FROM contact_group_members"
        " WHERE email IN (SELECT email FROM contacts) ORDER BY email"
    ).fetchall()
    by_gid: dict[int, list[str]] = {g["id"]: [] for g in groups}
    for m in members:
        if m["group_id"] in by_gid:
            by_gid[m["group_id"]].append(m["email"])
    for g in groups:
        g["members"] = by_gid[g["id"]]
    return groups


def create_group(name: str) -> int:
    name = (name or "").strip()
    if not name:
        raise ValueError("组名不能为空")
    if get_conn().execute("SELECT 1 FROM contact_groups WHERE name = ?", (name,)).fetchone():
        raise ValueError("同名联系组已存在")
    cur = get_conn().execute("INSERT INTO contact_groups (name) VALUES (?)", (name,))
    get_conn().commit()
    return int(cur.lastrowid)


def rename_group(group_id: int, name: str) -> None:
    name = (name or "").strip()
    if not name:
        raise ValueError("组名不能为空")
    if get_conn().execute(
        "SELECT 1 FROM contact_groups WHERE name = ? AND id != ?", (name, group_id)
    ).fetchone():
        raise ValueError("同名联系组已存在")
    get_conn().execute("UPDATE contact_groups SET name = ? WHERE id = ?", (name, group_id))
    get_conn().commit()


def delete_group(group_id: int) -> None:
    get_conn().execute("DELETE FROM contact_groups WHERE id = ?", (group_id,))
    get_conn().commit()  # 成员行随 ON DELETE CASCADE 级联清除


def set_members(group_id: int, emails: list[str], *, add: bool) -> int:
    """按 email 增/删组成员（规范化去重；新增时跳过通讯录中不存在的地址）。"""
    normed: list[str] = []
    for e in emails:
        e = norm_email(e)
        if e and e not in normed:
            normed.append(e)
    conn = get_conn()
    n = 0
    for e in normed:
        if add:
            if conn.execute("SELECT 1 FROM contacts WHERE email = ?", (e,)).fetchone() is None:
                continue
            if conn.execute(
                "SELECT 1 FROM contact_group_members WHERE group_id = ? AND email = ?",
                (group_id, e),
            ).fetchone():
                continue
            conn.execute(
                "INSERT INTO contact_group_members (group_id, email) VALUES (?, ?)",
                (group_id, e),
            )
        else:
            cur = conn.execute(
                "DELETE FROM contact_group_members WHERE group_id = ? AND email = ?",
                (group_id, e),
            )
            n += cur.rowcount
            continue
        n += 1
    conn.commit()
    return n


def cleanup_members() -> None:
    """联系人删净后清理组内孤儿成员行（删除联系人时调用）。"""
    get_conn().execute(
        "DELETE FROM contact_group_members WHERE email NOT IN (SELECT email FROM contacts)"
    )
    get_conn().commit()
