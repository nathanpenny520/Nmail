"""设置读写与 AI 端点连通性测试。

API key 永不回传前端，只返回 api_key_set 布尔值。
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator

from app.ai import llm
from app.db.database import get_setting, set_setting
from app.security import get_secret, has_secret, set_secret

router = APIRouter(prefix="/api", tags=["settings"])

DEFAULT_SETTINGS: dict[str, object] = {
    "ai_base_url": "",
    "ai_model": "",
    "poll_interval_minutes": 5,
    "digest_time": "08:30",
    "ui_font": "compact",     # compact | standard | large
    "body_font": "standard",  # small | standard | large
}


class AISettingsIn(BaseModel):
    base_url: str | None = None
    model: str | None = None
    # 仅在用户主动修改时提交：空字符串表示清除已存密钥，省略表示保持不变
    api_key: str | None = None


class SettingsIn(BaseModel):
    ai: AISettingsIn | None = None
    poll_interval_minutes: int | None = Field(default=None, ge=1, le=60)
    digest_time: str | None = None
    ui_font: str | None = None
    body_font: str | None = None

    @field_validator("digest_time")
    @classmethod
    def _validate_time(cls, v: str | None) -> str | None:
        if v is None:
            return v
        try:
            hh, mm = v.split(":")
            if not (0 <= int(hh) <= 23 and 0 <= int(mm) <= 59):
                raise ValueError
        except ValueError as exc:
            raise ValueError("digest_time 需为 HH:MM 格式") from exc
        return v

    @field_validator("ui_font")
    @classmethod
    def _validate_ui_font(cls, v: str | None) -> str | None:
        if v is not None and v not in ("compact", "standard", "large"):
            raise ValueError("ui_font 需为 compact/standard/large")
        return v

    @field_validator("body_font")
    @classmethod
    def _validate_body_font(cls, v: str | None) -> str | None:
        if v is not None and v not in ("small", "standard", "large"):
            raise ValueError("body_font 需为 small/standard/large")
        return v


def _ai_state() -> dict:
    return {
        "base_url": get_setting("ai_base_url", DEFAULT_SETTINGS["ai_base_url"]),
        "model": get_setting("ai_model", DEFAULT_SETTINGS["ai_model"]),
        "api_key_set": has_secret("ai_api_key"),
    }


@router.get("/settings")
def read_settings() -> dict:
    return {
        "ai": _ai_state(),
        "poll_interval_minutes": get_setting(
            "poll_interval_minutes", DEFAULT_SETTINGS["poll_interval_minutes"]
        ),
        "digest_time": get_setting("digest_time", DEFAULT_SETTINGS["digest_time"]),
        "ui_font": get_setting("ui_font", DEFAULT_SETTINGS["ui_font"]),
        "body_font": get_setting("body_font", DEFAULT_SETTINGS["body_font"]),
    }


@router.put("/settings")
def update_settings(payload: SettingsIn) -> dict:
    if payload.ai is not None:
        if payload.ai.base_url is not None:
            set_setting("ai_base_url", payload.ai.base_url.strip())
        if payload.ai.model is not None:
            set_setting("ai_model", payload.ai.model.strip())
        if payload.ai.api_key is not None:
            set_secret("ai_api_key", payload.ai.api_key.strip() or None)
    if payload.poll_interval_minutes is not None:
        set_setting("poll_interval_minutes", payload.poll_interval_minutes)
    if payload.digest_time is not None:
        set_setting("digest_time", payload.digest_time)
    if payload.ui_font is not None:
        set_setting("ui_font", payload.ui_font)
    if payload.body_font is not None:
        set_setting("body_font", payload.body_font)
    return read_settings()


class AITestIn(BaseModel):
    """字段省略时使用已保存的配置。"""

    base_url: str | None = None
    model: str | None = None
    api_key: str | None = None


@router.post("/ai/test")
def test_ai(payload: AITestIn) -> dict:
    base_url = payload.base_url if payload.base_url is not None else get_setting("ai_base_url", "")
    model = payload.model if payload.model is not None else get_setting("ai_model", "")
    api_key = payload.api_key if payload.api_key is not None else get_secret("ai_api_key")
    if not base_url or not model:
        return {
            "ok": False,
            "model": model,
            "reply": None,
            "latency_ms": 0,
            "error": "请先填写 Base URL 和模型名",
        }
    return llm.test_connection(base_url, model, api_key)
