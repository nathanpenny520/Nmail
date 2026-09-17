"""每日摘要生成。

统计部分零成本（本地 SQL + Python 分桶，`build_digest` 不调 LLM）；AI 摘要正文
由 agent 运行产出、经 `store_brief` 落同一天的 `agent_brief` 键（§18.6）。
"""
from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import date, datetime, timedelta

from app.ai.categories import CATEGORY_ORDER as CATEGORIES
from app.core.sync import add_notification
from app.db.database import get_conn

logger = logging.getLogger(__name__)


def _to_local_dt(iso: str | None) -> datetime | None:
    """ISO 日期 → 本地时区 datetime。naive 视为本地时间——与 sync._norm_date 的
    `astimezone(UTC)` 归一化假设一致（审查 F5：原先按 UTC 解释，两处假设相反）。
    """
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso).astimezone()
    except (ValueError, OSError, OverflowError):
        # Windows 上极值年份的本地时区换算抛 OSError [Errno 22]，畸形日期不参与摘要
        return None


def _collect_stats() -> dict:
    conn = get_conn()
    now_local = datetime.now().astimezone()
    today = now_local.date()
    week_ago = today - timedelta(days=6)

    rows = conn.execute(
        "SELECT e.id, e.account_id, e.subject, e.sender_name, e.sender_email, e.date,"
        " COALESCE(e.date_sort, e.date) AS date_key,"
        " e.is_read, e.archived_local, e.category, e.importance, e.needs_reply, e.reply_reason,"
        " a.email AS account_email, a.color AS account_color"
        " FROM emails e JOIN accounts a ON a.id = e.account_id"
        " WHERE COALESCE(e.date_sort, e.date) >= ? OR e.date IS NULL"
        " ORDER BY date_key DESC",
        ((week_ago - timedelta(days=1)).isoformat(),),
    ).fetchall()

    new_today = unread = auto_archived_today = 0
    by_category: Counter = Counter()
    trend: Counter = Counter()
    by_account: dict[int, dict] = {}
    for row in rows:
        dt = _to_local_dt(row["date"])
        account = by_account.setdefault(row["account_id"], {
            "email": row["account_email"],
            "color": row["account_color"],
            "count": 0,
            "unread": 0,
        })
        if not row["is_read"] and not row["archived_local"]:
            unread += 1
            account["unread"] += 1
        if row["archived_local"] and row["category"] == "promo":
            auto_archived_today += 1
        if dt and dt.date() == today:
            new_today += 1
            account["count"] += 1
            if row["category"]:
                by_category[row["category"]] += 1
        if dt and week_ago <= dt.date() <= today and not row["archived_local"]:
            trend[dt.date().isoformat()] += 1

    # 需要回复（未归档、未回复过）：已发送草稿视为已回复
    # v0.4 P3 后草稿统一走 user_drafts（旧 drafts 表已退役只读），in_reply_to 指向被回复邮件
    sent_ids = {
        r["in_reply_to"] for r in conn.execute(
            "SELECT DISTINCT in_reply_to FROM user_drafts"
            " WHERE status = 'sent' AND in_reply_to IS NOT NULL"
        ).fetchall()
    }
    need_reply = []
    important = []
    for row in rows:
        if row["archived_local"]:
            continue
        item = {
            "email_id": row["id"],
            "subject": row["subject"],
            "sender": row["sender_name"] or row["sender_email"],
            "date": row["date"],
            "date_key": row["date_key"] or "",
        }
        if row["needs_reply"] and row["id"] not in sent_ids:
            need_reply.append({**item, "reason": row["reply_reason"] or "", "has_draft": _has_draft(row["id"])})
        if row["importance"] in ("critical", "high") and row["category"] != "promo":
            important.append({**item, "category": row["category"], "importance": row["importance"],
                              "reason": row["reply_reason"] or ""})

    # critical 优先、组内最新在前（原升序把最新一封排最后，审查 F7）
    important.sort(key=lambda x: (x["importance"] == "critical", x["date_key"] or ""), reverse=True)

    return {
        "date": today.isoformat(),
        "overview": {
            "new_today": new_today,
            "unread": unread,
            "auto_archived": auto_archived_today,
            "need_reply": len(need_reply),
        },
        "by_category": {c: by_category.get(c, 0) for c in CATEGORIES},
        "trend": [
            {"day": (week_ago + timedelta(days=i)).isoformat(),
             "count": trend.get((week_ago + timedelta(days=i)).isoformat(), 0)}
            for i in range(7)
        ],
        "by_account": list(by_account.values()),
        "need_reply": need_reply[:20],
        "important": important[:10],
    }


def _has_draft(email_id: int) -> bool:
    row = get_conn().execute(
        "SELECT 1 FROM user_drafts WHERE in_reply_to = ?"
        " AND status IN ('pending_review','sent') LIMIT 1",
        (email_id,),
    ).fetchone()
    return bool(row)


def build_digest(force: bool = False) -> dict:
    """统计摘要（纯本地零 LLM）：开关关闭时的每日内容，也是 AI 摘要失败/无产出时的回退。

    同日重建保留用户手动清除的重要邮件记录（✕ 掉的不复活，跨天自然重置）与
    已存的 AI 摘要正文——晚间手动重跑崩溃回退时不抹掉晨间正文。
    """
    today = date.today().isoformat()
    conn = get_conn()
    existing = conn.execute(
        "SELECT content_json FROM digest_history WHERE date = ?", (today,)
    ).fetchone()
    stats = _collect_stats()
    if existing:
        old = json.loads(existing["content_json"])
        dismissed = set(old.get("dismissed_important") or [])
        if dismissed:
            stats["important"] = [i for i in stats["important"] if i["email_id"] not in dismissed]
            stats["dismissed_important"] = sorted(dismissed)
        if old.get("agent_brief"):
            stats["agent_brief"] = old["agent_brief"]
    conn.execute(
        "INSERT INTO digest_history (date, content_json) VALUES (?, ?)"
        " ON CONFLICT(date) DO UPDATE SET content_json = excluded.content_json,"
        " created_at = datetime('now')",
        (today, json.dumps(stats, ensure_ascii=False)),
    )
    conn.commit()
    add_notification("digest", "今日邮件摘要已生成", "到「每日摘要」页查看", today)
    return stats


def store_brief(brief_text: str) -> dict:
    """AI 摘要正文落摘要页（§18.6）：结构化统计照常收集，正文存独立键
    agent_brief——摘要页单独的「AI 摘要」区块呈现（当天不再有其他 AI 文字段）。
    agent 拟的草稿经 has_draft 自然出现在「需要回复」。
    通知由调用方负责：scheduler/手动触发发；对话 save_brief 不发（用户在场）。
    """
    today = date.today().isoformat()
    conn = get_conn()
    existing = conn.execute(
        "SELECT content_json FROM digest_history WHERE date = ?", (today,)
    ).fetchone()
    stats = _collect_stats()
    # 与 build_digest 同规则：保留用户手动清除的重要邮件记录，不让 ✕ 掉的复活
    if existing:
        dismissed = set(json.loads(existing["content_json"]).get("dismissed_important") or [])
        if dismissed:
            stats["important"] = [i for i in stats["important"] if i["email_id"] not in dismissed]
            stats["dismissed_important"] = sorted(dismissed)
    stats["agent_brief"] = brief_text
    conn.execute(
        "INSERT INTO digest_history (date, content_json) VALUES (?, ?)"
        " ON CONFLICT(date) DO UPDATE SET content_json = excluded.content_json,"
        " created_at = datetime('now')",
        (today, json.dumps(stats, ensure_ascii=False)),
    )
    conn.commit()
    return stats
