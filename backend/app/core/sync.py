"""UID 增量同步引擎。

- 首次同步只拉最近 N 天（见 imap_client.fetch_new）；
- UIDVALIDITY 变化时清空该文件夹本地数据并重新首次同步；
- 附件落盘到数据目录，元数据入库；
- 登录失败标记账号 auth_error 并发一次通知（授权码失效提醒）。
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone

from imap_tools.errors import MailboxLoginError

from app.core.imap_client import MailConfig, connect_imap, fetch_new, get_uidvalidity
from app.core.mail_html import count_remote_images
from app.config import get_data_dir
from app.db.database import get_conn
from app.security import get_secret

logger = logging.getLogger(__name__)

FIRST_SYNC_DAYS = 30

Account = dict  # accounts 表行（sqlite3.Row 转 dict）


def add_notification(n_type: str, title: str, body: str = "", ref_id: str | None = None) -> None:
    with get_conn() as conn:  # sqlite3 连接作上下文管理器 == 事务
        conn.execute(
            "INSERT INTO notifications (type, title, body, ref_id) VALUES (?, ?, ?, ?)",
            (n_type, title, body, ref_id),
        )


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_filename(name: str, index: int) -> str:
    name = re.sub(r'[\\/:*?"<>|\r\n]+', "_", (name or "").strip())
    return name or f"attachment-{index}"


def _save_attachments(account_id: int, email_id: int, parsed) -> bool:
    """保存附件文件并写元数据行，返回是否有附件。"""
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
    conn.commit()
    return has_any


def _upsert_email(account_id: int, folder: str, parsed) -> int:
    """插入（或忽略重复）邮件行，返回行 id。"""
    text = (parsed.body_text or "").strip()
    snippet = re.sub(r"\s+", " ", text)[:180]
    date_iso = parsed.date.isoformat(timespec="seconds") if parsed.date else None
    conn = get_conn()
    conn.execute(
        "INSERT OR IGNORE INTO emails"
        " (account_id, folder, uid, message_id, subject, sender_name, sender_email,"
        "  recipients, cc, date, snippet, body_text, body_html, remote_img_count)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
            snippet,
            text,
            parsed.body_html or "",
            count_remote_images(parsed.body_html or ""),
        ),
    )
    conn.commit()
    row = conn.execute(
        "SELECT id FROM emails WHERE account_id = ? AND folder = ? AND uid = ?",
        (account_id, folder, parsed.uid),
    ).fetchone()
    return int(row["id"])


def _set_account_status(account_id: int, status: str, detail: str | None = None) -> None:
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
            f"{titles[status]}：{prev['email']}",
            detail or "请在 设置-账号 中重新验证",
            str(account_id),
        )


def sync_account(account: Account, folders: tuple[str, ...] = ("INBOX",)) -> dict:
    """同步单个账号的指定文件夹，返回 {ok, folders: [...], error}。"""
    account_id = int(account["id"])
    password = get_secret(f"account_pwd:{account_id}")
    if not password:
        return {"ok": False, "folders": [], "error": "缺少密码凭证"}

    cfg = MailConfig(
        email=account["email"],
        password=password,
        imap_server=account["imap_server"],
        imap_port=int(account["imap_port"]),
    )
    results: list[dict] = []
    try:
        with connect_imap(cfg) as mb:
            for folder in folders:
                results.append(_sync_folder(mb, account_id, folder))
    except MailboxLoginError:
        detail = "IMAP 登录被拒绝，授权码可能已过期或被修改"
        _set_account_status(account_id, "auth_error", detail)
        return {"ok": False, "folders": results, "error": detail}
    except Exception as exc:  # noqa: BLE001 — 网络/服务器错误统一为 connection_error
        logger.warning("sync failed for %s: %s", account["email"], exc)
        _set_account_status(account_id, "connection_error", str(exc)[:300])
        return {"ok": False, "folders": results, "error": str(exc)}

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

    # AI 流水线（白/黑名单 → 分类 → 自动归档 → 草稿）；失败不影响同步结果
    new_ids = [eid for r in results for eid in r.get("new_email_ids", [])]
    if new_ids:
        try:
            from app.core.pipeline import process_new_emails

            process_new_emails(account, new_ids)
        except Exception:  # noqa: BLE001
            logger.exception("pipeline crashed for account %s", account_id)

    return {"ok": True, "folders": results, "error": None}


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
        # 服务器文件夹被重建：清空本地该文件夹数据，重新增量起点
        conn.execute(
            "DELETE FROM emails WHERE account_id = ? AND folder = ?", (account_id, folder)
        )
        conn.commit()
        last_uid = 0

    new_count = 0
    latest_subject = ""
    new_email_ids: list[int] = []
    for parsed in fetch_new(mb, folder, last_uid, first_sync_days=FIRST_SYNC_DAYS):
        email_id = _upsert_email(account_id, folder, parsed)
        _save_attachments(account_id, email_id, parsed)
        last_uid = max(last_uid, parsed.uid)
        new_count += 1
        new_email_ids.append(email_id)
        latest_subject = latest_subject or parsed.subject

    conn.execute(
        "INSERT INTO sync_state (account_id, folder, last_uid, uidvalidity) VALUES (?, ?, ?, ?)"
        " ON CONFLICT(account_id, folder) DO UPDATE SET"
        " last_uid = excluded.last_uid, uidvalidity = excluded.uidvalidity",
        (account_id, folder, last_uid, uidvalidity or stored_uidv),
    )
    conn.commit()
    return {
        "folder": folder,
        "new_count": new_count,
        "latest_subject": latest_subject,
        "new_email_ids": new_email_ids,
    }


def delete_account_files(account_id: int) -> None:
    """删除账号附件目录（账号删除时调用）。"""
    base = get_data_dir() / "accounts" / str(account_id)
    if base.exists():
        import shutil

        shutil.rmtree(base, ignore_errors=True)
