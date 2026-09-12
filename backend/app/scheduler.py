"""后台轮询调度器。

每 60 秒 tick 一次：
- 检查各账号是否到达轮询间隔（settings.poll_interval_minutes），到期则增量同步 INBOX；
- 检查每日摘要（settings.digest_time）当天是否已到点且未生成，到点则生成。
"""
from __future__ import annotations

import logging
from contextlib import suppress
from datetime import datetime, timedelta, UTC

from apscheduler.schedulers.background import BackgroundScheduler

from app.core.outbox import send_user_draft
from app.core.sync import start_sync
from app.db.database import get_conn, get_setting

logger = logging.getLogger(__name__)

TICK_SECONDS = 60


def _digest_due() -> bool:
    target = str(get_setting("digest_time", "08:30") or "08:30")
    try:
        target_h, target_m = (int(x) for x in target.split(":"))
    except ValueError:
        return False
    now = datetime.now()
    if (now.hour, now.minute) < (target_h, target_m):
        return False
    row = get_conn().execute(
        "SELECT 1 FROM digest_history WHERE date = ?", (now.date().isoformat(),)
    ).fetchone()
    return not row


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt
    except ValueError:
        return None


def _notify(title: str, body: str) -> None:
    get_conn().execute(
        "INSERT INTO notifications (type, title, body) VALUES ('compose', ?, ?)",
        (title, body),
    )
    get_conn().commit()


def send_due_drafts() -> None:
    """定时发送到期草稿；成功/失败均写通知，失败退回编辑态。"""
    rows = get_conn().execute(
        "SELECT id, subject, to_addrs, send_at FROM user_drafts"
        " WHERE status = 'scheduled' AND send_at IS NOT NULL"
    ).fetchall()
    now = datetime.now()
    for row in rows:
        try:
            due = datetime.fromisoformat(row["send_at"])
        except ValueError:
            due = None
        if due is None or due > now:
            continue
        try:
            send_user_draft(row["id"])
            _notify("定时邮件已发送", f"「{row['subject'] or '（无主题）'}」已按计划发出")
            logger.info("scheduled draft %s sent", row["id"])
        except Exception as exc:  # noqa: BLE001 — 单封失败不阻塞其他定时任务
            get_conn().execute(
                "UPDATE user_drafts SET status = 'editing', send_at = NULL,"
                " updated_at = datetime('now') WHERE id = ?",
                (row["id"],),
            )
            get_conn().commit()
            _notify("定时发送失败，草稿已退回写信台", f"「{row['subject'] or '（无主题）'}」：{exc}")
            logger.exception("scheduled draft %s failed", row["id"])


def expire_stale_actions() -> int:
    """审批动作 24h 未处理自动过期（REDESIGN_PLAN §6.5；审查 U2：原先 pending 永久挂起）。

    created_at 为 SQLite datetime('now')（UTC），边界用同源表达式比较；每次 tick
    顺带执行（pending 量小，无索引也足够快）。
    """
    conn = get_conn()
    cur = conn.execute(
        "UPDATE ai_actions SET status = 'expired',"
        " error = '超过 24 小时未处理，自动过期', decided_at = ?"
        " WHERE status = 'pending' AND created_at <= datetime('now', '-24 hours')",
        (datetime.now().isoformat(timespec="seconds"),),
    )
    conn.commit()
    if cur.rowcount:
        logger.info("expired %s stale pending ai_actions", cur.rowcount)
    return cur.rowcount


def poll_due_accounts() -> None:
    interval_minutes = int(get_setting("poll_interval_minutes", 5) or 5)
    now = datetime.now(UTC)
    rows = get_conn().execute("SELECT * FROM accounts ORDER BY id").fetchall()
    for row in rows:
        last = _parse_iso(row["last_sync_at"])
        if last is not None and now - last < timedelta(minutes=interval_minutes):
            continue
        try:
            # 后台线程执行：长同步（如首翻大邮箱）不再阻塞调度 tick
            result = start_sync({
                "id": row["id"],
                "email": row["email"],
                "imap_server": row["imap_server"],
                "imap_port": row["imap_port"],
            })
            if not result["started"] and result.get("reason") != "syncing":
                logger.info("poll sync not started for %s: %s", row["email"], result.get("reason"))
        except Exception:  # noqa: BLE001 — 单账号失败不影响其他账号
            logger.exception("poll sync crashed for %s", row["email"])

    try:
        send_due_drafts()
    except Exception:  # noqa: BLE001
        logger.exception("scheduled draft dispatch crashed")

    try:
        expire_stale_actions()
    except Exception:  # noqa: BLE001
        logger.exception("ai_actions expiry scan crashed")

    if _digest_due():
        try:
            from app.ai.digest import build_digest

            build_digest()
            logger.info("daily digest generated")
        except Exception:  # noqa: BLE001
            logger.exception("digest generation failed")


class MailScheduler:
    def __init__(self) -> None:
        self._scheduler = BackgroundScheduler()

    def start(self) -> None:
        self._scheduler.add_job(
            poll_due_accounts,
            "interval",
            seconds=TICK_SECONDS,
            id="mail_poll",
            max_instances=1,
            coalesce=True,
        )
        self._scheduler.start()
        logger.info("mail scheduler started (tick %ss)", TICK_SECONDS)

    def shutdown(self) -> None:
        with suppress(Exception):
            self._scheduler.shutdown(wait=False)
