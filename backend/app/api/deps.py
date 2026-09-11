"""API 层公共依赖与错误翻译（IMPROVEMENT_PLAN §3.3）。

core 层抛业务码（mailbox.MailError），这里统一定 HTTP 语义——各端点不再各自
写「查账号→查密钥→查 SMTP→异常转 HTTP」样板；AI 调用的「未配置 400 / 其余 502」
翻译同样收在这里。
"""
from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from fastapi import HTTPException

from app.ai import tasks
from app.core.mailbox import MailError

_MAIL_ERROR_STATUS: dict[str, int] = {
    "not_found": 404,
    "missing_credential": 400,
    "smtp_missing": 400,
    "state": 400,
    "no_recipient": 400,
    "send_failed": 502,
    "server": 502,
}

T = TypeVar("T")


def mail_error_to_http(exc: MailError) -> HTTPException:
    """MailError → HTTPException（4xx 业务错 / 502 服务器错，文案透传）。"""
    return HTTPException(_MAIL_ERROR_STATUS.get(exc.code, 502), exc.message)


def ai_config_or_400(profile_id: str | None) -> tuple[str, str, str | None]:
    """解析 AI 配置；未配置/停用 → 400（区分两种文案）。返回 (base_url, model, api_key)。

    需要在副作用（落库等）之前做配置预检的端点用这个（如总管家流式版先验后存）。
    """
    try:
        return tasks._ai_config(profile_id)
    except tasks.AINotConfigured as exc:
        raise HTTPException(400, str(exc)) from None


def ai_result_or_http(call: Callable[[], T]) -> T:
    """执行一次 AI 调用并统一翻译：未配置/停用 → 400，参数错（ValueError）→ 400，
    其余 → 502「AI 调用失败：…」。"""
    try:
        return call()
    except tasks.AINotConfigured as exc:  # 区分「未配置端点」与「AI 已停用」
        raise HTTPException(400, str(exc)) from None
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"AI 调用失败：{exc}") from exc
