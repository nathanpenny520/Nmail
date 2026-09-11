"""邮件 API：列表/搜索、详情（安全 HTML）、状态操作、发送、附件下载。"""
from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.core import imap_client
from app.core.mail_html import markdown_to_email_html, sanitize_email_html
from app.db.database import get_conn
from app.security import get_secret

router = APIRouter(prefix="/api", tags=["emails"])

LIST_COLUMNS = (
    "e.id, e.account_id, a.email AS account_email, a.color AS account_color,"
    " e.folder, e.uid, e.subject, e.sender_name, e.sender_email, e.date, e.snippet,"
    " e.is_read, e.starred, e.archived_local, e.has_attachments,"
    " e.category, e.importance, e.needs_reply, e.reply_reason"
)


class BatchActionIn(BaseModel):
    ids: list[int]
    action: str  # read|unread|star|unstar|archive|unarchive|trash|move
    folder: str | None = None  # action=move 的目标文件夹


@router.post("/emails/batch-action")
def batch_action(payload: BatchActionIn) -> dict:
    """批量操作：归档类纯本地；IMAP 类按账号分组共用连接，文件夹内合并打标。"""
    if not payload.ids:
        raise HTTPException(400, "ids 为空")
    ids = list(dict.fromkeys(payload.ids))
    action = payload.action
    if action not in ("read", "unread", "star", "unstar", "archive", "unarchive", "trash", "move"):
        raise HTTPException(400, f"未知操作：{action}")
    if action == "move" and not payload.folder:
        raise HTTPException(400, "move 需要目标文件夹")

    conn = get_conn()
    placeholders = ",".join("?" for _ in ids)
    rows = conn.execute(
        f"SELECT e.id, e.account_id, e.folder, e.uid, a.email AS account_email,"
        f" a.imap_server, a.imap_port FROM emails e"
        f" JOIN accounts a ON a.id = e.account_id WHERE e.id IN ({placeholders})",
        ids,
    ).fetchall()

    # 归档类：仅本地标记
    if action in ("archive", "unarchive"):
        value = 1 if action == "archive" else 0
        conn.execute(
            f"UPDATE emails SET archived_local = ? WHERE id IN ({placeholders})",
            (value, *ids),
        )
        conn.commit()
        return {"ok": True, "updated": len(rows), "failed": 0}

    # IMAP 类：按账号分组，每账号一条连接
    by_account: dict[int, list] = {}
    for r in rows:
        by_account.setdefault(r["account_id"], []).append(r)

    flag_map = {
        "read": (imap_client.SEEN_FLAG, True),
        "unread": (imap_client.SEEN_FLAG, False),
        "star": (imap_client.FLAGGED_FLAG, True),
        "unstar": (imap_client.FLAGGED_FLAG, False),
    }

    updated = 0
    failed = 0
    for account_id, account_rows in by_account.items():
        first = account_rows[0]
        password = get_secret(f"account_pwd:{account_id}")
        if not password:
            failed += len(account_rows)
            continue
        cfg = imap_client.MailConfig(
            email=first["account_email"], password=password,
            imap_server=first["imap_server"], imap_port=int(first["imap_port"]),
        )
        try:
            with imap_client.connect_imap(cfg) as mb:
                if action in flag_map:
                    flag, value = flag_map[action]
                    by_folder: dict[str, list[str]] = {}
                    for r in account_rows:
                        by_folder.setdefault(r["folder"], []).append(str(r["uid"]))
                    for folder, uid_list in by_folder.items():
                        mb.folder.set(folder)
                        mb.flag(uid_list, [flag], value)
                    id_list = [r["id"] for r in account_rows]
                    col = "is_read" if action in ("read", "unread") else "starred"
                    val = 1 if action in ("read", "star") else 0
                    ph = ",".join("?" for _ in id_list)
                    conn.execute(
                        f"UPDATE emails SET {col} = ? WHERE id IN ({ph})",
                        (val, *id_list),
                    )
                elif action == "trash":
                    for r in account_rows:
                        imap_client.trash_email(mb, r["folder"], r["uid"])
                    id_list = [r["id"] for r in account_rows]
                    ph = ",".join("?" for _ in id_list)
                    conn.execute(f"DELETE FROM emails WHERE id IN ({ph})", id_list)
                elif action == "move":
                    for r in account_rows:
                        new_uid = imap_client.move_email(mb, r["folder"], r["uid"], payload.folder or "")
                        if new_uid is None:
                            # 服务器未回新 UID 时不能把旧 uid 带进新文件夹：
                            # 撞 (account, folder, uid) UNIQUE 且增量同步会跳过它——
                            # 删除本地行，交下次增量同步按服务器状态重建
                            conn.execute("DELETE FROM emails WHERE id = ?", (r["id"],))
                        else:
                            conn.execute(
                                "UPDATE emails SET folder = ?, uid = ? WHERE id = ?",
                                (payload.folder, new_uid, r["id"]),
                            )
            updated += len(account_rows)
        except Exception:  # noqa: BLE001 — 单账号失败不影响其他账号
            failed += len(account_rows)
    conn.commit()
    return {"ok": failed == 0, "updated": updated, "failed": failed}


class EmailActionIn(BaseModel):
    action: str  # read|unread|star|unstar|archive|unarchive|trash|move
    folder: str | None = None  # action=move 时的目标文件夹


@router.get("/emails")
def list_emails(
    account_id: int | None = None,
    folder: str | None = None,
    q: str | None = None,
    is_read: bool | None = None,
    starred: bool | None = None,
    category: str | None = None,
    archived: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    where: list[str] = []
    params: list = []

    if category:
        where.append("e.category = ?")
        params.append(category)

    if q and q.strip():
        # 搜索时忽略文件夹/归档过滤，覆盖该（或全部）账号的所有文件夹
        query = q.strip().replace('"', '""')
        if len(query) >= 3:
            where.append("e.id IN (SELECT rowid FROM emails_fts WHERE emails_fts MATCH ?)")
            params.append(f'"{query}"')
        else:
            like = f"%{query}%"
            where.append(
                "(e.subject LIKE ? OR e.body_text LIKE ? OR e.sender_email LIKE ?"
                " OR e.sender_name LIKE ?)"
            )
            params.extend([like, like, like, like])
    else:
        if folder:
            where.append("e.folder = ?")
            params.append(folder)
        elif not archived:
            where.append("e.folder = 'INBOX'")
        where.append("e.archived_local = ?")
        params.append(1 if archived else 0)

    if account_id is not None:
        where.append("e.account_id = ?")
        params.append(account_id)
    if is_read is not None:
        where.append("e.is_read = ?")
        params.append(1 if is_read else 0)
    if starred is not None:
        where.append("e.starred = ?")
        params.append(1 if starred else 0)

    clause = (" WHERE " + " AND ".join(where)) if where else ""
    conn = get_conn()
    total = conn.execute(
        f"SELECT COUNT(*) AS n FROM emails e{clause}", params
    ).fetchone()["n"]
    rows = conn.execute(
        f"SELECT {LIST_COLUMNS} FROM emails e JOIN accounts a ON a.id = e.account_id"
        f"{clause} ORDER BY COALESCE(e.date_sort, e.date) IS NULL, COALESCE(e.date_sort, e.date) DESC, e.uid DESC LIMIT ? OFFSET ?",
        [*params, limit, offset],
    ).fetchall()
    return {"total": total, "items": [_summary(r) for r in rows]}


def _summary(r) -> dict:  # noqa: ANN001
    return {
        "id": r["id"],
        "account_id": r["account_id"],
        "account_email": r["account_email"],
        "account_color": r["account_color"],
        "folder": r["folder"],
        "uid": r["uid"],
        "subject": r["subject"],
        "sender_name": r["sender_name"],
        "sender_email": r["sender_email"],
        "date": r["date"],
        "snippet": r["snippet"],
        "is_read": bool(r["is_read"]),
        "starred": bool(r["starred"]),
        "archived_local": bool(r["archived_local"]),
        "has_attachments": bool(r["has_attachments"]),
        "category": r["category"] or "",
        "importance": r["importance"] or "",
        "needs_reply": bool(r["needs_reply"]),
        "reply_reason": r["reply_reason"] or "",
    }


def _get_email_row(email_id: int):
    row = get_conn().execute(
        f"SELECT {LIST_COLUMNS}, e.body_text, e.body_html, e.recipients, e.cc, e.remote_img_count"
        " FROM emails e JOIN accounts a ON a.id = e.account_id WHERE e.id = ?",
        (email_id,),
    ).fetchone()
    if not row:
        raise HTTPException(404, "邮件不存在")
    return row


def _sender_image_trusted(sender_email: str) -> bool:
    """发件人是否在「图片信任白名单」（邮箱或 @域名）。"""
    email = (sender_email or "").strip().lower()
    if not email:
        return False
    rows = get_conn().execute(
        "SELECT pattern FROM sender_lists WHERE list_type = 'image_trust'"
    ).fetchall()
    for r in rows:
        pattern = r["pattern"].lower()
        if pattern.startswith("@"):
            if email.endswith(pattern):
                return True
        elif email == pattern:
            return True
    return False


@router.get("/emails/{email_id}")
def get_email(email_id: int, images: bool = False) -> dict:
    row = _get_email_row(email_id)

    attachments = get_conn().execute(
        "SELECT id, filename, mime, size, path, cid FROM attachments WHERE email_id = ? ORDER BY id",
        (email_id,),
    ).fetchall()
    cid_map = {
        a["cid"]: (a["path"], a["mime"])
        for a in attachments
        if a["cid"]
    }

    # 放行条件（任一）：URL 显式请求 / 全局设置放行 / 发件人在图片信任白名单
    from app.db.database import get_setting

    allow_images = (
        images
        or bool(get_setting("allow_remote_images", False))
        or _sender_image_trusted(row["sender_email"])
    )

    body_html = row["body_html"] or ""
    html_clean = None
    blocked = 0
    if body_html:
        html_clean, blocked = sanitize_email_html(
            body_html, allow_remote_images=allow_images, cid_map=cid_map
        )

    return {
        **_summary(row),
        "recipients": json.loads(row["recipients"] or "[]"),
        "cc": json.loads(row["cc"] or "[]"),
        "body_text": row["body_text"],
        "body_html": html_clean,
        "remote_blocked": blocked,
        "remote_img_count": row["remote_img_count"],
        "attachments": [
            {
                "id": a["id"],
                "filename": a["filename"],
                "mime": a["mime"],
                "size": a["size"],
                "download_url": f"/api/attachments/{a['id']}/download",
            }
            for a in attachments
        ],
    }


def _imap_for(account_id: int) -> tuple[imap_client.MailConfig, dict]:
    row = get_conn().execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
    if not row:
        raise HTTPException(404, "账号不存在")
    password = get_secret(f"account_pwd:{account_id}")
    if not password:
        raise HTTPException(400, "缺少密码凭证")
    cfg = imap_client.MailConfig(
        email=row["email"], password=password,
        imap_server=row["imap_server"], imap_port=int(row["imap_port"]),
        smtp_server=row["smtp_server"], smtp_port=int(row["smtp_port"]),
    )
    return cfg, {"email": row["email"], "smtp_server": row["smtp_server"], "smtp_port": row["smtp_port"]}


@router.post("/emails/{email_id}/action")
def email_action(email_id: int, payload: EmailActionIn) -> dict:
    row = _get_email_row(email_id)
    action = payload.action

    if action in ("archive", "unarchive"):
        # 本地归档视图：仅改本地标记，服务器邮件不动
        value = 1 if action == "archive" else 0
        conn = get_conn()
        conn.execute("UPDATE emails SET archived_local = ? WHERE id = ?", (value, email_id))
        conn.commit()
        return {"ok": True}

    cfg, _acct = _imap_for(row["account_id"])
    new_uid: int | None = None
    try:
        with imap_client.connect_imap(cfg) as mb:
            if action == "read":
                imap_client.set_flag(mb, row["folder"], row["uid"], imap_client.SEEN_FLAG, True)
            elif action == "unread":
                imap_client.set_flag(mb, row["folder"], row["uid"], imap_client.SEEN_FLAG, False)
            elif action == "star":
                imap_client.set_flag(mb, row["folder"], row["uid"], imap_client.FLAGGED_FLAG, True)
            elif action == "unstar":
                imap_client.set_flag(mb, row["folder"], row["uid"], imap_client.FLAGGED_FLAG, False)
            elif action == "trash":
                imap_client.trash_email(mb, row["folder"], row["uid"])
            elif action == "move":
                if not payload.folder:
                    raise HTTPException(400, "move 需要目标文件夹")
                new_uid = imap_client.move_email(mb, row["folder"], row["uid"], payload.folder)
            else:
                raise HTTPException(400, f"未知操作：{action}")
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 — 服务器端失败时不做本地变更
        raise HTTPException(502, f"服务器操作失败：{exc}") from exc

    conn = get_conn()
    if action == "read":
        conn.execute("UPDATE emails SET is_read = 1 WHERE id = ?", (email_id,))
    elif action == "unread":
        conn.execute("UPDATE emails SET is_read = 0 WHERE id = ?", (email_id,))
    elif action == "star":
        conn.execute("UPDATE emails SET starred = 1 WHERE id = ?", (email_id,))
    elif action == "unstar":
        conn.execute("UPDATE emails SET starred = 0 WHERE id = ?", (email_id,))
    elif action == "trash":
        conn.execute("DELETE FROM emails WHERE id = ?", (email_id,))
    elif action == "move":
        if new_uid is None:
            # 拿不到新 UID 时旧 uid 写进新文件夹会撞 UNIQUE 且被增量跳过——删行重建
            conn.execute("DELETE FROM emails WHERE id = ?", (email_id,))
        else:
            conn.execute(
                "UPDATE emails SET folder = ?, uid = ? WHERE id = ?",
                (payload.folder, new_uid, email_id),
            )
    conn.commit()
    return {"ok": True}


@router.post("/emails/send")
async def send_email_endpoint(
    account_id: int = Form(...),
    to: str = Form(...),
    cc: str = Form(""),
    bcc: str = Form(""),
    subject: str = Form(...),
    body: str = Form(...),
    files: list[UploadFile] = File(default=[]),
) -> dict:
    cfg, acct = _imap_for(account_id)
    if not acct.get("smtp_server"):
        raise HTTPException(400, "该账号未配置 SMTP 服务器")
    to_list = [x.strip() for x in re_split(to)]
    cc_list = [x.strip() for x in re_split(cc)] if cc else []
    bcc_list = [x.strip() for x in re_split(bcc)] if bcc else []
    if not to_list:
        raise HTTPException(400, "收件人不能为空")

    tmp_dir = Path(tempfile.mkdtemp(prefix="nmail-send-"))
    paths: list[str] = []
    try:
        for f in files:
            target = tmp_dir / f.filename
            with open(target, "wb") as fh:
                fh.write(await f.read())
            paths.append(str(target))
        html = markdown_to_email_html(body)
        sent_message = imap_client.send_email(
            cfg, to_list, cc_list, bcc_list, subject, body, html, paths
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"发送失败：{exc}") from exc
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    imap_client.append_sent(cfg, sent_message)
    return {"ok": True}


def re_split(raw: str) -> list[str]:
    return [x for x in raw.replace(";", ",").split(",") if x.strip()]


@router.get("/attachments/{attachment_id}/download")
def download_attachment(attachment_id: int) -> FileResponse:
    row = get_conn().execute(
        "SELECT filename, mime, path FROM attachments WHERE id = ?", (attachment_id,)
    ).fetchone()
    if not row or not Path(row["path"]).exists():
        raise HTTPException(404, "附件不存在")
    return FileResponse(
        row["path"],
        filename=row["filename"],
        media_type=row["mime"] or "application/octet-stream",
    )
