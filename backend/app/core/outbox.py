"""写信台草稿发送（API 与调度器共用的唯一实现）。

放 core 层的原因：调度器到期派发不能 import API 层（分层规则，IMPROVEMENT_PLAN
A2/T4），且后台线程不应出现 HTTPException——本模块统一抛 mailbox.MailError，
由 api/deps.py 翻译为 HTTP；调度器直接消费 code/message。
"""
from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path

from app.config import get_data_dir
from app.core import mailbox
from app.core.imap_client import SEEN_FLAG, reply_subject
from app.core.mail_html import (
    decorate_outgoing_html,
    html_to_plain_text,
    markdown_to_email_html,
    sanitize_outgoing_html,
    wrap_email_body_html,
)
from app.db.database import get_conn, get_setting, tx

logger = logging.getLogger(__name__)


def draft_dir(draft_id: int) -> Path:
    """草稿附件目录（删除草稿与发送成功后清理由调用方执行）。"""
    return get_data_dir() / "drafts" / str(draft_id)


def template_files_dir(template_id: str) -> Path:
    """模板附件目录（S-0921 模板带附件；template_id 由前端生成，sanitize 防穿越）。

    放 core 的原因：ai/tools 的 apply_template 复制附件也要用，而 ai 层禁 import api 层。"""
    safe = re.sub(r"[^\w.-]", "_", template_id) or "_"
    return get_data_dir() / "compose_template_files" / safe


def _append_signature_if_configured(account_id: int, body_html: str) -> str:
    """AI 草稿发送前补该账号默认签名（EXPERIENCE_PLAN B6）。幂等：正文已含同款签名则跳过。"""
    from app.core.mail_html import markdown_body_html

    sigs = get_setting("compose_signatures", []) or []
    content = next((str(s.get("content") or "") for s in sigs
                    if isinstance(s, dict) and int(s.get("account_id") or 0) == account_id), None)
    if not content:
        return body_html
    sig_html = sanitize_outgoing_html(markdown_body_html(content)).strip()
    if not sig_html or sig_html in body_html:
        return body_html
    return body_html + sig_html


def migrate_legacy_ai_drafts() -> int:
    """一次性：旧 drafts 表（AI 待审草稿）数据并入 user_drafts（v0.4 P3，REDESIGN_PLAN §5.1）。

    幂等：KV legacy_drafts_migrated 置位后跳过。content(Markdown)→body_html 与原
    approve 发送路径同源（markdown_to_email_html）；status 映射
    pending→pending_review / sent→sent / discarded→discarded；收件人=原发件人、
    主题=Re: 原主题、in_reply_to=原邮件（软引用）。旧表保留只读，不再使用。
    启动期调用（main.lifespan）；schema 变更在迁移 v19。
    """
    if get_setting("legacy_drafts_migrated"):
        return 0
    rows = get_conn().execute("SELECT * FROM drafts ORDER BY id").fetchall()
    with tx() as conn:
        # 门控与数据同一事务提交（set_setting 会自 commit，破坏外层事务，故直写 SQL）；
        # 中断即整体回滚，下次启动重跑，绝不出现半份拷贝
        conn.execute(
            "INSERT INTO settings (key, value) VALUES ('legacy_drafts_migrated', 'true')"
            " ON CONFLICT(key) DO UPDATE SET value = 'true', updated_at = datetime('now')"
        )
        for r in rows:
            email = conn.execute(
                "SELECT subject, sender_email FROM emails WHERE id = ?", (r["email_id"],)
            ).fetchone()
            subject = reply_subject(email["subject"]) if email else "回复"
            to_addr = (email["sender_email"] if email else "") or ""
            conn.execute(
                "INSERT INTO user_drafts (account_id, mode, in_reply_to, to_addrs, subject,"
                " body_html, status, origin, instruction, created_at, updated_at)"
                " VALUES (?, 'reply', ?, ?, ?, ?, ?, 'ai', ?, ?, ?)",
                (
                    r["account_id"],
                    r["email_id"],
                    to_addr,
                    subject,
                    markdown_to_email_html(r["content"] or ""),
                    {"pending": "pending_review"}.get(r["status"], r["status"]),
                    r["instruction"],
                    r["created_at"],
                    r["updated_at"] or r["created_at"],  # 旧表 updated_at 可空
                ),
            )
    return len(rows)


def _mark_original_seen(email_id: int) -> None:
    """回复发送后把原邮件在服务器端也标为已读（IMAP STORE \\Seen，审查 C1）。

    本地 is_read 已置位但服务器 SEEN 不同步时，网页端仍显示未读、重同步后
    本地状态也会漂回。尽力而为：邮件可能已被移动/删除或服务器暂不可达，
    失败只告警不回滚发送结果。
    """
    row = get_conn().execute(
        "SELECT account_id, folder, uid FROM emails WHERE id = ?", (email_id,)
    ).fetchone()
    if row is None or not row["uid"]:
        return
    try:
        handle = mailbox.load_account(int(row["account_id"]))
        with mailbox.open_imap(handle) as mb:
            mb.folder.set(row["folder"])
            mb.flag([str(row["uid"])], [SEEN_FLAG], True)
    except Exception as exc:  # noqa: BLE001 — 已读回写失败不影响发送成功
        logger.warning("回复后回写服务器已读失败 (email %s): %s", email_id, exc)


def send_user_draft(draft_id: int) -> None:
    """发送草稿（唯一实现，API 与调度器共用）：状态校验 → 地址解析 →
    消毒/派生纯文本 → 发送 → 标记 sent。

    v0.4：status 含 pending_review（AI 待审批准发送与手写发送同一条通路）。
    失败抛 MailError（code ∈ not_found | state | no_recipient | missing_credential
    | not_found(账号) | smtp_missing | send_failed），状态保持不变；
    成功即置 sent、清 send_at、删附件目录，并对回复目标邮件补标已读。
    """
    row = get_conn().execute("SELECT * FROM user_drafts WHERE id = ?", (draft_id,)).fetchone()
    if row is None:
        raise mailbox.MailError("not_found", "草稿不存在")
    if row["status"] not in ("editing", "scheduled", "pending_review"):
        raise mailbox.MailError("state", "该草稿已发送或已丢弃")

    to_list = mailbox.split_addresses(row["to_addrs"])
    cc_list = mailbox.split_addresses(row["cc_addrs"])
    bcc_list = mailbox.split_addresses(row["bcc_addrs"])
    if not to_list:
        raise mailbox.MailError("no_recipient", "收件人不能为空")

    handle = mailbox.load_account(int(row["account_id"]))

    # AI 起草的信补默认签名（EXPERIENCE_PLAN B6）：前端编辑器是人工写信时插签名的
    # 唯一入口，AI 起草的邮件原本永远没有签名（prompts 声称"系统会自动处理"但实现
    # 缺失）。用户开启 auto_insert_signature 时在发送前补上；幂等（已含同款签名跳过）。
    if row["origin"] == "ai":
        html = _append_signature_if_configured(int(row["account_id"]), row["body_html"] or "")
    else:
        html = row["body_html"] or ""

    html = wrap_email_body_html(decorate_outgoing_html(sanitize_outgoing_html(html)))
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
    # 回复原邮件补标已读（原 approve 语义，迁移后对所有回复草稿生效）
    if row["in_reply_to"]:
        conn.execute("UPDATE emails SET is_read = 1 WHERE id = ?", (row["in_reply_to"],))
    conn.commit()
    if row["in_reply_to"]:
        _mark_original_seen(int(row["in_reply_to"]))
    # 通讯录自动采集（v0.4 P4）：发送成功的收件人入册
    from app.core import contacts as contacts_core  # 局部导入避免环

    contacts_core.collect_addresses(row["to_addrs"], int(row["account_id"]))
    contacts_core.collect_addresses(row["cc_addrs"], int(row["account_id"]))
    contacts_core.collect_addresses(row["bcc_addrs"], int(row["account_id"]))
    shutil.rmtree(draft_dir(draft_id), ignore_errors=True)
