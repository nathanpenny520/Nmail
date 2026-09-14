"""OpenAI 兼容客户端。

base_url 可指向任意 OpenAI 兼容端点（OpenAI / DeepSeek / Ollama / LM Studio 等）；
api_key 为空时使用占位符，以兼容 Ollama 等不校验密钥的本地服务。
"""
from __future__ import annotations

import json
import time

import httpx
from openai import OpenAI

# 按阶段收紧超时：connect 5s、读写 15s，坏端点/断网时快速失败而非长时间挂起
AI_TIMEOUT = httpx.Timeout(15.0, connect=5.0)


def build_client(base_url: str, api_key: str | None, timeout: httpx.Timeout = AI_TIMEOUT) -> OpenAI:
    return OpenAI(
        base_url=base_url or None,
        api_key=api_key or "EMPTY",
        timeout=timeout,
        max_retries=0,
    )


def chat(base_url: str, model: str, api_key: str | None,
         system: str, user: str, **kwargs) -> tuple[str, dict]:
    """单轮对话，返回 (回复文本, 用量 dict)。"""
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    return chat_messages(base_url, model, api_key, messages, **kwargs)


def chat_messages(base_url: str, model: str, api_key: str | None,
                  messages: list[dict], max_tokens: int = 2000,
                  temperature: float = 0.3) -> tuple[str, dict]:
    """多轮对话，返回 (回复文本, {prompt_tokens, completion_tokens})。"""
    client = build_client(base_url, api_key)
    resp = client.chat.completions.create(
        model=model,
        messages=messages,  # type: ignore[arg-type]
        max_tokens=max_tokens,
        temperature=temperature,
    )
    usage = {
        "prompt_tokens": getattr(resp.usage, "prompt_tokens", 0) or 0,
        "completion_tokens": getattr(resp.usage, "completion_tokens", 0) or 0,
    }
    content = resp.choices[0].message.content or "" if resp.choices else ""
    return content, usage


def iter_deltas(base_url: str, model: str, api_key: str | None,
                messages: list[dict], usage_out: dict | None = None,
                max_tokens: int = 2000, temperature: float = 0.3):
    """流式对话：逐段 yield 文本增量；支持时在最后一个 chunk 回填 token 用量。

    stream_options 先带后不带重试一次：部分 OpenAI 兼容端点（旧版 Ollama /
    LM Studio 等）不认该参数会直接报错（审查 F4）——此时退回无用量回填的普通流。
    """
    client = build_client(base_url, api_key)
    kwargs: dict = {
        "model": model,
        "messages": messages,  # type: ignore[arg-type]
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": True,
    }
    try:
        stream = client.chat.completions.create(**kwargs, stream_options={"include_usage": True})
    except Exception:  # noqa: BLE001 — 端点不认 stream_options，去掉参数重试
        stream = client.chat.completions.create(**kwargs)
    for chunk in stream:
        if usage_out is not None and getattr(chunk, "usage", None) is not None:
            usage_out["prompt_tokens"] = getattr(chunk.usage, "prompt_tokens", 0) or 0
            usage_out["completion_tokens"] = getattr(chunk.usage, "completion_tokens", 0) or 0
        if chunk.choices:
            delta = chunk.choices[0].delta
            content = getattr(delta, "content", None)
            if content:
                yield content


# ── Agent 单步调用（原生 function calling，REDESIGN_PLAN §17.1）────────

def _tool_choice_kw(tool_choice: str | None) -> dict:
    """auto 缺省不传（部分兼容端点不认该参数）；none=预算收尾强制文本。"""
    return {"tool_choice": tool_choice} if tool_choice and tool_choice != "auto" else {}


def _openai_tools(tools: list[dict]) -> list[dict]:
    """内部工具表（name/description/parameters）→ OpenAI wire 格式。"""
    return [{"type": "function", "function": t} for t in tools]


def _split_tool_calls(message) -> tuple[str, list[dict]]:  # noqa: ANN001
    """OpenAI message → (content, tool_calls)；tool_calls 统一为 {id,name,arguments(dict)}。"""
    content = getattr(message, "content", None) or ""
    calls: list[dict] = []
    for tc in getattr(message, "tool_calls", None) or []:
        fn = getattr(tc, "function", None)
        if fn is None:
            continue
        try:
            args = json.loads(fn.arguments or "{}")
        except ValueError:
            args = {}
        if not isinstance(args, dict):
            args = {}
        calls.append({"id": tc.id or f"call_{len(calls)}", "name": fn.name or "",
                      "arguments": args})
    return content, calls


def chat_step(base_url: str, model: str, api_key: str | None,
              messages: list[dict], tools: list[dict] | None = None,
              tool_choice: str | None = None, max_tokens: int = 2000,
              temperature: float = 0.3) -> tuple[str, list[dict], dict, str]:
    """Agent 单步（非流式）：返回 (content, tool_calls, usage, finish_reason)。

    tools 为内部格式 [{name, description, parameters}]；端点不支持 tools 参数时
    抛 openai.APIStatusError（由 agent 层探测降级）。
    """
    client = build_client(base_url, api_key)
    kwargs: dict = {
        "model": model,
        "messages": messages,  # type: ignore[arg-type]
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if tools:
        kwargs["tools"] = _openai_tools(tools)
        kwargs.update(_tool_choice_kw(tool_choice))
    resp = client.chat.completions.create(**kwargs)
    usage = {
        "prompt_tokens": getattr(resp.usage, "prompt_tokens", 0) or 0,
        "completion_tokens": getattr(resp.usage, "completion_tokens", 0) or 0,
    }
    choice = resp.choices[0] if resp.choices else None
    content, calls = _split_tool_calls(choice.message) if choice else ("", [])
    return content, calls, usage, getattr(choice, "finish_reason", "") or ""


def iter_chat_step(base_url: str, model: str, api_key: str | None,
                   messages: list[dict], tools: list[dict] | None = None,
                   tool_choice: str | None = None, max_tokens: int = 2000,
                   temperature: float = 0.3):
    """Agent 单步（流式）：yield ("text_delta", 增量)；生成器 return 值为
    (content, tool_calls, usage, finish_reason)。工具调用分片按 index 聚合。"""
    client = build_client(base_url, api_key)
    kwargs: dict = {
        "model": model,
        "messages": messages,  # type: ignore[arg-type]
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": True,
    }
    if tools:
        kwargs["tools"] = _openai_tools(tools)
        kwargs.update(_tool_choice_kw(tool_choice))
    try:
        stream = client.chat.completions.create(**kwargs, stream_options={"include_usage": True})
    except Exception:  # noqa: BLE001 — 端点不认 stream_options，去掉参数重试
        stream = client.chat.completions.create(**kwargs)

    content_parts: list[str] = []
    usage = {"prompt_tokens": 0, "completion_tokens": 0}
    finish_reason = ""
    slots: dict[int, dict] = {}  # tool_calls 分片按 index 聚合
    for chunk in stream:
        if getattr(chunk, "usage", None) is not None:
            usage["prompt_tokens"] = getattr(chunk.usage, "prompt_tokens", 0) or 0
            usage["completion_tokens"] = getattr(chunk.usage, "completion_tokens", 0) or 0
        if not chunk.choices:
            continue
        choice = chunk.choices[0]
        finish_reason = choice.finish_reason or finish_reason
        delta = choice.delta
        piece = getattr(delta, "content", None)
        if piece:
            content_parts.append(piece)
            yield ("text_delta", piece)
        for tc in getattr(delta, "tool_calls", None) or []:
            slot = slots.setdefault(tc.index, {"id": "", "name": "", "args": ""})
            if tc.id:
                slot["id"] = tc.id
            fn = getattr(tc, "function", None)
            if fn is not None:
                if fn.name:
                    slot["name"] = fn.name
                if fn.arguments:
                    slot["args"] += fn.arguments
    calls: list[dict] = []
    for i in sorted(slots):
        slot = slots[i]
        try:
            args = json.loads(slot["args"] or "{}")
        except ValueError:
            args = {}
        if not isinstance(args, dict):
            args = {}
        calls.append({"id": slot["id"] or f"call_{i}", "name": slot["name"],
                      "arguments": args})
    return "".join(content_parts), calls, usage, finish_reason


def friendly_error(error: str) -> str:
    """鉴权类错误补人话提示——401 多为密钥在服务商平台侧被删除/重置，本地保存无损。"""
    low = error.lower()
    if "401" in error or "authentication" in low or "invalid_api_key" in low:
        return error + "（提示：401 通常不是保存失败，而是该密钥已在服务商平台被删除/重置，请到控制台核对或重新生成）"
    return error


def test_connection(base_url: str, model: str, api_key: str | None) -> dict:
    """发送一个极小请求，验证端点 / 密钥 / 模型名是否可用。"""
    started = time.perf_counter()
    try:
        client = build_client(base_url, api_key)
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Reply with the single word: pong"}],
            max_tokens=10,
            temperature=0,
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        return {
            "ok": True,
            "model": model,
            "reply": (resp.choices[0].message.content or "").strip(),
            "latency_ms": latency_ms,
            "error": None,
        }
    except Exception as exc:  # 网络 / 鉴权 / 模型名错误统一转为友好结果
        return {
            "ok": False,
            "model": model,
            "reply": None,
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "error": friendly_error(str(exc)),
        }
