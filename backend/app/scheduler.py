"""后台轮询调度器。

每 60 秒 tick 一次，检查各账号是否到达轮询间隔（settings.poll_interval_minutes），
到期则增量同步 INBOX。用"检查到期"而非"每账号注册定时任务"，
修改轮询间隔设置后无需重建调度。
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler

from app.core.sync import sync_account
from app.db.database import get_conn, get_setting

logger = logging.getLogger(__name__)

TICK_SECONDS = 60


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def poll_due_accounts() -> None:
    interval_minutes = int(get_setting("poll_interval_minutes", 5) or 5)
    now = datetime.now(timezone.utc)
    rows = get_conn().execute("SELECT * FROM accounts ORDER BY id").fetchall()
    for row in rows:
        last = _parse_iso(row["last_sync_at"])
        if last is not None and now - last < timedelta(minutes=interval_minutes):
            continue
        try:
            result = sync_account({
                "id": row["id"],
                "email": row["email"],
                "imap_server": row["imap_server"],
                "imap_port": row["imap_port"],
            })
            if not result["ok"]:
                logger.info("poll sync failed for %s: %s", row["email"], result.get("error"))
        except Exception:  # noqa: BLE001 — 单账号失败不影响其他账号
            logger.exception("poll sync crashed for %s", row["email"])


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
        try:
            self._scheduler.shutdown(wait=False)
        except Exception:  # noqa: BLE001
            pass
