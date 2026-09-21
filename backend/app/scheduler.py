"""后台轮询调度器。

每 60 秒 tick 一次：
- 检查各账号是否到达轮询间隔（settings.poll_interval_minutes），到期则增量同步 INBOX；
- 检查每日摘要（settings.digest_time）当天是否已到点且未生成，到点则生成统计摘要；
- AI 摘要（settings.agent_brief_enabled，§18.6）：开启时到点改由调度触发一次
  agent 定时运行（工具白名单硬边界），替代统计摘要——产出通知+草稿进待审列表；
  也可由摘要页/对话随时手动触发（start_daily_brief，互斥锁防叠加）。
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
from app.core.update_apply import auto_update_tick
from app.db.database import get_conn, get_setting, set_setting

logger = logging.getLogger(__name__)

TICK_SECONDS = 60

# AI 摘要固定指令（§18.6）：写动作只有拟稿/本地标记（白名单硬边界在 agent 循环），
# 草稿一律进待审列表等用户确认，绝不直接发送
SCHEDULER_BRIEF_QUESTION = (
    "这是每日定时摘要任务（无人值守自动运行）：请检查各账号今天以来的未读邮件，"
    "按重要性总结要点；对明显需要回复的邮件直接调用 create_draft 拟好回复草稿"
    "（会进入待审列表，由用户确认后才发送，你不能发送）；可用 set_category 标记"
    "重要性或需要回复。不要执行其他写操作。最后用简洁的中文输出 AI 摘要正文。"
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
    """AI 摘要开关 + 到点判断（§18.6）：复用 digest_time；当天未跑过才触发。

    与统计摘要互斥（开启即替代）；当天触发标记走 KV agent_brief_last_run
    （定时与手动触发都盖章，手动跑过当天定时不再重跑），不占 digest_history
    （关闭开关后统计摘要照常按 digest_history 判断）。
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


# 手动/定时触发互斥：进程内标志（重启自然清零，无 KV 残留卡死风险）+ 锁
_brief_running = False
_brief_lock = threading.Lock()


def brief_running() -> bool:
    """AI 摘要 agent 是否正在运行（前端按钮态/接口 409 判断用）。"""
    return _brief_running


def start_daily_brief(origin: str) -> bool:
    """触发一次 AI 摘要 agent 运行（定时/摘要页/对话共用入口）。

    已在运行返回 False（不叠加、不盖章——运行方结束时自己盖章/已盖）。
    独立线程执行（180s 预算不阻塞调度 tick），origin 落 agent 操作记录。
    """
    global _brief_running
    with _brief_lock:
        if _brief_running:
            return False
        _brief_running = True
        set_setting("agent_brief_last_run", datetime.now().date().isoformat())
    threading.Thread(target=_run_daily_brief, args=(origin,), daemon=True,
                     name="agent-brief").start()
    return True


def _run_daily_brief(origin: str = "scheduler") -> None:
    """AI 摘要运行体（独立线程，避免 180s 预算阻塞调度 tick）。

    origin（scheduler/manual）落操作记录；SCHEDULER_ALLOWED 工具白名单是硬边界——
    send/trash/move 等即使 auto 模式也不可用；草稿只进待审列表。
    成功后摘要文本经 digest.store_brief 写入「每日摘要」页当日内容
    （结构化统计照常）——AI 摘要是摘要页唯一的 AI 文字段；
    运行失败或无产出时回退统计版 build_digest，保证当天内容不缺席。
    """
    global _brief_running
    try:
        from app.ai import agent as ai_agent
        from app.ai.digest import build_digest, store_brief

        account_ids = [r["id"] for r in
                       get_conn().execute("SELECT id FROM accounts ORDER BY id").fetchall()]
        if not account_ids:
            return
        events = list(ai_agent.run_stream(
            SCHEDULER_BRIEF_QUESTION, None, None, account_ids, "auto", None,
            origin=origin, allowed_tools=ai_agent.SCHEDULER_ALLOWED))
        text = "".join(e.get("text", "") for e in events if e.get("type") == "text").strip()
        if text:
            store_brief(text)
            # 通知是纯文本（Notification API 平台限制，无法渲染 markdown）——
            # 先 md→plain 清理再截短；完整排版站内看（摘要页渲染 markdown）
            from app.core.mail_html import markdown_to_plain_text

            plain = markdown_to_plain_text(text)
            if len(plain) > 500:
                plain = plain[:500].rstrip() + "…"
            add_notification("digest", "AI 摘要已生成",
                             plain + "\n\n—— 拟好的回复草稿在待审列表；点击前往「每日摘要」页看完整排版")
            logger.info("agent daily brief finished (origin=%s, chars=%d)", origin, len(text))
        else:
            # 无产出（步数/预算触顶等）：回退统计摘要，当天内容不缺席
            build_digest()
            add_notification("digest", "AI 摘要未产出，已生成统计摘要",
                             "详见 设置-AI 用量-操作记录；可在「每日摘要」页重新生成")
            logger.info("agent daily brief empty, fallback stats digest (origin=%s)", origin)
    except Exception:  # noqa: BLE001 — 定时任务失败不影响调度循环
        logger.exception("agent daily brief crashed")
        try:
            from app.ai.digest import build_digest

            build_digest()
            add_notification("digest", "AI 摘要失败，已生成统计摘要",
                             "AI 摘要运行出错（详见 操作记录）；可在「每日摘要」页重新生成")
        except Exception:  # noqa: BLE001
            logger.exception("fallback digest after brief crash also failed")
            add_notification("digest", "AI 摘要失败",
                             "AI 摘要与统计摘要均生成失败，详见日志与 设置-AI 用量-操作记录")
    finally:
        with _brief_lock:
            _brief_running = False


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
    """定时发送到期草稿；成功/失败均写通知，失败退回编辑态。

    发送前跑 precheck（S-0921）：规则层 blocker 不发出、退回编辑态并通知；
    AI 深审按设置开关叠加（失败降级仅规则层，不打断发送）。
    """
    from app.core import precheck

    rows = get_conn().execute(
        "SELECT id, subject, to_addrs, send_at, body_html FROM user_drafts"
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
            blockers = [i for i in precheck.draft_rule_issues(row["id"], row)
                        if i["severity"] == "blocker"]
            if blockers:
                get_conn().execute(
                    "UPDATE user_drafts SET status = 'editing', send_at = NULL,"
                    " updated_at = datetime('now') WHERE id = ?",
                    (row["id"],),
                )
                get_conn().commit()
                _notify("定时邮件未发出，草稿已退回写信台",
                        f"「{row['subject'] or '（无主题）'}」发送前检查未通过："
                        + "；".join(i["message"] for i in blockers))
                logger.info("scheduled draft %s blocked by precheck", row["id"])
                continue
            # AI 深审（可选）：开关默认开，未配置/失败降级为仅规则层结果
            if get_setting("ai_send_review", True):
                try:
                    from app.ai import tasks as ai_tasks
                    from app.core.mail_html import html_to_plain_text

                    names = [r["filename"] for r in get_conn().execute(
                        "SELECT filename FROM user_draft_attachments WHERE draft_id = ?"
                        " ORDER BY id", (row["id"],)).fetchall()]
                    review = ai_tasks.review_send_draft(
                        row["subject"] or "", html_to_plain_text(row["body_html"] or ""), names)
                    if review["blockers"]:
                        get_conn().execute(
                            "UPDATE user_drafts SET status = 'editing', send_at = NULL,"
                            " updated_at = datetime('now') WHERE id = ?",
                            (row["id"],),
                        )
                        get_conn().commit()
                        _notify("定时邮件未发出，草稿已退回写信台",
                                f"「{row['subject'] or '（无主题）'}」AI 审查发现问题："
                                + "；".join(review["blockers"][:3]))
                        logger.info("scheduled draft %s blocked by ai review", row["id"])
                        continue
                except Exception:  # noqa: BLE001 — AI 深审不可用不阻塞发送
                    logger.exception("ai send review failed for draft %s", row["id"])
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
    from app.db.database import reap_dead_thread_conns

    try:
        reap_dead_thread_conns()
    except Exception:  # noqa: BLE001 — 回收失败不影响本轮轮询
        logger.exception("dead-thread conn reaper crashed")

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
            # 其余文件夹的历史回补由独立回补线程负责（sync.maybe_start_backfill，
            # EXPERIENCE_PLAN B1）；轮询不扩展到全部文件夹——高频访问的仍是 INBOX。
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
        # AI 摘要（§18.6）：start_daily_brief 内盖章+置运行标志防 60s tick 重复触发
        start_daily_brief("scheduler")
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
        # 自动更新心跳（UPDATE_AND_DESKTOP.md §3.3）：检查侧自带 24h 缓存节流，
        # 每小时问一次只为兜底长驻进程；不可自更新渠道与关闭开关时内部直返
        self._scheduler.add_job(
            auto_update_tick,
            "interval",
            hours=1,
            id="update_tick",
            max_instances=1,
            coalesce=True,
        )
        self._scheduler.start()
        logger.info("mail scheduler started (tick %ss)", TICK_SECONDS)

    def shutdown(self) -> None:
        with suppress(Exception):
            self._scheduler.shutdown(wait=False)
