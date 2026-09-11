"""写信台草稿发送（API 与调度器共用的唯一实现）。

放 core 层的原因：调度器到期派发不能 import API 层（分层规则，IMPROVEMENT_PLAN
A2/T4），且后台线程不应出现 HTTPException——本模块统一抛 mailbox.MailError，
由 api/deps.py 翻译为 HTTP；调度器直接消费 code/message。
"""
from __future__ import annotations

import shutil
from pathlib import Path

from app.config import get_data_dir
from app.core import mailbox
from app.core.mail_html import html_to_plain_text, sanitize_outgoing_html, wrap_email_body_html
from app.db.database import get_conn


def draft_dir(draft_id: int) -> Path:
    """草稿附件目录（删除草稿与发送成功后清理由调用方执行）。"""
    return get_data_dir() / "drafts" / str(draft_id)


def send_user_draft(draft_id: int) -> None:
    """发送写信台草稿：状态校验 → 地址解析 → 消毒/派生纯文本 → 发送 → 标记 sent。

    失败抛 MailError（code ∈ not_found | state | no_recipient | missing_credential
    | not_found(账号) | smtp_missing | send_failed），状态保持不变；
    成功即置 sent、清 send_at、删附件目录。
    """
    row = get_conn().execute("SELECT * FROM user_drafts WHERE id = ?", (draft_id,)).fetchone()
    if row is None:
        raise mailbox.MailError("not_found", "草稿不存在")
    if row["status"] not in ("editing", "scheduled"):
        raise mailbox.MailError("state", "该草稿已发送或已丢弃")

    to_list = mailbox.split_addresses(row["to_addrs"])
    cc_list = mailbox.split_addresses(row["cc_addrs"])
    bcc_list = mailbox.split_addresses(row["bcc_addrs"])
    if not to_list:
        raise mailbox.MailError("no_recipient", "收件人不能为空")

    handle = mailbox.load_account(int(row["account_id"]))

    html = wrap_email_body_html(sanitize_outgoing_html(row["body_html"]))
    text = html_to_plain_text(html)

    # 回复信件带上 In-Reply-To，让对方客户端正确串线
    in_reply_to: str | None = None
    if row["in_reply_to"]:
        mrow = get_conn().execute(
            "SELECT message_id FROM emails WHERE id = ?", (row["in_reply_to"],)
        ).fetchone()
        if mrow and mrow["message_id"]:
            in_reply_to = mrow["message_id"]

    paths = [
        r["path"]
        for r in get_conn().execute(
            "SELECT path FROM user_draft_attachments WHERE draft_id = ? ORDER BY id", (draft_id,)
        ).fetchall()
        if Path(r["path"]).exists()
    ]

    try:
        mailbox.send_message(
            handle, to=to_list, cc=cc_list, bcc=bcc_list,
            subject=row["subject"], text=text, html=html,
            attachment_paths=paths, in_reply_to=in_reply_to,
        )
    except mailbox.MailError:
        raise
    except Exception as exc:  # noqa: BLE001 — SMTP/网络错误统一为 send_failed
        raise mailbox.MailError("send_failed", f"发送失败：{exc}") from exc

    conn = get_conn()
    conn.execute(
        "UPDATE user_drafts SET status = 'sent', send_at = NULL, updated_at = datetime('now')"
        " WHERE id = ?",
        (draft_id,),
    )
    conn.commit()
    shutil.rmtree(draft_dir(draft_id), ignore_errors=True)
