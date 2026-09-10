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
