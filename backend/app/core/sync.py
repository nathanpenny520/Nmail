"""UID 增量同步引擎。

- 分块断点续拉：UID 升序每 ~25 封一块，每块入库即提交断点（见 imap_client.iter_new_mail），
  中断/失败后从断点续传，不再整批重放；
- 同步在后台线程执行（start_sync），进度写账号 status/status_detail，前端轮询可见；
- 首翻全量（EXPERIENCE_PLAN B1）：首同步只拉最新一页立即可用，更早历史由回补线程
  （maybe_start_backfill → _backfill_worker）从新到旧分块补齐全部文件夹；
  回补邮件不进 AI 流水线、不发通知、不采通讯录；
- UIDVALIDITY 变化时清空该文件夹本地数据并重新首次同步；
- 附件落盘到数据目录，元数据入库；
- 登录失败标记账号 auth_error 并发一次通知（授权码失效提醒）；
- 网络类瞬时错误自动重试一次（断点已在，重试成本仅为剩余部分）。
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
from datetime import datetime, UTC


from imap_tools.errors import MailboxLoginError

from app.core import imap_client, mailbox
from app.core.imap_client import get_uidvalidity, iter_new_mail
from app.core.mail_html import count_remote_images
from app.config import get_data_dir
from app.db.database import close_thread_conn, get_conn

logger = logging.getLogger(__name__)

Account = dict  # accounts 表行（sqlite3.Row 转 dict）

# 进行中的同步账号（进程内防重入：调度器轮询与手动同步可能并发触发同一账号）
_SYNCING: set[int] = set()
_SYNC_LOCK = threading.Lock()

# 进行中的历史回补账号（与增量同步独立：回补长跑数小时，不能占住 _SYNCING 挡住收信）
_BACKFILLING: set[int] = set()
_BACKFILL_LOCK = threading.Lock()


def add_notification(n_type: str, title: str, body: str = "", ref_id: str | None = None) -> None:
    with get_conn() as conn:  # sqlite3 连接作上下文管理器 == 事务
        conn.execute(
            "INSERT INTO notifications (type, title, body, ref_id) VALUES (?, ?, ?, ?)",
            (n_type, title, body, ref_id),
        )


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _safe_filename(name: str, index: int) -> str:
    name = re.sub(r'[\\/:*?"<>|\r\n]+', "_", (name or "").strip())
    return name or f"attachment-{index}"


def _save_attachments(account_id: int, email_id: int, parsed) -> bool:
    """保存附件文件并写元数据行，返回是否有附件（事务由调用方按块提交）。"""
    base = get_data_dir() / "accounts" / str(account_id) / "attachments" / str(email_id)
    conn = get_conn()
    has_any = False
    for index, att in enumerate(parsed.attachments):
        if not att.payload:
            continue
        has_any = True
        filename = _safe_filename(att.filename, index)
        target = base / f"{index}_{filename}"
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(att.payload)
        except OSError:
            logger.exception("save attachment failed: %s", target)
            continue
        conn.execute(
            "INSERT INTO attachments (email_id, filename, mime, size, path, cid)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (email_id, filename, att.content_type, len(att.payload), str(target), att.cid),
        )
    return has_any


def _norm_date(dt: datetime | None) -> tuple[str | None, str | None]:
    """归一化邮件日期为 (date, date_sort)；畸形日期头容错。

    年份超界的 Date 头（如 year=0001/9999）在 Windows 的本地时区换算
    （astimezone → CRT localtime）会抛 `OSError: [Errno 22] Invalid argument`，
    曾导致整个文件夹同步死循环——此处任何异常都降级为不参与排序。
    """
    if dt is None:
        return None, None
    try:
        return dt.isoformat(timespec="seconds"), dt.astimezone(UTC).isoformat(timespec="seconds")
    except Exception:  # noqa: BLE001 — 单封畸形日期不阻塞同步
        try:
            return dt.isoformat(), None
        except Exception:  # noqa: BLE001
            return None, None


def _upsert_email(account_id: int, folder: str, parsed) -> int:
    """插入（或忽略重复）邮件行，返回行 id（不提交，事务由调用方按块管理）。"""
    text = (parsed.body_text or "").strip()
    snippet = re.sub(r"\s+", " ", text)[:180]
    date_iso, date_sort = _norm_date(parsed.date)
    conn = get_conn()
    cur = conn.execute(
        "INSERT OR IGNORE INTO emails"
        " (account_id, folder, uid, message_id, subject, sender_name, sender_email,"
        "  recipients, cc, date, date_sort, snippet, body_text, body_html, remote_img_count,"
        "  is_read, starred)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            account_id,
            folder,
            parsed.uid,
            (parsed.message_id or "").strip(),
            parsed.subject,
            parsed.sender_name,
            parsed.sender_email,
            json.dumps(parsed.recipients, ensure_ascii=False),
            json.dumps(parsed.cc, ensure_ascii=False),
            date_iso,
            date_sort,
            snippet,
            text,
            parsed.body_html or "",
            count_remote_images(parsed.body_html or ""),
            # 按服务器 FLAGS 初始化：别处（网页/手机）已读/星标过的新邮件不再误报未读
            1 if imap_client.SEEN_FLAG in parsed.flags else 0,
            1 if imap_client.FLAGGED_FLAG in parsed.flags else 0,
        ),
    )
    if cur.rowcount == 0:  # 重复邮件（上次中断前已入库）：回查既有行
        row = conn.execute(
            "SELECT id FROM emails WHERE account_id = ? AND folder = ? AND uid = ?",
            (account_id, folder, parsed.uid),
        ).fetchone()
        return int(row["id"])
    return int(cur.lastrowid)


def _set_account_status(account_id: int, status: str, detail: str | None = None,
                        error_title: str | None = None) -> None:
    conn = get_conn()
    prev = conn.execute("SELECT status, email FROM accounts WHERE id = ?", (account_id,)).fetchone()
    conn.execute(
        "UPDATE accounts SET status = ?, status_detail = ? WHERE id = ?",
        (status, detail, account_id),
    )
    conn.commit()
    # 状态变化时发一次通知，避免重复打扰（授权码失效提醒）
    if prev and prev["status"] != status and status in ("auth_error", "connection_error"):
        titles = {
            "auth_error": "授权码可能已过期",
            "connection_error": "邮箱连接异常",
        }
        add_notification(
            "account_error",
            f"{error_title or titles[status]}：{prev['email']}",
            detail or "请在 设置-账号 中重新验证",
            str(account_id),
        )


def sync_account(account: Account, folders: tuple[str, ...] = ("INBOX",)) -> dict:
    """同步单个账号的指定文件夹，返回 {ok, folders: [...], error}。

    网络类异常（含 QQ 随机掐断重负载连接导致的 Errno 22）自动重试：
    断点已按小块落库，重试只补剩余部分；重试间退避等待，给服务商频控降温。
    登录失败不重试（结果可预期）。
    """
    account_id = int(account["id"])
    try:
        handle = mailbox.load_account(account_id)  # 全项目唯一 MailConfig 构造点
    except mailbox.MailError as exc:
        return {"ok": False, "folders": [], "error": exc.message}
    results: list[dict] = []
    last_error: Exception | None = None
    for attempt, backoff in ((1, 0), (2, 15), (3, 45)):
        if backoff:
            logger.info("sync retry for %s in %ss (断点已落库，只补剩余)", account["email"], backoff)
            time.sleep(backoff)
        try:
            with mailbox.open_imap(handle) as mb:
                results = []
                for folder in folders:
                    results.append(_sync_folder(mb, account_id, folder))
            last_error = None
            break
        except MailboxLoginError:
            detail = "IMAP 登录被拒绝，授权码可能已过期或被修改"
            _set_account_status(account_id, "auth_error", detail)
            return {"ok": False, "folders": results, "error": detail}
        except Exception as exc:  # noqa: BLE001 — 网络/服务器错误统一为 connection_error
            last_error = exc
            logger.warning("sync failed for %s (attempt %d): %s", account["email"], attempt, exc)

    if last_error is not None:
        _set_account_status(account_id, "connection_error", str(last_error)[:300])
        return {"ok": False, "folders": results, "error": str(last_error)}

    _set_account_status(account_id, "ok")
    conn = get_conn()
    conn.execute(
        "UPDATE accounts SET last_sync_at = ?, status_detail = NULL WHERE id = ?",
        (_utc_now_iso(), account_id),
    )
    conn.commit()

    new_total = sum(r["new_count"] for r in results)
    if new_total > 0:
        first = results[0]
        add_notification(
            "new_mail",
            f"{account['email']}：{new_total} 封新邮件",
            first.get("latest_subject") or "",
            str(account_id),
        )

    # AI 流水线（白/黑名单 → 分类 → 自动归档 → 草稿）；失败不影响同步结果。
    # v0.4：只对 INBOX 新邮件跑管线——按需同步的其他文件夹不做分类/草稿/归档
    new_ids = [eid for r in results if r["folder"] == "INBOX" for eid in r.get("new_email_ids", [])]
    if new_ids:
        try:
            from app.core.pipeline import process_new_emails

            process_new_emails(account, new_ids)
        except Exception:  # noqa: BLE001
            logger.exception("pipeline crashed for account %s", account_id)

    # B1 全量同步：有未完成回补（首翻新账号/升级存量/上次中断）→ 起后台回补线程
    maybe_start_backfill(account)

    return {"ok": True, "folders": results, "error": None}


def start_sync(account: Account, folders: tuple[str, ...] = ("INBOX",)) -> dict:
    """在后台线程执行同步，立即返回 {started, reason?}。

    手动同步、添加账号、调度器轮询都走这里：长同步不再阻塞请求与调度 tick。
    进度经账号 status/status_detail 呈现，完成后发通知。
    """
    account_id = int(account["id"])
    with _SYNC_LOCK:
        if account_id in _SYNCING:
            return {"started": False, "reason": "syncing"}
        if not mailbox.has_credentials(account_id):
            # OAuth 账号令牌丢失要可见：置 auth_error+通知（状态迁移时只发一次），
            # 否则调度器会静默跳过、标已读/收信全部无声失败——曾静默 24 小时无人知
            row = get_conn().execute(
                "SELECT auth_type FROM accounts WHERE id = ?", (account_id,)
            ).fetchone()
            if row and row["auth_type"] == "oauth2":
                _set_account_status(
                    account_id, "auth_error", "OAuth 授权丢失，请到 设置-邮箱账号 重新授权",
                    error_title="OAuth 授权丢失",
                )
            return {"started": False, "reason": "no_credentials"}
        _SYNCING.add(account_id)

    def _run() -> None:
        try:
            sync_account(account, folders)
        except Exception:  # noqa: BLE001 — sync_account 内部已兜底，这里防御线程带异常退出
            logger.exception("background sync crashed for account %s", account_id)
        finally:
            close_thread_conn()  # 一次性线程：连接随线程关闭，防泄漏
            with _SYNC_LOCK:
                _SYNCING.discard(account_id)

    threading.Thread(target=_run, name=f"sync-{account_id}", daemon=True).start()
    return {"started": True}


# ---------------------------------------------------------------------------
# 历史回补（EXPERIENCE_PLAN B1）：全部文件夹 × 全部历史，从新到旧分块补齐
# ---------------------------------------------------------------------------

_BACKFILL_PAGE = 25  # 与增量块一致：小块 + 节流，防服务商频控/掐连接
_BACKFILL_PAGES_PER_FOLDER_PASS = 80  # 单文件夹单趟最多 80 页（~2000 封），趟间重连换气
_BACKFILL_IDLE_SLEEP = 30.0  # 无进展退避（服务器持续掐断时防空转）


def maybe_start_backfill(account: Account) -> None:
    """有未完成回补时起独立后台线程（防重入）。增量同步照常进行，互不阻塞。"""
    account_id = int(account["id"])
    if not _backfill_pending(account_id):
        return
    with _BACKFILL_LOCK:
        if account_id in _BACKFILLING:
            return
        if not mailbox.has_credentials(account_id):
            return
        _BACKFILLING.add(account_id)
    threading.Thread(
        target=_backfill_worker, args=(account,), name=f"backfill-{account_id}", daemon=True
    ).start()


def _ensure_folders_enumerated(account_id: int, mb) -> None:  # noqa: ANN001 — MailBox
    """LIST 全量文件夹写入缓存，并为每个待回补文件夹确保 sync_state 行存在。

    Gmail 的 All Mail（special_use=all）与 INBOX 内容重复，排除在回补外；
    其余文件夹（含已发送/垃圾/废纸篓）全部回补——用户要求原生客户端级全量。
    """
    from app.core import folders as folders_core

    listing = imap_client.list_folders(mb)
    if not listing:
        return  # 空 LIST（网络抖动）：宁用旧缓存，勿清空（folders.refresh_cache 同口径）
    folders_core.upsert_listing(account_id, listing)
    conn = get_conn()
    for row in conn.execute(
        "SELECT name, special_use FROM folders WHERE account_id = ?", (account_id,)
    ).fetchall():
        if (row["special_use"] or "") == "all":
            continue
        conn.execute(
            "INSERT OR IGNORE INTO sync_state (account_id, folder, last_uid, backfill_done)"
            " VALUES (?, ?, 0, 0)",
            (account_id, row["name"]),
        )
    conn.commit()


def _backfill_todo(account_id: int) -> list[str]:
    """待回补文件夹，INBOX 优先。"""
    rows = get_conn().execute(
        "SELECT folder FROM sync_state WHERE account_id = ? AND backfill_done = 0",
        (account_id,),
    ).fetchall()
    folders = [r["folder"] for r in rows]
    return sorted(folders, key=lambda f: (f != "INBOX", f))


def _backfill_worker(account: Account) -> None:
    """回补主循环：每轮一条 IMAP 连接，按文件夹轮转分趟拉取，断点在库可续传。

    网络被掐/超时 → 下轮重连从断点继续；无进展退避，防对频控服务器空转。
    """
    account_id = int(account["id"])
    try:
        handle = mailbox.load_account(account_id)
    except mailbox.MailError as exc:
        logger.warning("backfill aborted for %s: %s", account.get("email"), exc.message)
        with _BACKFILL_LOCK:
            _BACKFILLING.discard(account_id)
        return
    try:
        while _backfill_pending(account_id):
            progressed = False
            try:
                with mailbox.open_imap(handle) as mb:
                    _ensure_folders_enumerated(account_id, mb)
                    for folder in _backfill_todo(account_id):
                        outcome = _backfill_folder_pass(mb, account_id, folder)
                        if outcome == "progress":
                            progressed = True
                        time.sleep(1.0)  # 文件夹之间小憩
            except MailboxLoginError:
                logger.warning("backfill stopped for %s: 授权失效", account.get("email"))
                _set_account_status(account_id, "auth_error", "IMAP 登录被拒绝，授权码可能已过期")
                return
            except Exception as exc:  # noqa: BLE001 — 网络/服务器错误：重连下一轮
                logger.warning("backfill pass failed for %s: %s", account.get("email"), exc)
            if not progressed:
                time.sleep(_BACKFILL_IDLE_SLEEP)
    finally:
        close_thread_conn()
        with _BACKFILL_LOCK:
            _BACKFILLING.discard(account_id)


def _backfill_folder_pass(mb, account_id: int, folder: str) -> str:  # noqa: ANN001 — MailBox
    """单文件夹单趟回补：从 backfill_uid 断点向下拉至多 _BACKFILL_PAGES_PER_FOLDER_PASS 页。

    返回 'done'（该文件夹历史已齐）或 'progress'（还有剩余，后续趟继续）。
    只入库邮件与附件：不进 AI 流水线、不发通知、不采通讯录（老邮件全量跑 AI
    与通知轰炸都是灾难，通讯录也不该被十年前的古董发件人淹没）。
    """
    conn = get_conn()
    state = conn.execute(
        "SELECT backfill_uid, backfill_done FROM sync_state WHERE account_id = ? AND folder = ?",
        (account_id, folder),
    ).fetchone()
    if state is None or state["backfill_done"]:
        return "done"
    # 先做一次常规同步（新文件夹补首翻、旧文件夹收增量），保证断点锚点存在
    _sync_folder(mb, account_id, folder)
    state = conn.execute(
        "SELECT backfill_uid, backfill_done FROM sync_state WHERE account_id = ? AND folder = ?",
        (account_id, folder),
    ).fetchone()
    if state is None or state["backfill_done"]:
        return "done"  # 常规同步时发现历史已齐（文件夹总量不足一页）
    upper = state["backfill_uid"] if state else None
    if not upper or upper <= 1:
        _save_backfill_state(conn, account_id, folder, upper, 1)
        conn.commit()
        return "done"

    mb.folder.set(folder)
    older = sorted((int(u) for u in mb.uids(f"UID 1:{upper - 1}")), reverse=True)
    if not older:
        _save_backfill_state(conn, account_id, folder, upper, 1)
        conn.commit()
        return "done"

    total = len(older)
    page = 0
    for start in range(0, min(total, _BACKFILL_PAGES_PER_FOLDER_PASS * _BACKFILL_PAGE), _BACKFILL_PAGE):
        window = older[start : start + _BACKFILL_PAGE]
        for parsed_msg in imap_client.fetch_uids_parsed(mb, window):
            email_id = _upsert_email(account_id, folder, parsed_msg)
            _save_attachments(account_id, email_id, parsed_msg)
        # 断点随页提交：min(window) 即下一趟的搜索上界（更旧的还没拉）
        _save_backfill_state(conn, account_id, folder, min(window), 0)
        conn.commit()
        page += 1
        _set_account_status(
            account_id, "syncing", f"回补 {folder}：剩 {max(0, total - page * _BACKFILL_PAGE)} 封"
        )
        time.sleep(0.2)  # 页间节流，与增量同步同口径

    if total <= _BACKFILL_PAGES_PER_FOLDER_PASS * _BACKFILL_PAGE:
        _save_backfill_state(conn, account_id, folder, min(older), 1)
        conn.commit()
        logger.info("backfill %s/%s: +%d uids, folder history complete", account_id, folder, total)
        return "done"
    logger.info("backfill %s/%s: +%d uids this pass, continuing", account_id, folder, page * _BACKFILL_PAGE)
    return "progress"


def _save_sync_state(conn, account_id: int, folder: str,
                     last_uid: int, uidvalidity: int | None) -> None:  # noqa: ANN001
    conn.execute(
        "INSERT INTO sync_state (account_id, folder, last_uid, uidvalidity) VALUES (?, ?, ?, ?)"
        " ON CONFLICT(account_id, folder) DO UPDATE SET"
        " last_uid = excluded.last_uid, uidvalidity = excluded.uidvalidity",
        (account_id, folder, last_uid, uidvalidity),
    )


def _save_backfill_state(conn, account_id: int, folder: str,
                         backfill_uid: int | None, done: int) -> None:  # noqa: ANN001
    """更新回补断点（行由 _save_sync_state 先建；迁移 v26 前的老行也有默认值）。"""
    conn.execute(
        "UPDATE sync_state SET backfill_uid = ?, backfill_done = ?"
        " WHERE account_id = ? AND folder = ?",
        (backfill_uid, done, account_id, folder),
    )


def _backfill_pending(account_id: int) -> bool:
    row = get_conn().execute(
        "SELECT 1 FROM sync_state WHERE account_id = ? AND backfill_done = 0 LIMIT 1",
        (account_id,),
    ).fetchone()
    return row is not None


def _reconcile_flags(mb, account_id: int, folder: str) -> int:  # noqa: ANN001
    """以服务器 FLAGS 对账本地已读/星标——外部客户端（TB/网页/手机）已读变化的入网点。

    UID SEARCH UNSEEN/FLAGGED 各一条命令，与本地该文件夹全部行比对，只翻有差异的
    行（本地行为主：服务器侧已删的 UID 不会凭空进本地）；SEARCH 失败整段跳过。
    返回翻动行数（日志用），事务由调用方提交。
    """
    result = imap_client.search_flag_uids(mb, folder)
    if result is None:
        return 0
    unread_uids, flagged_uids = result
    conn = get_conn()
    changed = 0
    read_ids: list[int] = []
    unread_ids: list[int] = []
    star_ids: list[int] = []
    unstar_ids: list[int] = []
    for row in conn.execute(
        "SELECT id, uid, is_read, starred FROM emails WHERE account_id = ? AND folder = ?",
        (account_id, folder),
    ).fetchall():
        want_read = 0 if int(row["uid"]) in unread_uids else 1
        want_star = 1 if int(row["uid"]) in flagged_uids else 0
        if int(row["is_read"]) != want_read:
            (unread_ids if want_read == 0 else read_ids).append(int(row["id"]))
        if int(row["starred"]) != want_star:
            (star_ids if want_star else unstar_ids).append(int(row["id"]))
    for ids, col, val in (
        (read_ids, "is_read", 1),
        (unread_ids, "is_read", 0),
        (star_ids, "starred", 1),
        (unstar_ids, "starred", 0),
    ):
        # 分批防超 SQLite 变量上限
        for start in range(0, len(ids), 500):
            chunk = ids[start : start + 500]
            ph = ",".join("?" * len(chunk))
            cur = conn.execute(f"UPDATE emails SET {col} = ? WHERE id IN ({ph})", (val, *chunk))
            changed += cur.rowcount
    return changed


def _sync_folder(mb, account_id: int, folder: str) -> dict:  # noqa: ANN001
    conn = get_conn()
    state = conn.execute(
        "SELECT last_uid, uidvalidity FROM sync_state WHERE account_id = ? AND folder = ?",
        (account_id, folder),
    ).fetchone()
    last_uid = int(state["last_uid"]) if state else 0
    stored_uidv = int(state["uidvalidity"]) if state and state["uidvalidity"] else None

    uidvalidity = get_uidvalidity(mb, folder)
    if uidvalidity is not None and stored_uidv is not None and uidvalidity != stored_uidv:
        # 服务器文件夹被重建：清空本地该文件夹数据（附件行随 FK 级联删除），重新增量起点
        stale_ids = [
            int(r["id"]) for r in conn.execute(
                "SELECT id FROM emails WHERE account_id = ? AND folder = ?", (account_id, folder)
            ).fetchall()
        ]
        conn.execute(
            "DELETE FROM emails WHERE account_id = ? AND folder = ?", (account_id, folder)
        )
        conn.commit()
        last_uid = 0
        if stale_ids:
            # R7：附件文件在磁盘不随行删除——UIDVALIDITY 变化产生的孤儿目录顺带清掉
            import shutil

            att_base = get_data_dir() / "accounts" / str(account_id) / "attachments"
            for eid in stale_ids:
                shutil.rmtree(att_base / str(eid), ignore_errors=True)

    new_count = 0
    latest_subject = ""
    new_email_ids: list[int] = []
    from app.core import contacts as contacts_core  # 局部导入避免环（contacts 不依赖 sync）

    if last_uid <= 0:
        # 首同步（EXPERIENCE_PLAN B1）：拉最新一页立即可用；更早历史由回补线程
        # 从新到旧补齐。旧实现只拉最近 30 天且永不回补，大邮箱永远缺历史。
        mb.folder.set(folder)
        newest = sorted((int(u) for u in mb.uids("ALL")), reverse=True)
        window, rest = newest[:25], newest[25:]
        done = 0 if rest else 1  # 文件夹总量不足一页 → 历史已齐
        backfill_uid: int | None = None
        for parsed_msg in sorted(
            imap_client.fetch_uids_parsed(mb, window) if window else [], key=lambda m: m.uid
        ):
            email_id = _upsert_email(account_id, folder, parsed_msg)
            _save_attachments(account_id, email_id, parsed_msg)
            contacts_core.collect_sender(parsed_msg.sender_email, parsed_msg.sender_name, account_id)
            last_uid = max(last_uid, parsed_msg.uid)
            new_count += 1
            latest_subject = latest_subject or parsed_msg.subject
            new_email_ids.append(email_id)
        backfill_uid = last_uid or None
        _save_sync_state(conn, account_id, folder, last_uid, uidvalidity or stored_uidv)
        _save_backfill_state(conn, account_id, folder, backfill_uid, done)
        conn.commit()
        if new_count:
            _set_account_status(account_id, "syncing", f"同步中：已收 {new_count} 封")
        return {
            "folder": folder,
            "new_count": new_count,
            "latest_subject": latest_subject,
            "new_email_ids": new_email_ids,
        }

    for chunk in iter_new_mail(mb, folder, last_uid):
        if not chunk:
            continue
        chunk_ids: list[int] = []
        for parsed_msg in chunk:
            email_id = _upsert_email(account_id, folder, parsed_msg)
            _save_attachments(account_id, email_id, parsed_msg)
            # 通讯录自动采集（v0.4 P4）：新邮件发件人入册
            contacts_core.collect_sender(parsed_msg.sender_email, parsed_msg.sender_name, account_id)
            chunk_ids.append(email_id)
            last_uid = max(last_uid, parsed_msg.uid)
            new_count += 1
            latest_subject = latest_subject or parsed_msg.subject
        new_email_ids.extend(chunk_ids)
        # 块级断点：入库与断点同一事务提交，中断后从断点续传
        _save_sync_state(conn, account_id, folder, last_uid, uidvalidity or stored_uidv)
        conn.commit()
        _set_account_status(account_id, "syncing", f"同步中：已收 {new_count} 封")

    _save_sync_state(conn, account_id, folder, last_uid, uidvalidity or stored_uidv)
    conn.commit()
    try:
        fixed = _reconcile_flags(mb, account_id, folder)
        if fixed:
            conn.commit()
            logger.info("flags reconciled for account %s folder %s: %d rows",
                        account_id, folder, fixed)
    except Exception:  # noqa: BLE001 — 对账尽力而为，同步结果不受影响
        logger.exception("flag reconcile failed for account %s folder %s", account_id, folder)
    return {
        "folder": folder,
        "new_count": new_count,
        "latest_subject": latest_subject,
        "new_email_ids": new_email_ids,
    }


def resync_folder_with_mb(mb, account_id: int, folder: str) -> dict:  # noqa: ANN001 — mb 为 MailBox
    """复用既有 IMAP 连接做单文件夹增量同步（批量移动/归档后目标文件夹立即可见）。

    尽力而为：失败只记日志不抛——服务器侧移动已成功，本地重建还有轮询兜底
    （调度轮询含归档文件夹）。供 batch_ops 在动作 job 内就地调用。
    """
    try:
        return _sync_folder(mb, account_id, folder)
    except Exception:  # noqa: BLE001 — 同上，重建失败不推翻已完成的移动
        logger.exception("post-action resync failed for account %s folder %s",
                         account_id, folder)
        return {"folder": folder, "new_count": 0, "new_email_ids": []}


def delete_account_files(account_id: int) -> None:
    """删除账号附件目录（账号删除时调用）。"""
    base = get_data_dir() / "accounts" / str(account_id)
    if base.exists():
        import shutil

        shutil.rmtree(base, ignore_errors=True)
