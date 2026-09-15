"""后台轮询调度器。

每 60 秒 tick 一次：
- 检查各账号是否到达轮询间隔（settings.poll_interval_minutes），到期则增量同步 INBOX；
- 检查每日摘要（settings.digest_time）当天是否已到点且未生成，到点则生成；
- AI 晨报（settings.agent_brief_enabled，§18.6）：开启时到点改由调度触发一次
  agent 定时运行（工具白名单硬边界），替代每日摘要——产出通知+草稿进待审列表。
"""
from __future__ import annotations

import logging
import threading
from contextlib import suppress
from datetime import datetime, timedelta, UTC

from apscheduler.schedulers.background import BackgroundScheduler

from app.core.folders import archive_folder_name
from app.core.outbox import send_user_draft
from app.core.sync import add_notification, start_sync
from app.db.database import get_conn, get_setting, set_setting

logger = logging.getLogger(__name__)

TICK_SECONDS = 60

# AI 晨报固定指令（§18.6）：写动作只有拟稿/本地标记（白名单硬边界在 agent 循环），
# 草稿一律进待审列表等用户确认，绝不直接发送
SCHEDULER_BRIEF_QUESTION = (
    "这是每日定时晨报任务（无人值守自动运行）：请检查各账号今天以来的未读邮件，"
    "按重要性总结要点；对明显需要回复的邮件直接调用 create_draft 拟好回复草稿"
    "（会进入待审列表，由用户确认后才发送，你不能发送）；可用 set_category 标记"
    "重要性或需要回复。不要执行其他写操作。最后用简洁的中文输出晨报正文。"
)


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


def _brief_enabled_and_due() -> bool:
    """AI 晨报开关 + 到点判断（§18.6）：复用 digest_time；当天未跑过才触发。

    与每日摘要互斥（开启即替代）；当天触发标记走 KV agent_brief_last_run，
    不占 digest_history（关闭开关后摘要照常按 digest_history 判断）。
    """
    if not bool(get_setting("agent_brief_enabled", False)):
        return False
    target = str(get_setting("digest_time", "08:30") or "08:30")
    try:
        target_h, target_m = (int(x) for x in target.split(":"))
    except ValueError:
        return False
    now = datetime.now()
    if (now.hour, now.minute) < (target_h, target_m):
        return False
    return str(get_setting("agent_brief_last_run", "")) != now.date().isoformat()


def _run_daily_brief() -> None:
    """AI 晨报运行体（独立线程，避免 180s 预算阻塞调度 tick）。

    origin=scheduler 落操作记录；SCHEDULER_ALLOWED 工具白名单是硬边界——
    send/trash/move 等即使 auto 模式也不可用；草稿只进待审列表。
    成功后晨报文本经 digest.store_agent_brief 写入「每日摘要」页当日内容
    （结构化统计照常，AI 综述=晨报正文）——晨报是摘要的 AI 形态而非并行物；
    运行失败或无产出时回退旧版 build_digest，保证当天摘要不缺席。
    """
    try:
        from app.ai import agent as ai_agent
        from app.ai.digest import build_digest, store_agent_brief

        account_ids = [r["id"] for r in
                       get_conn().execute("SELECT id FROM accounts ORDER BY id").fetchall()]
        if not account_ids:
            return
        events = list(ai_agent.run_stream(
            SCHEDULER_BRIEF_QUESTION, None, None, account_ids, "auto", None,
            origin="scheduler", allowed_tools=ai_agent.SCHEDULER_ALLOWED))
        text = "".join(e.get("text", "") for e in events if e.get("type") == "text").strip()
        if text:
            store_agent_brief(text)
            # 通知正文带晨报全文（通知中心可展开阅读；跳转去摘要页看完整排版）
            add_notification("digest", "AI 晨报已生成",
                             text[:2000] + "\n\n—— 拟好的回复草稿在待审列表；点击前往「每日摘要」页")
            logger.info("agent daily brief finished (chars=%d)", len(text))
        else:
            # 无产出（步数/预算触顶等）：回退旧版摘要，当天内容不缺席
            build_digest()
            add_notification("digest", "AI 晨报未产出，已回退每日摘要",
                             "详见 设置-AI 用量-操作记录；今日摘要按常规生成")
            logger.info("agent daily brief empty, fallback digest generated")
    except Exception:  # noqa: BLE001 — 定时任务失败不影响调度循环
        logger.exception("agent daily brief crashed")
        try:
            from app.ai.digest import build_digest

            build_digest()
            add_notification("digest", "AI 晨报失败，已回退每日摘要",
                             "晨报运行出错（详见 操作记录）；今日摘要按常规生成")
        except Exception:  # noqa: BLE001
            logger.exception("fallback digest after brief crash also failed")
            add_notification("digest", "AI 晨报失败",
                             "晨报与摘要均生成失败，详见日志与 设置-AI 用量-操作记录")


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
            # 轮询 = INBOX + 归档文件夹（仅当该账号缓存里已有此文件夹——从未归档过
            # 的账号服务器上还没有它，带上只会报错）。归档是真实服务器移动，归档夹
            # 不进轮询时，移动后删行重建的邮件要等手动同步才可见。
            # 其余文件夹仍按需同步（界面点开/POST /folders/sync），全量轮询不值得：
            # 每文件夹一次 SELECT 的开销换不来高频访问。
            archive = archive_folder_name(row["id"])
            known = get_conn().execute(
                "SELECT 1 FROM folders WHERE account_id = ? AND name = ?", (row["id"], archive)
            ).fetchone()
            poll_folders = ("INBOX", archive) if known else ("INBOX",)
            # 后台线程执行：长同步（如首翻大邮箱）不再阻塞调度 tick
            result = start_sync({
                "id": row["id"],
                "email": row["email"],
                "imap_server": row["imap_server"],
                "imap_port": row["imap_port"],
            }, folders=poll_folders)
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

    if _brief_enabled_and_due():
        # AI 晨报（§18.6）：先落当天标记防 60s tick 重复触发，线程内跑 agent
        set_setting("agent_brief_last_run", datetime.now().date().isoformat())
        threading.Thread(target=_run_daily_brief, daemon=True, name="agent-brief").start()
    elif _digest_due():
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
