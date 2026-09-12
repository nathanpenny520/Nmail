"""通讯录（v0.4 P4，REDESIGN_PLAN §5.3）：往来联系人自动采集与写信联想。

采集零操作：收信入库采集发件人、发送成功采集收件人（upsert，use_count 计数、
last_seen_at 刷新）；手动编辑过的行（source=manual）不被自动覆盖，仅累计计数。
account_id 作用域：每账号各自的往来（UNIQUE(COALESCE(account_id,0), email)），
手动新增为全局（account_id NULL）；联想时全局查（跨账号去重取最优行）。
"""
from __future__ import annotations

import re

from app.db.database import get_conn

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def norm_email(email: str) -> str:
    return (email or "").strip().lower()


def split_addresses(raw: str) -> list[str]:
    """逗号分隔的地址串 → 规范化列表（去空）。"""
    return [p for p in (norm_email(x) for x in (raw or "").split(",")) if p]


def collect_addresses(raw: str, account_id: int | None) -> int:
    """从逗号分隔地址串采集全部联系人（发送侧 To/Cc/Bcc，支持「Name <a@x>」）。"""
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
