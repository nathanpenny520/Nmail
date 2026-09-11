"""写信工作台：用户手写草稿的增删改查、附件持久化、定时与发送。

独立于 AI 待审草稿（api/drafts.py）。前端写信工作台的每个标签对应一条
user_drafts 记录，编辑内容防抖自动保存（PATCH）；附件上传即落盘
（data_dir/drafts/<id>/），发送时从磁盘读取，定时发送由调度器到期触发。
发送走 core/outbox.send_user_draft（API 与 scheduler 共用的唯一实现），
本模块只留薄壳并把 MailError 翻译为 HTTP。
"""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from app.api.deps import mail_error_to_http
from app.core import mailbox, outbox
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
    shutil.rmtree(outbox.draft_dir(draft_id), ignore_errors=True)


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
    target_dir = outbox.draft_dir(draft_id)
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

@router.post("/{draft_id}/send")
def send_draft(draft_id: int) -> dict:
    """立即发送草稿。收发件人、正文与附件均取自已保存内容。"""
    try:
        outbox.send_user_draft(draft_id)
    except mailbox.MailError as exc:
        raise mail_error_to_http(exc)
    return {"ok": True}
