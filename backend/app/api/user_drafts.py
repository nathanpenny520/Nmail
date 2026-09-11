"""写信工作台：用户手写草稿的增删改查、附件持久化、定时与发送。

独立于 AI 待审草稿（api/drafts.py）。前端写信工作台的每个标签对应一条
user_drafts 记录，编辑内容防抖自动保存（PATCH）；附件上传即落盘
（data_dir/drafts/<id>/），发送时从磁盘读取，定时发送由调度器到期触发
（send_draft_now 供 API 与 scheduler 共用）。正文存 HTML，发送前消毒并
派生纯文本 alternative。
"""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from app.api.emails import _imap_for, re_split
from app.config import get_data_dir
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


class ScheduleIn(BaseModel):
    send_at: str  # ISO 本地时间（datetime-local），如 2026-09-11T15:30


def _draft_dir(draft_id: int) -> Path:
    return get_data_dir() / "drafts" / str(draft_id)


def _att_dict(row) -> dict:  # noqa: ANN001
    return {
        "id": row["id"],
        "draft_id": row["draft_id"],
        "filename": row["filename"],
        "mime": row["mime"],
        "size": row["size"],
    }


def _draft_dict(row) -> dict:  # noqa: ANN001
    atts = get_conn().execute(
        "SELECT * FROM user_draft_attachments WHERE draft_id = ? ORDER BY id", (row["id"],)
    ).fetchall()
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
        "send_at": row["send_at"],
        "attachments": [_att_dict(a) for a in atts],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _get_draft(draft_id: int):
    row = get_conn().execute("SELECT * FROM user_drafts WHERE id = ?", (draft_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "草稿不存在")
    return row


def _remove_draft_files(draft_id: int) -> None:
    shutil.rmtree(_draft_dir(draft_id), ignore_errors=True)


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
    _remove_draft_files(draft_id)  # 附件行随 FK 级联删除，磁盘文件手动清
    return {"ok": True}


# ── 附件持久化 ──────────────────────────────────────────────

@router.post("/{draft_id}/attachments")
async def upload_attachments(draft_id: int, files: list[UploadFile] = File(...)) -> dict:
    _get_draft(draft_id)
    conn = get_conn()
    target_dir = _draft_dir(draft_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    for f in files:
        cur = conn.execute(
            "INSERT INTO user_draft_attachments (draft_id, filename, mime, size, path)"
            " VALUES (?, ?, ?, ?, '')",
            (draft_id, f.filename, f.content_type or "", 0),
        )
        safe_name = Path(f.filename or "attachment").name  # 剥掉路径成分
        target = target_dir / f"{cur.lastrowid}_{safe_name}"
        data = await f.read()
        target.write_bytes(data)
        conn.execute(
            "UPDATE user_draft_attachments SET size = ?, path = ? WHERE id = ?",
            (len(data), str(target), cur.lastrowid),
        )
    conn.commit()
    return {"draft": _draft_dict(_get_draft(draft_id))}


@router.delete("/{draft_id}/attachments/{att_id}")
def delete_attachment(draft_id: int, att_id: int) -> dict:
    _get_draft(draft_id)
    row = get_conn().execute(
        "SELECT * FROM user_draft_attachments WHERE id = ? AND draft_id = ?",
        (att_id, draft_id),
    ).fetchone()
    if row is None:
        raise HTTPException(404, "附件不存在")
    conn = get_conn()
    conn.execute("DELETE FROM user_draft_attachments WHERE id = ?", (att_id,))
    conn.commit()
    try:
        Path(row["path"]).unlink(missing_ok=True)
    except OSError:
        pass
    return {"draft": _draft_dict(_get_draft(draft_id))}


# ── 定时发送 ────────────────────────────────────────────────

@router.post("/{draft_id}/schedule")
def schedule_draft(draft_id: int, payload: ScheduleIn) -> dict:
    row = _get_draft(draft_id)
    if row["status"] not in ("editing", "scheduled"):
        raise HTTPException(400, "该草稿已发送或已丢弃")
    try:
        when = datetime.fromisoformat(payload.send_at)
    except ValueError as exc:
        raise HTTPException(400, "时间格式无效") from exc
    if when <= datetime.now():
        raise HTTPException(400, "定时时间必须晚于当前时间")
    conn = get_conn()
    conn.execute(
        "UPDATE user_drafts SET status = 'scheduled', send_at = ?, updated_at = datetime('now')"
        " WHERE id = ?",
        (payload.send_at, draft_id),
    )
    conn.commit()
    return {"draft": _draft_dict(_get_draft(draft_id))}


@router.post("/{draft_id}/unschedule")
def unschedule_draft(draft_id: int) -> dict:
    row = _get_draft(draft_id)
    if row["status"] != "scheduled":
        raise HTTPException(400, "该草稿未在定时队列中")
    conn = get_conn()
    conn.execute(
        "UPDATE user_drafts SET status = 'editing', send_at = NULL, updated_at = datetime('now')"
        " WHERE id = ?",
        (draft_id,),
    )
    conn.commit()
    return {"draft": _draft_dict(_get_draft(draft_id))}


# ── 发送 ────────────────────────────────────────────────────

def send_draft_now(draft_id: int) -> None:
    """发送草稿（同步核心，API 与调度器共用）。失败抛 HTTPException。"""
    row = _get_draft(draft_id)
    if row["status"] not in ("editing", "scheduled"):
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

    paths = [
        r["path"]
        for r in get_conn().execute(
            "SELECT path FROM user_draft_attachments WHERE draft_id = ? ORDER BY id", (draft_id,)
        ).fetchall()
        if Path(r["path"]).exists()
    ]

    try:
        sent_message = imap_client.send_email(
            cfg, to_list, cc_list, bcc_list, row["subject"], text, html, paths,
            in_reply_to=in_reply_to,
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"发送失败：{exc}") from exc

    imap_client.append_sent(cfg, sent_message)
    conn = get_conn()
    conn.execute(
        "UPDATE user_drafts SET status = 'sent', send_at = NULL, updated_at = datetime('now')"
        " WHERE id = ?",
        (draft_id,),
    )
    conn.commit()
    _remove_draft_files(draft_id)


@router.post("/{draft_id}/send")
def send_draft(draft_id: int) -> dict:
    """立即发送草稿。收发件人、正文与附件均取自已保存内容。"""
    send_draft_now(draft_id)
    return {"ok": True}
