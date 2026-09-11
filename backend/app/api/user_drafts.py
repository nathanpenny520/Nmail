"""写信工作台：用户手写草稿的增删改查与发送。

独立于 AI 待审草稿（api/drafts.py）。前端写信工作台的每个标签对应一条
user_drafts 记录，编辑内容防抖自动保存（PATCH）；发送走 SMTP 通路并把
status 置为 sent。正文存 HTML，发送前消毒并派生纯文本 alternative。
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from app.api.emails import _imap_for, re_split
from app.core import imap_client
from app.core.mail_html import html_to_plain_text, sanitize_outgoing_html, wrap_email_body_html
from app.db.database import get_conn

router = APIRouter(prefix="/api/user-drafts", tags=["user-drafts"])

_UPDATABLE = ("account_id", "mode", "in_reply_to", "to_addrs", "cc_addrs", "bcc_addrs", "subject", "body_html")


class UserDraftIn(BaseModel):
    account_id: int | None = None
    mode: str | None = None
    in_reply_to: int | None = None
    to_addrs: str | None = None
    cc_addrs: str | None = None
    bcc_addrs: str | None = None
    subject: str | None = None
    body_html: str | None = None


def _draft_dict(row) -> dict:  # noqa: ANN001
    return {
        "id": row["id"],
        "account_id": row["account_id"],
        "mode": row["mode"],
        "in_reply_to": row["in_reply_to"],
        "to_addrs": row["to_addrs"],
        "cc_addrs": row["cc_addrs"],
        "bcc_addrs": row["bcc_addrs"],
        "subject": row["subject"],
        "body_html": row["body_html"],
        "status": row["status"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _get_draft(draft_id: int) -> Any:
    row = get_conn().execute("SELECT * FROM user_drafts WHERE id = ?", (draft_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "草稿不存在")
    return row


@router.post("")
def create_draft(payload: UserDraftIn) -> dict:
    if payload.account_id is None:
        raise HTTPException(400, "缺少发件账号")
    conn = get_conn()
    if conn.execute("SELECT 1 FROM accounts WHERE id = ?", (payload.account_id,)).fetchone() is None:
        raise HTTPException(400, "发件账号不存在")
    cur = conn.execute(
        "INSERT INTO user_drafts (account_id, mode, in_reply_to, to_addrs, cc_addrs,"
        " bcc_addrs, subject, body_html) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            payload.account_id,
            payload.mode or "new",
            payload.in_reply_to,
            payload.to_addrs or "",
            payload.cc_addrs or "",
            payload.bcc_addrs or "",
            payload.subject or "",
            payload.body_html or "",
        ),
    )
    conn.commit()
    return {"draft": _draft_dict(_get_draft(cur.lastrowid))}


@router.get("")
def list_drafts(status: str = "editing") -> dict:
    rows = get_conn().execute(
        "SELECT * FROM user_drafts WHERE status = ? ORDER BY updated_at DESC LIMIT 100",
        (status,),
    ).fetchall()
    return {"drafts": [_draft_dict(r) for r in rows]}


@router.get("/{draft_id}")
def get_draft(draft_id: int) -> dict:
    return {"draft": _draft_dict(_get_draft(draft_id))}


@router.patch("/{draft_id}")
def update_draft(draft_id: int, payload: UserDraftIn) -> dict:
    _get_draft(draft_id)
    sets, values = [], []
    for field in _UPDATABLE:
        val = getattr(payload, field)
        if val is not None:
            sets.append(f"{field} = ?")
            values.append(val)
    if sets:
        sets.append("updated_at = datetime('now')")
        values.append(draft_id)
        conn = get_conn()
        conn.execute(f"UPDATE user_drafts SET {', '.join(sets)} WHERE id = ?", values)
        conn.commit()
    return {"ok": True}


@router.delete("/{draft_id}")
def delete_draft(draft_id: int) -> dict:
    _get_draft(draft_id)
    conn = get_conn()
    conn.execute("DELETE FROM user_drafts WHERE id = ?", (draft_id,))
    conn.commit()
    return {"ok": True}


@router.post("/{draft_id}/send")
async def send_draft(draft_id: int, files: list[UploadFile] = File(default=[])) -> dict:
    """发送草稿。收发件人与正文取自已保存的草稿内容，附件随请求上传。"""
    row = _get_draft(draft_id)
    if row["status"] != "editing":
        raise HTTPException(400, "该草稿已发送或已丢弃")

    to_list = re_split(row["to_addrs"])
    cc_list = re_split(row["cc_addrs"])
    bcc_list = re_split(row["bcc_addrs"])
    if not to_list:
        raise HTTPException(400, "收件人不能为空")

    cfg, acct = _imap_for(row["account_id"])
    if not acct.get("smtp_server"):
        raise HTTPException(400, "该账号未配置 SMTP 服务器")

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

    tmp_dir = None
    try:
        if files:
            tmp_dir = Path(tempfile.mkdtemp(prefix="nmail-send-"))
            for f in files:
                target = tmp_dir / f.filename
                with open(target, "wb") as fh:
                    fh.write(await f.read())
        sent_message = imap_client.send_email(
            cfg,
            to_list,
            cc_list,
            bcc_list,
            row["subject"],
            text,
            html,
            [str(tmp_dir / f.filename) for f in files] if tmp_dir else [],
            in_reply_to=in_reply_to,
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"发送失败：{exc}") from exc
    finally:
        if tmp_dir:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    imap_client.append_sent(cfg, sent_message)
    conn = get_conn()
    conn.execute(
        "UPDATE user_drafts SET status = 'sent', updated_at = datetime('now') WHERE id = ?",
        (draft_id,),
    )
    conn.commit()
    return {"ok": True}
