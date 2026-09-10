"""OpenAI 兼容客户端。

base_url 可指向任意 OpenAI 兼容端点（OpenAI / DeepSeek / Ollama / LM Studio 等）；
api_key 为空时使用占位符，以兼容 Ollama 等不校验密钥的本地服务。
"""
from __future__ import annotations

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
            "error": str(exc),
        }
