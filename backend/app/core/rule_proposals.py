"""手动整理观察 → 发件人黑名单规则提议（REDESIGN_PLAN §18.5 规则提议）。

观察用户手动归档/删除动作（core/batch_ops 任务体回写后调用 observe）；同一
发件人 14 天内累计 ≥PROPOSE_THRESHOLD 次 → 生成 pending 提议。去重边界：
pattern 已在白/黑名单、或已有 pending/rejected 提议时不再提（rejected=用户
明确拒绝过，防骚扰）；pending 提议设上限。批准/拒绝由 api 层 decide 处理
（批准走 sender_lists 既有管线，不引入规则引擎，守产品决策 #3）。
"""
from __future__ import annotations

from app.core.sync import add_notification
from app.db.database import get_conn

PROPOSE_THRESHOLD = 3
WINDOW_DAYS = 14
MAX_PENDING = 5


def observe(emails: list[dict], action: str) -> None:
    """记录一次手动整理观察（archive/trash），达阈值则生成提议。

    emails: [{id, account_id, sender_email}]（batch_ops 已快照 sender——trash
    会删本地行，必须在执行前取好）。
    """
    if action not in ("archive", "trash") or not emails:
        return
    conn = get_conn()
    for r in emails:
        sender = str(r.get("sender_email") or "").strip().lower()
        if sender and "@" in sender:
            conn.execute(
                "INSERT OR IGNORE INTO rule_observations (email_id, account_id, sender_email, action)"
                " VALUES (?, ?, ?, ?)",
                (r["id"], r.get("account_id"), sender, action),
            )
    conn.commit()
    propose()


def propose() -> None:
    """按观察生成 pending 提议（幂等；GET 列表时懒触发兜底）。"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT sender_email, COUNT(*) n FROM rule_observations"
        " WHERE created_at >= datetime('now', ?)"
        " GROUP BY sender_email HAVING n >= ? ORDER BY n DESC",
        (f"-{WINDOW_DAYS} days", PROPOSE_THRESHOLD),
    ).fetchall()
    for r in rows:
        pattern = r["sender_email"]
        known = conn.execute(
            "SELECT 1 FROM sender_lists WHERE pattern = ?"
            " UNION ALL SELECT 1 FROM agent_proposals WHERE pattern = ?"
            " AND status IN ('pending', 'rejected')",
            (pattern, pattern),
        ).fetchone()
        if known:
            continue
        pending_n = conn.execute(
            "SELECT COUNT(*) n FROM agent_proposals WHERE status = 'pending'"
        ).fetchone()["n"]
        if pending_n >= MAX_PENDING:
            return
        sample = conn.execute(
            "SELECT subject FROM emails WHERE sender_email = ? ORDER BY id DESC LIMIT 3",
            (pattern,),
        ).fetchall()
        conn.execute(
            "INSERT INTO agent_proposals (pattern, evidence_count, sample_subjects)"
            " VALUES (?, ?, ?)",
            (pattern, r["n"], "；".join(str(s["subject"] or "")[:30] for s in sample)),
        )
        conn.commit()
        add_notification(
            "ai_proposal",
            "AI 规则提议",
            f"「{pattern}」近 {WINDOW_DAYS} 天被你手动整理 {r['n']} 次——到 设置-AI 用量-规则提议 采纳或忽略",
        )
