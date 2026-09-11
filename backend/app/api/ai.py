"""AI 能力 API：上下文问答、总管家问答、写作辅助、用量统计、「AI 整理」补分类。"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.ai import tasks
from app.core.pipeline import classify_missing
from app.db.database import get_conn

router = APIRouter(prefix="/api/ai", tags=["ai"])


class ChatIn(BaseModel):
    email_id: int | None = None
    email_ids: list[int] | None = None  # 可选：多封（如搜索结果）作为上下文
    question: str
    history: list[dict] | None = None


class WriteIn(BaseModel):
    text: str
    op: str  # polish|formal|casual|shorten|expand|translate_zh|translate_en|custom
    instruction: str | None = None


class OrganizeIn(BaseModel):
    account_id: int | None = None
    folder: str = "INBOX"
    limit: int = 200


class ManagerChatIn(BaseModel):
    question: str
    history: list[dict] | None = None
    account_id: int | None = None
    days: int = 7


@router.post("/chat-manager")
def chat_manager(payload: ManagerChatIn) -> dict:
    """「AI 总管家」：基于最近邮件全量上下文回答全局问题。"""
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
    context = (
        f"邮箱最近 {payload.days} 天概况：共 {len(rows)} 封（{cats_str}），"
        f"未读 {unread_row['n']} 封。明细（新→旧，最多 150 条）：\n" + "\n".join(lines)
    )
    try:
        answer = tasks.chat_with_context(
            context, payload.question, history=payload.history,
        )
    except tasks.AINotConfigured:
        raise HTTPException(400, "未配置 AI 端点，请在设置中填写") from None
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"AI 调用失败：{exc}") from exc
    return {"answer": answer}


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
    contexts = []
    account_id = None
    for eid in ids[:5]:  # 上下文最多取 5 封，防 token 失控
        ctx, account_id = _build_context(eid)
        contexts.append(f"===== 邮件 {eid} =====\n{ctx}")
    try:
        answer = tasks.chat_with_context(
            "\n\n".join(contexts), payload.question,
            history=payload.history, account_id=account_id,
        )
    except tasks.AINotConfigured:
        raise HTTPException(400, "未配置 AI 端点，请在设置中填写") from None
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"AI 调用失败：{exc}") from exc
    return {"answer": answer}


@router.post("/write")
def write(payload: WriteIn) -> dict:
    try:
        result = tasks.write_assist(payload.text, payload.op, payload.instruction)
    except tasks.AINotConfigured:
        raise HTTPException(400, "未配置 AI 端点，请在设置中填写") from None
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"AI 调用失败：{exc}") from exc
    return {"text": result}


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
