"""AI 任务实现：批量分类、生成回复草稿、上下文问答、写作辅助。

统一通过 llm.chat 调用并写入 ai_logs；未配置 AI 端点时抛 AINotConfigured，
由调用方决定降级行为。
"""
from __future__ import annotations

import json
import logging
import re
from contextlib import contextmanager
from datetime import datetime, UTC
from typing import Any
from collections.abc import Iterator

from app.ai import llm, profiles, prompts
from app.ai.categories import CATEGORY_KEYS
from app.db.database import get_conn

logger = logging.getLogger(__name__)


class AINotConfigured(Exception):
    pass


def _ai_config(profile_id: str | None = None) -> tuple[str, str, str | None]:
    """解析目标档案的 (base_url, model, api_key)；未配置/不完整时抛 AINotConfigured。"""
    try:
        return profiles.resolve_config(profile_id)
    except profiles.ProfileNotConfigured as exc:
        raise AINotConfigured(str(exc)) from None


@contextmanager
def _logged(task_type: str, summary: str, model: str = "",
            account_id: int | None = None, usage_out: dict | None = None) -> Iterator:
    """ai_logs 统一记账（IMPROVEMENT_PLAN §3.3b）：正常退出记成功日志，异常记失败
    日志（摘要=异常文本截 200）后 re-raise——各任务函数不再各写一对样板。

    - 常规：``with _logged("draft", subj, model, aid) as ok: ...; ok(usage)``
    - 流式/累计用量：传 usage_out=与 llm 层共享的 dict，成功失败都取其中累计值。
    """
    usage = usage_out if usage_out is not None else {}
    final_summary = summary

    def ok(u: dict | None = None, summary_override: str | None = None) -> None:
        if u:
            usage.update(u)
        if summary_override is not None:
            nonlocal final_summary
            final_summary = summary_override

    try:
        yield ok
    except Exception as exc:  # noqa: BLE001
        log_usage(task_type, model, usage.get("prompt_tokens", 0),
                  usage.get("completion_tokens", 0), False, str(exc)[:200], account_id)
        raise
    log_usage(task_type, model, usage.get("prompt_tokens", 0),
              usage.get("completion_tokens", 0), True, final_summary, account_id)


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
    return datetime.now(UTC).isoformat(timespec="seconds")


def _extract_json(text: str) -> Any:
    """从模型输出中稳健提取 JSON（容忍代码块包裹和前后杂讯）。"""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.+?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # 首个平衡的 [ ] / { }（v0.4.x 止血：旧「首到尾」跨度会被混入的
        # 幻觉 <result> 等文本搅坏，见 REDESIGN_PLAN §17.1）；数组优先保持
        # 「分类结果：[{...}]」类输出的既有行为
        for start_ch, end_ch in (("[", "]"), ("{", "}")):
            start = text.find(start_ch)
            if start == -1:
                continue
            depth, in_str, esc = 0, False, False
            for i in range(start, len(text)):
                ch = text[i]
                if in_str:
                    if esc:
                        esc = False
                    elif ch == "\\":
                        esc = True
                    elif ch == '"':
                        in_str = False
                    continue
                if ch == '"':
                    in_str = True
                elif ch == start_ch:
                    depth += 1
                elif ch == end_ch:
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(text[start : i + 1])
                        except json.JSONDecodeError:
                            break
        raise


def classify_batch(items: list[dict], account_id: int | None = None,
                   profile_id: str | None = None) -> list[dict]:
    """批量分类邮件。items: [{id, subject, sender, body_head}]，返回同序结果列表。

    单封解析失败时跳过并记日志，不影响其他邮件。
    """
    base_url, model, api_key = _ai_config(profile_id)
    email_lines = []
    for it in items:
        body = (it["body_head"] or "").replace("\n", " ").strip()
        email_lines.append(
            f'--- id={it["id"]} ---\n发件人: {it["sender"]}\n主题: {it["subject"]}\n正文: {body}'
        )
    user = prompts.CLASSIFY_USER_TEMPLATE.format(count=len(items), emails="\n".join(email_lines))

    with _logged("classify", f"{len(items)} 封", model, account_id) as ok:
        text, usage = llm.chat(base_url, model, api_key, prompts.CLASSIFY_SYSTEM, user)
        ok(usage)

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
        if category not in CATEGORY_KEYS:
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
    profile_id: str | None = None,
) -> str:
    """为一封来信生成回复草稿正文（Markdown）；账号设置文风提示词时注入遵循。"""
    base_url, model, api_key = _ai_config(profile_id)
    system = prompts.DRAFT_SYSTEM
    if account_id is not None:
        row = get_conn().execute(
            "SELECT style_prompt FROM accounts WHERE id = ?", (account_id,)
        ).fetchone()
        if row and row["style_prompt"]:
            system += f"\n\n用户的文风要求（起草时请遵循）：{row['style_prompt']}"
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

    with _logged("draft", email_row["subject"][:80], model, account_id) as ok:
        text, usage = llm.chat(base_url, model, api_key, system, user)
        ok(usage)
    return text.strip()


def chat_with_context(
    context_text: str,
    question: str,
    history: list[dict] | None = None,
    account_id: int | None = None,
    profile_id: str | None = None,
) -> str:
    """基于邮件上下文回答问题（非流式）。history: [{role, content}]"""
    base_url, model, api_key = _ai_config(profile_id)
    messages = _chat_messages(context_text, question, history)
    with _logged("chat", question[:80], model, account_id) as ok:
        text, usage = llm.chat_messages(base_url, model, api_key, messages)
        ok(usage)
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
    profile_id: str | None = None,
):
    """流式版问答：返回一个 yield 文本增量的生成器；结束时写用量日志。"""
    base_url, model, api_key = _ai_config(profile_id)
    messages = _chat_messages(context_text, question, history)
    usage: dict = {"prompt_tokens": 0, "completion_tokens": 0}

    def generate():
        # 流式：usage 由 iter_deltas 边发边填，成功/失败都按累计值记账
        with _logged("chat", question[:80], model, account_id, usage_out=usage):
            yield from llm.iter_deltas(base_url, model, api_key, messages, usage_out=usage)

    return generate()


def write_assist(text: str, op: str, instruction: str | None = None,
                 profile_id: str | None = None) -> str:
    """写作辅助：润色/正式/随意/缩短/扩充/翻译/按指令写邮件（compose）。"""
    base_url, model, api_key = _ai_config(profile_id)
    if op == "compose":
        # 按指令写邮件：instruction 必填，text 作为可选背景/草稿上下文
        if not instruction or not instruction.strip():
            raise ValueError("请先描述要让 AI 写什么")
        system = (
            "你是邮件写作助手。根据用户的指令直接撰写邮件正文：只输出内容本身，"
            "不要解释或复述指令。用 Markdown 格式组织排版（可用加粗、列表、分段），"
            "语言跟随指令（未指明则用中文）。称呼与落款仅在指令给出相关信息时才写。"
        )
        context = f"\n\n可参考的背景/已有草稿：\n{text[:4000]}" if text.strip() else ""
        user = f"{instruction.strip()}{context}"
        with _logged("write", "compose", model) as ok:
            result, usage = llm.chat(base_url, model, api_key, system, user)
            ok(usage)
        return result.strip()

    if op == "custom":
        head = instruction or "润色"
    else:
        head = prompts.WRITE_OPS.get(op)
        if not head:
            raise ValueError(f"未知写作操作：{op}")
    user = prompts.WRITE_USER_TEMPLATE.format(instruction=head, text=text[:6000])
    with _logged("write", op, model) as ok:
        result, usage = llm.chat(base_url, model, api_key,
                                 "你是写作助手，只输出改写结果本身，不要解释。", user)
        ok(usage)
    return result.strip()


def digest_overview(user: str, account_id: int | None = None,
                    profile_id: str | None = None) -> str:
    """每日摘要的 AI 综述段落。"""
    base_url, model, api_key = _ai_config(profile_id)
    with _logged("digest", "digest", model, account_id) as ok:
        text, usage = llm.chat(
            base_url, model, api_key,
            "你是邮件秘书，用中文写简洁的每日综述，只输出综述本身。",
            user,
        )
        ok(usage)
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
