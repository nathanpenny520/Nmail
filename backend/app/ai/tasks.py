"""AI 任务实现：批量分类、生成回复草稿、上下文问答、写作辅助。

统一通过 llm.chat 调用并写入 ai_logs；未配置 AI 端点时抛 AINotConfigured，
由调用方决定降级行为。
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from app.ai import llm, prompts
from app.db.database import get_conn, get_setting
from app.security import get_secret

logger = logging.getLogger(__name__)


class AINotConfigured(Exception):
    pass


def _ai_config() -> tuple[str, str, str]:
    base_url = (get_setting("ai_base_url", "") or "").strip()
    model = (get_setting("ai_model", "") or "").strip()
    api_key = get_secret("ai_api_key")
    if not base_url or not model:
        raise AINotConfigured("未配置 AI 端点，请在 设置-AI 端点 中填写")
    return base_url, model, api_key


def log_usage(task_type: str, model: str, prompt_tokens: int, completion_tokens: int,
              ok: bool, summary: str = "", account_id: int | None = None) -> None:
    conn = get_conn()
    conn.execute(
        "INSERT INTO ai_logs (task_type, account_id, model, prompt_tokens,"
        " completion_tokens, ok, summary) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (task_type, account_id, model, prompt_tokens, completion_tokens,
         1 if ok else 0, summary[:200]),
    )
    conn.commit()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _extract_json(text: str) -> Any:
    """从模型输出中稳健提取 JSON（容忍代码块包裹和前后杂讯）。"""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.+?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # 尝试截取第一个 [ 或 { 到最后一个 ] 或 }
        for start_ch, end_ch in (("[", "]"), ("{", "}")):
            start, end = text.find(start_ch), text.rfind(end_ch)
            if start != -1 and end > start:
                try:
                    return json.loads(text[start : end + 1])
                except json.JSONDecodeError:
                    continue
        raise


def classify_batch(items: list[dict], account_id: int | None = None) -> list[dict]:
    """批量分类邮件。items: [{id, subject, sender, body_head}]，返回同序结果列表。

    单封解析失败时跳过并记日志，不影响其他邮件。
    """
    base_url, model, api_key = _ai_config()
    email_lines = []
    for it in items:
        body = (it["body_head"] or "").replace("\n", " ").strip()
        email_lines.append(
            f'--- id={it["id"]} ---\n发件人: {it["sender"]}\n主题: {it["subject"]}\n正文: {body}'
        )
    user = prompts.CLASSIFY_USER_TEMPLATE.format(count=len(items), emails="\n".join(email_lines))

    try:
        text, usage = llm.chat(base_url, model, api_key, prompts.CLASSIFY_SYSTEM, user)
        log_usage("classify", model,
                  usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0),
                  True, f"{len(items)} 封", account_id)
    except Exception as exc:  # noqa: BLE001
        log_usage("classify", model, 0, 0, False, str(exc)[:200], account_id)
        raise

    try:
        data = _extract_json(text)
        results = {int(r["id"]): r for r in data if isinstance(r, dict) and "id" in r}
    except Exception as exc:  # noqa: BLE001
        logger.warning("classify parse failed: %s; raw=%s", exc, text[:300])
        return []

    out = []
    for it in items:
        r = results.get(int(it["id"]))
        if not r:
            continue
        category = r.get("category", "")
        if category not in ("work", "personal", "notification", "verification", "promo", "social"):
            continue
        importance = r.get("importance", "normal")
        if importance not in ("critical", "high", "normal", "low"):
            importance = "normal"
        out.append({
            "id": int(it["id"]),
            "category": category,
            "importance": importance,
            "needs_reply": bool(r.get("needs_reply")),
            "reason": str(r.get("reason", ""))[:120],
        })
    return out


def generate_reply_draft(
    email_row,  # noqa: ANN001 — emails 表行
    my_email: str,
    instruction: str | None = None,
    account_id: int | None = None,
) -> str:
    """为一封来信生成回复草稿正文（Markdown）；已学习 Tone DNA 时注入风格。"""
    base_url, model, api_key = _ai_config()
    system = prompts.DRAFT_SYSTEM
    if account_id is not None:
        row = get_conn().execute(
            "SELECT tone_dna FROM accounts WHERE id = ?", (account_id,)
        ).fetchone()
        if row and row["tone_dna"]:
            system += f"\n\n用户的写作风格参考（尽量贴近模仿）：{row['tone_dna']}"
    body = email_row["body_text"] or ""
    if not body.strip():
        from bs4 import BeautifulSoup

        body = BeautifulSoup(email_row["body_html"] or "", "html.parser").get_text("\n", strip=True)
    body = body.strip()[:4000]

    user = prompts.DRAFT_USER_TEMPLATE.format(
        my_email=my_email,
        sender=email_row["sender_name"] or email_row["sender_email"],
        sender_email=email_row["sender_email"],
        subject=email_row["subject"],
        date=email_row["date"] or "",
        body=body or "（正文为空）",
    )
    if instruction:
        user += f"\n\n用户的额外要求：{instruction}"

    try:
        text, usage = llm.chat(base_url, model, api_key, system, user)
        log_usage("draft", model,
                  usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0),
                  True, email_row["subject"][:80], account_id)
    except Exception as exc:  # noqa: BLE001
        log_usage("draft", model, 0, 0, False, str(exc)[:200], account_id)
        raise
    return text.strip()


def chat_with_context(
    context_text: str,
    question: str,
    history: list[dict] | None = None,
    account_id: int | None = None,
) -> str:
    """基于邮件上下文回答问题（非流式）。history: [{role, content}]"""
    base_url, model, api_key = _ai_config()
    messages = _chat_messages(context_text, question, history)
    try:
        text, usage = llm.chat_messages(base_url, model, api_key, messages)
        log_usage("chat", model,
                  usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0),
                  True, question[:80], account_id)
    except Exception as exc:  # noqa: BLE001
        log_usage("chat", model, 0, 0, False, str(exc)[:200], account_id)
        raise
    return text.strip()


def _chat_messages(context_text: str, question: str, history: list[dict] | None) -> list[dict]:
    messages: list[dict] = [{"role": "system", "content": prompts.CHAT_SYSTEM}]
    if history:
        messages.extend(history[-6:])
    messages.append({
        "role": "user",
        "content": f"【邮件上下文】\n{context_text[:8000]}\n\n【问题】{question}",
    })
    return messages


def chat_with_context_stream(
    context_text: str,
    question: str,
    history: list[dict] | None = None,
    account_id: int | None = None,
):
    """流式版问答：返回一个 yield 文本增量的生成器；结束时写用量日志。"""
    base_url, model, api_key = _ai_config()
    messages = _chat_messages(context_text, question, history)
    usage: dict = {"prompt_tokens": 0, "completion_tokens": 0}

    def generate():
        parts: list[str] = []
        try:
            for delta in llm.iter_deltas(base_url, model, api_key, messages, usage_out=usage):
                parts.append(delta)
                yield delta
        except Exception as exc:  # noqa: BLE001
            log_usage("chat", model, usage.get("prompt_tokens", 0),
                      usage.get("completion_tokens", 0), False, str(exc)[:200], account_id)
            raise
        log_usage("chat", model, usage.get("prompt_tokens", 0),
                  usage.get("completion_tokens", 0), True, question[:80], account_id)

    return generate()


def write_assist(text: str, op: str, instruction: str | None = None) -> str:
    """写作辅助：润色/正式/随意/缩短/扩充/翻译。"""
    base_url, model, api_key = _ai_config()
    if op == "custom":
        head = instruction or "润色"
    else:
        head = prompts.WRITE_OPS.get(op)
        if not head:
            raise ValueError(f"未知写作操作：{op}")
    user = prompts.WRITE_USER_TEMPLATE.format(instruction=head, text=text[:6000])
    try:
        result, usage = llm.chat(base_url, model, api_key,
                                 "你是写作助手，只输出改写结果本身，不要解释。", user)
        log_usage("write", model,
                  usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0),
                  True, op, None)
    except Exception as exc:  # noqa: BLE001
        log_usage("write", model, 0, 0, False, str(exc)[:200], None)
        raise
    return result.strip()


def digest_overview(user: str, account_id: int | None = None) -> str:
    """每日摘要的 AI 综述段落。"""
    base_url, model, api_key = _ai_config()
    try:
        text, usage = llm.chat(
            base_url, model, api_key,
            "你是邮件秘书，用中文写简洁的每日综述，只输出综述本身。",
            user,
        )
        log_usage("digest", model,
                  usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0),
                  True, "digest", account_id)
    except Exception as exc:  # noqa: BLE001
        log_usage("digest", model, 0, 0, False, str(exc)[:200], account_id)
        raise
    return text.strip()


def generate_tone_dna(samples: list[str], account_id: int | None = None) -> str:
    """从已发邮件样本总结用户的写作风格（Tone DNA）。"""
    base_url, model, api_key = _ai_config()
    joined = "\n\n----\n\n".join(s[:1500] for s in samples if s.strip())
    user = (
        "以下是用户发出的若干封真实邮件，请总结这个人的写作风格，"
        "输出一段 100-200 字的中文风格描述，包括：常用语言、正式程度、称呼与结尾习惯、"
        "句子长短与语气、常见口头表达。只输出风格描述本身，供今后模仿其风格起草邮件。\n\n"
        + joined
    )
    try:
        text, usage = llm.chat(
            base_url, model, api_key,
            "你是写作风格分析师，只输出风格描述本身。",
            user, temperature=0.2,
        )
        log_usage("tone_dna", model,
                  usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0),
                  True, f"{len(samples)} 封样本", account_id)
    except Exception as exc:  # noqa: BLE001
        log_usage("tone_dna", model, 0, 0, False, str(exc)[:200], account_id)
        raise
    return text.strip()


def usage_stats() -> dict:
    conn = get_conn()
    totals = conn.execute(
        "SELECT COUNT(*) AS calls,"
        " COALESCE(SUM(prompt_tokens),0) AS prompt_tokens,"
        " COALESCE(SUM(completion_tokens),0) AS completion_tokens,"
        " COALESCE(SUM(CASE WHEN ok=0 THEN 1 ELSE 0 END),0) AS failures"
        " FROM ai_logs"
    ).fetchone()
    by_day = conn.execute(
        "SELECT date(created_at) AS day, COUNT(*) AS calls,"
        " COALESCE(SUM(prompt_tokens + completion_tokens),0) AS tokens"
        " FROM ai_logs GROUP BY date(created_at) ORDER BY day DESC LIMIT 14"
    ).fetchall()
    by_task = conn.execute(
        "SELECT task_type, COUNT(*) AS calls,"
        " COALESCE(SUM(prompt_tokens + completion_tokens),0) AS tokens"
        " FROM ai_logs GROUP BY task_type"
    ).fetchall()
    return {
        "calls": totals["calls"],
        "prompt_tokens": totals["prompt_tokens"],
        "completion_tokens": totals["completion_tokens"],
        "failures": totals["failures"],
        "by_day": [dict(r) for r in by_day],
        "by_task": [dict(r) for r in by_task],
    }
