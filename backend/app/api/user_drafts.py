"""草稿统一 API（v0.4 P3，REDESIGN_PLAN §5.1）：手写 + AI 待审共用 user_drafts。

status 全集：editing / scheduled / pending_review（AI 待审）/ sent / discarded；
origin 区分 ai / human。原 api/drafts.py 的批准发送（走 outbox 同一通路）、
丢弃/恢复、带指令重写并入此处；旧接口已退役。前端写信工作台的每个标签对应
一条 user_drafts 记录，编辑内容防抖自动保存（PATCH）；附件上传即落盘
（data_dir/drafts/<id>/），定时发送由调度器到期触发。
"""
from __future__ import annotations

import shutil
from contextlib import suppress
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from app.ai import tasks
from app.api.deps import ai_result_or_http, mail_error_to_http
from app.core import imap_client, mailbox, outbox
from app.core.mail_html import markdown_to_email_html
from app.db.database import get_conn

router = APIRouter(prefix="/api/user-drafts", tags=["user-drafts"])

_UPDATABLE = ("account_id", "mode", "in_reply_to", "to_addrs", "cc_addrs", "bcc_addrs", "subject", "body_html")

DRAFT_STATUSES = ("editing", "scheduled", "pending_review", "sent", "discarded")

_DRAFT_JOIN = (
    "SELECT d.*, e.subject AS email_subject, e.sender_name AS email_sender_name,"
    " e.sender_email AS email_sender_email, e.date AS email_date, e.snippet AS email_snippet"
    " FROM user_drafts d LEFT JOIN emails e ON e.id = d.in_reply_to"
)


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
    email_ctx = None
    if row["in_reply_to"] and row["email_subject"] is not None:
        email_ctx = {
            "subject": row["email_subject"],
            "sender_name": row["email_sender_name"],
            "sender_email": row["email_sender_email"],
            "date": row["email_date"],
            "snippet": row["email_snippet"],
        }
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
        "origin": row["origin"],
        "instruction": row["instruction"],
        "send_at": row["send_at"],
        "attachments": [_att_dict(a) for a in atts],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "email": email_ctx,
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
    """按状态列草稿（v0.4 状态全集见 DRAFT_STATUSES，含 AI 待审 pending_review）。"""
    if status not in DRAFT_STATUSES:
        raise HTTPException(400, f"status 需为 {'/'.join(DRAFT_STATUSES)}")
    rows = get_conn().execute(
        f"{_DRAFT_JOIN} WHERE d.status = ? ORDER BY d.updated_at DESC LIMIT 200",
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
async def upload_attachments(draft_id: int, files: list[UploadFile] = File(...)) -> dict:  # noqa: B008 — FastAPI 依赖注入惯用法
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
    with suppress(OSError):
        Path(row["path"]).unlink(missing_ok=True)
    return {"draft": _draft_dict(_get_draft(draft_id))}


# ── 定时发送 ────────────────────────────────────────────────

@router.post("/{draft_id}/schedule")
def schedule_draft(draft_id: int, payload: ScheduleIn) -> dict:
    row = _get_draft(draft_id)
    if row["status"] not in ("editing", "scheduled", "pending_review"):
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
    # 回到来源态：AI 待审回 pending_review，手写回 editing
    back = "pending_review" if row["origin"] == "ai" else "editing"
    conn = get_conn()
    conn.execute(
        "UPDATE user_drafts SET status = ?, send_at = NULL, updated_at = datetime('now')"
        " WHERE id = ?",
        (back, draft_id),
    )
    conn.commit()
    return {"draft": _draft_dict(_get_draft(draft_id))}


# ── 待审流转（v0.4：原 api/drafts.py 能力并入）──────────────────

@router.post("/{draft_id}/discard")
def discard_draft(draft_id: int) -> dict:
    row = _get_draft(draft_id)
    if row["status"] not in ("pending_review", "editing"):
        raise HTTPException(400, "仅待审/编辑中的草稿可丢弃")
    conn = get_conn()
    conn.execute(
        "UPDATE user_drafts SET status = 'discarded', updated_at = datetime('now') WHERE id = ?",
        (draft_id,),
    )
    conn.commit()
    return {"draft": _draft_dict(_get_draft(draft_id))}


@router.post("/{draft_id}/reopen")
def reopen_draft(draft_id: int) -> dict:
    """把已丢弃的草稿恢复为来源态（AI→待审，手写→编辑中）。"""
    row = _get_draft(draft_id)
    if row["status"] != "discarded":
        raise HTTPException(400, "仅已丢弃的草稿可恢复")
    back = "pending_review" if row["origin"] == "ai" else "editing"
    conn = get_conn()
    conn.execute(
        "UPDATE user_drafts SET status = ?, updated_at = datetime('now') WHERE id = ?",
        (back, draft_id),
    )
    conn.commit()
    return {"draft": _draft_dict(_get_draft(draft_id))}


class RegenerateIn(BaseModel):
    instruction: str | None = None


class RegenerateForEmailIn(BaseModel):
    email_id: int
    instruction: str | None = None


@router.post("/regenerate-for-email")
def regenerate_for_email(payload: RegenerateForEmailIn) -> dict:
    """邮件视图一键拟稿（可带指令）：该邮件已有待审草稿则覆盖正文，否则新建。
    （原 /api/drafts/regenerate 同能力，v0.4 P3 迁入）"""
    conn = get_conn()
    email_row = conn.execute("SELECT * FROM emails WHERE id = ?", (payload.email_id,)).fetchone()
    if not email_row:
        raise HTTPException(404, "邮件不存在")
    account = conn.execute(
        "SELECT * FROM accounts WHERE id = ?", (email_row["account_id"],)
    ).fetchone()
    if not account:
        raise HTTPException(404, "账号不存在")

    content = ai_result_or_http(lambda: tasks.generate_reply_draft(
        email_row, account["email"],
        instruction=payload.instruction, account_id=int(account["id"]),
    ))

    existing = conn.execute(
        "SELECT id FROM user_drafts WHERE in_reply_to = ? AND status = 'pending_review'"
        " ORDER BY id DESC LIMIT 1",
        (payload.email_id,),
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE user_drafts SET body_html = ?, instruction = ?, updated_at = datetime('now')"
            " WHERE id = ?",
            (markdown_to_email_html(content), payload.instruction, existing["id"]),
        )
        draft_id = int(existing["id"])
    else:
        cursor = conn.execute(
            "INSERT INTO user_drafts (account_id, mode, in_reply_to, to_addrs, subject,"
            " body_html, status, origin, instruction) VALUES (?, 'reply', ?, ?, ?, ?,"
            " 'pending_review', 'ai', ?)",
            (
                account["id"],
                payload.email_id,
                email_row["sender_email"] or "",
                imap_client.reply_subject(email_row["subject"] or ""),
                markdown_to_email_html(content),
                payload.instruction,
            ),
        )
        draft_id = int(cursor.lastrowid)
    conn.commit()
    return {"ok": True, "draft": _draft_dict(_get_draft(draft_id))}


@router.post("/{draft_id}/regenerate")
def regenerate_draft(draft_id: int, payload: RegenerateIn) -> dict:
    """带指令重写 AI 待审草稿（覆盖正文），与原 /api/drafts/regenerate 同能力。"""
    row = _get_draft(draft_id)
    if row["status"] != "pending_review":
        raise HTTPException(400, "仅待审草稿可重写")
    if not row["in_reply_to"]:
        raise HTTPException(400, "该草稿未关联原邮件，无法重写")
    email_row = get_conn().execute(
        "SELECT * FROM emails WHERE id = ?", (row["in_reply_to"],)
    ).fetchone()
    account = get_conn().execute(
        "SELECT * FROM accounts WHERE id = ?", (row["account_id"],)
    ).fetchone()
    if not email_row or not account:
        raise HTTPException(404, "原邮件或账号不存在")

    content = ai_result_or_http(lambda: tasks.generate_reply_draft(
        email_row, account["email"],
        instruction=payload.instruction, account_id=int(account["id"]),
    ))
    conn = get_conn()
    conn.execute(
        "UPDATE user_drafts SET body_html = ?, instruction = ?, updated_at = datetime('now')"
        " WHERE id = ?",
        (markdown_to_email_html(content), payload.instruction, draft_id),
    )
    conn.commit()
    return {"ok": True, "draft": _draft_dict(_get_draft(draft_id))}


# ── 发送 ────────────────────────────────────────────────────

@router.post("/{draft_id}/send")
def send_draft(draft_id: int) -> dict:
    """立即发送草稿。收发件人、正文与附件均取自已保存内容。"""
    try:
        outbox.send_user_draft(draft_id)
    except mailbox.MailError as exc:
        raise mail_error_to_http(exc) from exc
    return {"ok": True}
