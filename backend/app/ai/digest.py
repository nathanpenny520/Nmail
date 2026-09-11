"""每日摘要生成。

统计部分零成本（本地 SQL + Python 分桶）；AI 只写一段综述，未配置 AI 时摘要依然可用。
"""
from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import date, datetime, timedelta, timezone

from app.ai import tasks
from app.core.sync import add_notification
from app.db.database import get_conn

logger = logging.getLogger(__name__)

CATEGORIES = ("work", "personal", "notification", "verification", "promo", "social")


def _to_local_dt(iso: str | None) -> datetime | None:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone()
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
    sent_ids = {
        r["email_id"] for r in conn.execute(
            "SELECT DISTINCT email_id FROM drafts WHERE status = 'sent'"
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

    important.sort(key=lambda x: (x["importance"] != "critical", x["date_key"]), reverse=False)

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
        "SELECT 1 FROM drafts WHERE email_id = ? AND status IN ('pending','sent') LIMIT 1",
        (email_id,),
    ).fetchone()
    return bool(row)


def _ai_overview(stats: dict) -> str:
    lines = [f"今日新邮件 {stats['overview']['new_today']} 封，未读 {stats['overview']['unread']} 封，"
             f"自动归档营销 {stats['overview']['auto_archived']} 封。"]
    if stats["by_category"]:
        cats = "、".join(f"{k} {v} 封" for k, v in stats["by_category"].items() if v)
        lines.append(f"分类分布：{cats}。")
    if stats["need_reply"]:
        lines.append("需要回复：" + "；".join(
            f"{i['sender']}的「{i['subject'][:30]}」（{i['reason'][:20]}）" for i in stats["need_reply"][:5]))
    if stats["important"]:
        lines.append("重要邮件：" + "；".join(
            f"「{i['subject'][:30]}」" for i in stats["important"][:5]))
    user = "以下是今日邮箱统计数据，请写一段 3-5 句的中文每日综述，突出最需要用户注意的事（验证码、账单、截止日期、重要来信）。只输出综述本身。\n\n" + "\n".join(lines)
    try:
        return tasks.digest_overview(user)
    except Exception as exc:  # noqa: BLE001 — 综述失败不影响结构化摘要
        logger.warning("digest ai overview failed: %s", exc)
        return ""


def build_digest(force: bool = False) -> dict:
    today = date.today().isoformat()
    conn = get_conn()
    if not force:
        existing = conn.execute(
            "SELECT content_json FROM digest_history WHERE date = ?", (today,)
        ).fetchone()
        if existing:
            return json.loads(existing["content_json"])

    stats = _collect_stats()
    stats["ai_overview"] = _ai_overview(stats)
    conn.execute(
        "INSERT INTO digest_history (date, content_json) VALUES (?, ?)"
        " ON CONFLICT(date) DO UPDATE SET content_json = excluded.content_json,"
        " created_at = datetime('now')",
        (today, json.dumps(stats, ensure_ascii=False)),
    )
    conn.commit()
    add_notification("digest", "今日邮件摘要已生成", "到「每日摘要」页查看", today)
    return stats
