"""AI 能力 API：上下文问答、总管家问答、写作辅助、用量统计、「AI 整理」补分类。"""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.ai import profiles, tasks
from app.api.chats import append_message, require_session
from app.core.mail_html import markdown_body_html, sanitize_outgoing_html
from app.core.pipeline import classify_missing
from app.db.database import get_conn

router = APIRouter(prefix="/api/ai", tags=["ai"])


def _sse(gen):  # noqa: ANN001 — 生成器
    """把文本增量生成器包装为 SSE 响应；中途异常以 error 事件下发，前端可见。"""

    def stream():
        try:
            for delta in gen:
                yield f"data: {json.dumps({'delta': delta}, ensure_ascii=False)}\n\n"
        except Exception as exc:  # noqa: BLE001
            yield f"data: {json.dumps({'error': str(exc)[:300]}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        stream(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class ChatIn(BaseModel):
    email_id: int | None = None
    email_ids: list[int] | None = None  # 可选：多封（如搜索结果）作为上下文
    question: str
    history: list[dict] | None = None
    profile_id: str | None = None  # 可选：本次对话使用指定 AI 配置档案


class WriteIn(BaseModel):
    text: str
    op: str  # polish|formal|casual|shorten|expand|translate_zh|translate_en|custom|compose
    instruction: str | None = None
    profile_id: str | None = None
    want_html: bool = False  # 置 true 时附带 markdown→HTML 转换结果（编辑器直插）


class OrganizeIn(BaseModel):
    account_id: int | None = None
    folder: str = "INBOX"
    limit: int = 200


class ManagerChatIn(BaseModel):
    question: str
    history: list[dict] | None = None
    account_id: int | None = None
    days: int = 7
    session_id: int | None = None  # 提供时落库（会话持久化），否则保持旧的无痕行为
    profile_id: str | None = None  # 可选：本次对话使用指定 AI 配置档案


def _record_model(profile_id: str | None) -> str:
    """会话落库用的模型名：解析失败（未配置）时留空即可，不影响主流程。"""
    try:
        return profiles.resolve(profile_id).get("model") or ""
    except profiles.ProfileNotConfigured:
        return ""


def _persist_stream(gen, session_id: int, model: str):
    """包裹流式生成器：结束后把完整回复落库；中途异常保留已生成部分再抛出。"""
    chunks: list[str] = []
    try:
        for delta in gen:
            chunks.append(delta)
            yield delta
    except Exception:
        if chunks:
            append_message(session_id, "assistant", "".join(chunks), model=model)
        raise
    append_message(session_id, "assistant", "".join(chunks), model=model)


@router.post("/chat-manager")
def chat_manager(payload: ManagerChatIn) -> dict:
    """「AI 总管家」非流式版本（保留兼容）。"""
    context = _manager_context(payload)
    try:
        answer = tasks.chat_with_context(
            context, payload.question, history=payload.history,
            profile_id=payload.profile_id,
        )
    except tasks.AINotConfigured:
        raise HTTPException(400, "未配置 AI 端点，请在设置中填写") from None
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"AI 调用失败：{exc}") from exc
    if payload.session_id is not None:
        require_session(payload.session_id)
        append_message(payload.session_id, "user", payload.question)
        append_message(payload.session_id, "assistant", answer,
                       model=_record_model(payload.profile_id))
    return {"answer": answer}


@router.post("/chat-manager/stream")
def chat_manager_stream(payload: ManagerChatIn):
    """「AI 总管家」流式版本：SSE 逐段返回。"""
    context = _manager_context(payload)
    if payload.session_id is not None:
        require_session(payload.session_id)
        append_message(payload.session_id, "user", payload.question)
    try:
        gen = tasks.chat_with_context_stream(
            context, payload.question, history=payload.history,
            profile_id=payload.profile_id,
        )
    except tasks.AINotConfigured:
        raise HTTPException(400, "未配置 AI 端点，请在设置中填写") from None
    if payload.session_id is not None:
        gen = _persist_stream(gen, payload.session_id, _record_model(payload.profile_id))
    return _sse(gen)


def _manager_context(payload: ManagerChatIn) -> str:
    conn = get_conn()
    since = (datetime.now() - timedelta(days=max(1, payload.days))).isoformat(timespec="seconds")
    where = " WHERE e.date >= ?"
    params: list = [since]
    if payload.account_id is not None:
        where += " AND e.account_id = ?"
        params.append(payload.account_id)
    rows = conn.execute(
        "SELECT e.subject, e.sender_name, e.sender_email, e.date, e.category,"
        " e.importance, e.needs_reply, e.archived_local, e.snippet, a.email AS account_email"
        f" FROM emails e JOIN accounts a ON a.id = e.account_id{where}"
        " ORDER BY e.date DESC LIMIT 150",
        params,
    ).fetchall()

    lines = []
    cat_count: Counter = Counter()
    for r in rows:
        cat = r["category"] or "未分类"
        cat_count[cat] += 1
        flags = []
        if r["needs_reply"]:
            flags.append("需回复")
        if r["archived_local"]:
            flags.append("已归档")
        flags_str = f" [{'|'.join(flags)}]" if flags else ""
        snippet = (r["snippet"] or "")[:60]
        lines.append(
            f'{(r["date"] or "")[:10]} {r["account_email"]} <{r["sender_email"]}> '
            f'「{r["subject"]}」({cat}/{r["importance"] or "-"}){flags_str} {snippet}'
        )

    unread_row = conn.execute(
        f"SELECT COUNT(*) AS n FROM emails e{where} AND e.is_read = 0 AND e.archived_local = 0",
        params,
    ).fetchone()

    cats_str = "、".join(f"{k} {v}" for k, v in cat_count.most_common())
    return (
        f"邮箱最近 {payload.days} 天概况：共 {len(rows)} 封（{cats_str}），"
        f"未读 {unread_row['n']} 封。明细（新→旧，最多 150 条）：\n" + "\n".join(lines)
    )


def _build_context(email_id: int) -> tuple[str, int]:
    row = get_conn().execute(
        "SELECT subject, sender_name, sender_email, date, body_text, body_html, account_id"
        " FROM emails WHERE id = ?",
        (email_id,),
    ).fetchone()
    if not row:
        raise HTTPException(404, "邮件不存在")
    body = row["body_text"] or ""
    if not body.strip():
        from bs4 import BeautifulSoup

        body = BeautifulSoup(row["body_html"] or "", "html.parser").get_text("\n", strip=True)
    context = (
        f'主题: {row["subject"]}\n'
        f'发件人: {row["sender_name"]} <{row["sender_email"]}>\n'
        f'日期: {row["date"] or ""}\n\n{body.strip()[:6000]}'
    )
    return context, int(row["account_id"])


@router.post("/chat")
def chat(payload: ChatIn) -> dict:
    ids = payload.email_ids or ([payload.email_id] if payload.email_id else [])
    if not ids:
        raise HTTPException(400, "需要提供 email_id 或 email_ids 作为上下文")
    contexts, account_id = _chat_contexts(ids)
    try:
        answer = tasks.chat_with_context(
            "\n\n".join(contexts), payload.question,
            history=payload.history, account_id=account_id,
            profile_id=payload.profile_id,
        )
    except tasks.AINotConfigured:
        raise HTTPException(400, "未配置 AI 端点，请在设置中填写") from None
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"AI 调用失败：{exc}") from exc
    return {"answer": answer}


@router.post("/chat/stream")
def chat_stream(payload: ChatIn):
    ids = payload.email_ids or ([payload.email_id] if payload.email_id else [])
    if not ids:
        raise HTTPException(400, "需要提供 email_id 或 email_ids 作为上下文")
    contexts, account_id = _chat_contexts(ids)
    try:
        gen = tasks.chat_with_context_stream(
            "\n\n".join(contexts), payload.question,
            history=payload.history, account_id=account_id,
            profile_id=payload.profile_id,
        )
    except tasks.AINotConfigured:
        raise HTTPException(400, "未配置 AI 端点，请在设置中填写") from None
    return _sse(gen)


def _chat_contexts(ids: list[int]) -> tuple[list[str], int | None]:
    contexts = []
    account_id = None
    for eid in ids[:5]:  # 上下文最多取 5 封，防 token 失控
        ctx, account_id = _build_context(eid)
        contexts.append(f"===== 邮件 {eid} =====\n{ctx}")
    return contexts, account_id


@router.post("/write")
def write(payload: WriteIn) -> dict:
    try:
        result = tasks.write_assist(payload.text, payload.op, payload.instruction,
                                    profile_id=payload.profile_id)
    except tasks.AINotConfigured:
        raise HTTPException(400, "未配置 AI 端点，请在设置中填写") from None
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"AI 调用失败：{exc}") from exc
    resp: dict = {"text": result}
    if payload.want_html:
        html = markdown_body_html(result)
        resp["html"] = sanitize_outgoing_html(html)
    return resp


@router.post("/organize")
def organize(payload: OrganizeIn) -> dict:
    """为未分类邮件补跑分类（「AI 整理」按钮）。"""
    conn = get_conn()
    if payload.account_id is not None:
        account_ids = [payload.account_id]
    else:
        account_ids = [int(r["id"]) for r in conn.execute("SELECT id FROM accounts").fetchall()]
    total = {"classified": 0, "archived": 0, "drafts": 0, "skipped_no_ai": False}
    for aid in account_ids:
        result = classify_missing(aid, payload.folder, payload.limit)
        total["classified"] += result["classified"]
        total["archived"] += result["archived"]
        total["skipped_no_ai"] = total["skipped_no_ai"] or result["skipped_no_ai"]
    return total


@router.get("/usage")
def usage() -> dict:
    return tasks.usage_stats()
