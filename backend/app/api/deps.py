"""API 层公共依赖与错误翻译（IMPROVEMENT_PLAN §3.3）。

core 层抛业务码（mailbox.MailError），这里统一定 HTTP 语义——各端点不再各自
写「查账号→查密钥→查 SMTP→异常转 HTTP」样板。
"""
from __future__ import annotations

from fastapi import HTTPException

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


def mail_error_to_http(exc: MailError) -> HTTPException:
    """MailError → HTTPException（4xx 业务错 / 502 服务器错，文案透传）。"""
    return HTTPException(_MAIL_ERROR_STATUS.get(exc.code, 502), exc.message)
