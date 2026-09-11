"""待审草稿 API：列表、修改、通过（发送）、丢弃、重新生成。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.ai import tasks
from app.api.deps import mail_error_to_http
from app.core import imap_client, mailbox
from app.core.mail_html import markdown_to_email_html
from app.db.database import get_conn

router = APIRouter(prefix="/api/drafts", tags=["drafts"])

_DRAFT_JOIN = (
    "SELECT d.*, e.subject, e.sender_name, e.sender_email, e.date, e.snippet, e.message_id"
    " FROM drafts d JOIN emails e ON e.id = d.email_id"
)


class DraftUpdateIn(BaseModel):
    content: str | None = None


class DraftActionIn(BaseModel):
    action: str  # approve | discard
    content: str | None = None  # approve 时可携带最终内容


class RegenerateIn(BaseModel):
    email_id: int
    instruction: str | None = None


def _draft_dict(row) -> dict:  # noqa: ANN001
    return {
        "id": row["id"],
        "email_id": row["email_id"],
        "account_id": row["account_id"],
        "content": row["content"],
        "origin": row["origin"],
        "status": row["status"],
        "instruction": row["instruction"],
        "created_at": row["created_at"],
        "email": {
            "subject": row["subject"],
            "sender_name": row["sender_name"],
            "sender_email": row["sender_email"],
            "date": row["date"],
            "snippet": row["snippet"],
        },
    }


@router.get("")
def list_drafts(status: str = "pending") -> dict:
    if status not in ("pending", "sent", "discarded"):
        raise HTTPException(400, "status 需为 pending/sent/discarded")
    rows = get_conn().execute(
        f"{_DRAFT_JOIN} WHERE d.status = ? ORDER BY d.id DESC LIMIT 100", (status,)
    ).fetchall()
    return {"drafts": [_draft_dict(r) for r in rows]}


@router.patch("/{draft_id}")
def update_draft(draft_id: int, payload: DraftUpdateIn) -> dict:
    conn = get_conn()
    row = conn.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,)).fetchone()
    if not row:
        raise HTTPException(404, "草稿不存在")
    if row["status"] != "pending":
        raise HTTPException(400, "仅待审草稿可修改")
    conn.execute(
        "UPDATE drafts SET content = ?, updated_at = datetime('now') WHERE id = ?",
        (payload.content or "", draft_id),
    )
    conn.commit()
    return {"ok": True}


@router.post("/{draft_id}/action")
def draft_action(draft_id: int, payload: DraftActionIn) -> dict:
    conn = get_conn()
    row = conn.execute(f"{_DRAFT_JOIN} WHERE d.id = ?", (draft_id,)).fetchone()
    if not row:
        raise HTTPException(404, "草稿不存在")
    if row["status"] != "pending":
        raise HTTPException(400, "草稿已处理")

    if payload.action == "discard":
        conn.execute(
            "UPDATE drafts SET status = 'discarded', updated_at = datetime('now') WHERE id = ?",
            (draft_id,),
        )
        conn.commit()
        return {"ok": True}

    if payload.action != "approve":
        raise HTTPException(400, "action 需为 approve/discard")

    content = (payload.content or row["content"] or "").strip()
    if not content:
        raise HTTPException(400, "草稿内容为空，无法发送")

    try:
        handle = mailbox.load_account(int(row["account_id"]))
    except mailbox.MailError as exc:
        raise mail_error_to_http(exc)

    try:
        mailbox.send_message(
            handle,
            to=[row["sender_email"]],
            subject=imap_client.reply_subject(row["subject"]),
            text=content,
            html=markdown_to_email_html(content),
            in_reply_to=(row["message_id"] or "").strip() or None,
        )
    except mailbox.MailError as exc:  # smtp_missing 等
        raise mail_error_to_http(exc)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"发送失败：{exc}") from exc

    conn.execute(
        "UPDATE drafts SET status = 'sent', content = ?, updated_at = datetime('now') WHERE id = ?",
        (content, draft_id),
    )
    conn.execute("UPDATE emails SET is_read = 1 WHERE id = ?", (row["email_id"],))
    conn.commit()
    return {"ok": True}


@router.delete("/{draft_id}")
def delete_draft(draft_id: int) -> dict:
    """彻底删除草稿记录（任意状态）。"""
    conn = get_conn()
    row = conn.execute("SELECT id FROM drafts WHERE id = ?", (draft_id,)).fetchone()
    if not row:
        raise HTTPException(404, "草稿不存在")
    conn.execute("DELETE FROM drafts WHERE id = ?", (draft_id,))
    conn.commit()
    return {"ok": True}


@router.post("/{draft_id}/reopen")
def reopen_draft(draft_id: int) -> dict:
    """把已丢弃的草稿恢复为待审。"""
    conn = get_conn()
    row = conn.execute("SELECT id, status FROM drafts WHERE id = ?", (draft_id,)).fetchone()
    if not row:
        raise HTTPException(404, "草稿不存在")
    if row["status"] != "discarded":
        raise HTTPException(400, "仅已丢弃的草稿可恢复")
    conn.execute(
        "UPDATE drafts SET status = 'pending', updated_at = datetime('now') WHERE id = ?",
        (draft_id,),
    )
    conn.commit()
    return {"ok": True}


@router.post("/regenerate")
def regenerate_draft(payload: RegenerateIn) -> dict:
    """按 email_id 重新生成草稿（可带指令），覆盖现有待审草稿。"""
    conn = get_conn()
    email_row = conn.execute("SELECT * FROM emails WHERE id = ?", (payload.email_id,)).fetchone()
    if not email_row:
        raise HTTPException(404, "邮件不存在")
    account = conn.execute(
        "SELECT * FROM accounts WHERE id = ?", (email_row["account_id"],)
    ).fetchone()
    if not account:
        raise HTTPException(404, "账号不存在")

    try:
        content = tasks.generate_reply_draft(
            email_row, account["email"],
            instruction=payload.instruction, account_id=int(account["id"]),
        )
    except tasks.AINotConfigured:
        raise HTTPException(400, "未配置 AI 端点") from None
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"生成失败：{exc}") from exc

    existing = conn.execute(
        "SELECT id FROM drafts WHERE email_id = ? AND status = 'pending' ORDER BY id DESC LIMIT 1",
        (payload.email_id,),
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE drafts SET content = ?, instruction = ?, origin = 'ai',"
            " updated_at = datetime('now') WHERE id = ?",
            (content, payload.instruction, existing["id"]),
        )
        draft_id = existing["id"]
    else:
        cursor = conn.execute(
            "INSERT INTO drafts (email_id, account_id, content, origin, instruction)"
            " VALUES (?, ?, ?, 'ai', ?)",
            (payload.email_id, account["id"], content, payload.instruction),
        )
        draft_id = int(cursor.lastrowid)
    conn.commit()
    return {"ok": True, "draft_id": draft_id, "content": content}
