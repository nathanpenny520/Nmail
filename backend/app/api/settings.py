"""设置读写与 AI 端点连通性测试。

AI 端点配置已迁移到「配置档案」（见 api/profiles.py），此处仅保留通用设置；
测试端点字段省略时回退到激活档案。
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator

from app.ai import llm, profiles
from app.core import netproxy
from app.db.database import get_setting, set_setting

router = APIRouter(prefix="/api", tags=["settings"])

DEFAULT_SETTINGS: dict[str, object] = {
    "poll_interval_minutes": 5,
    "digest_time": "08:30",
    "ui_font": "compact",     # compact | standard | large
    "body_font": "standard",  # small | standard | large
    "allow_remote_images": False,  # 全局放行邮件远程图片（默认拦截防追踪）
    "update_check_enabled": True,  # 应用内更新检查（匿名版本对比，可关）
    "network_proxy": "",       # 全局代理地址（socks5://127.0.0.1:7890），空=直连
}


class SettingsIn(BaseModel):
    poll_interval_minutes: int | None = Field(default=None, ge=1, le=60)
    digest_time: str | None = None
    ui_font: str | None = None
    body_font: str | None = None
    allow_remote_images: bool | None = None
    update_check_enabled: bool | None = None
    network_proxy: str | None = Field(default=None, max_length=300)

    @field_validator("network_proxy")
    @classmethod
    def _validate_network_proxy(cls, v: str | None) -> str | None:
        if v is None:
            return v
        try:
            netproxy.parse_proxy_url(v)  # 空串=直连，合法；其余格式即时校验
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        return v

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


@router.get("/settings")
def read_settings() -> dict:
    return {
        "poll_interval_minutes": get_setting(
            "poll_interval_minutes", DEFAULT_SETTINGS["poll_interval_minutes"]
        ),
        "digest_time": get_setting("digest_time", DEFAULT_SETTINGS["digest_time"]),
        "ui_font": get_setting("ui_font", DEFAULT_SETTINGS["ui_font"]),
        "body_font": get_setting("body_font", DEFAULT_SETTINGS["body_font"]),
        "allow_remote_images": get_setting(
            "allow_remote_images", DEFAULT_SETTINGS["allow_remote_images"]
        ),
        "update_check_enabled": get_setting(
            "update_check_enabled", DEFAULT_SETTINGS["update_check_enabled"]
        ),
        "network_proxy": get_setting(
            "network_proxy", DEFAULT_SETTINGS["network_proxy"]
        ),
    }


@router.put("/settings")
def update_settings(payload: SettingsIn) -> dict:
    if payload.poll_interval_minutes is not None:
        set_setting("poll_interval_minutes", payload.poll_interval_minutes)
    if payload.digest_time is not None:
        set_setting("digest_time", payload.digest_time)
    if payload.ui_font is not None:
        set_setting("ui_font", payload.ui_font)
    if payload.body_font is not None:
        set_setting("body_font", payload.body_font)
    if payload.allow_remote_images is not None:
        set_setting("allow_remote_images", payload.allow_remote_images)
    if payload.update_check_enabled is not None:
        set_setting("update_check_enabled", payload.update_check_enabled)
    if payload.network_proxy is not None:
        set_setting("network_proxy", payload.network_proxy.strip())
    return read_settings()


class AITestIn(BaseModel):
    """字段省略时回退到激活档案的已存配置。"""

    base_url: str | None = None
    model: str | None = None
    api_key: str | None = None


@router.post("/ai/test")
def test_ai(payload: AITestIn) -> dict:
    try:
        p_base_url, p_model, p_api_key = profiles.resolve_config()
    except profiles.ProfileNotConfigured:
        p_base_url, p_model, p_api_key = "", "", None
    base_url = payload.base_url if payload.base_url is not None else p_base_url
    model = payload.model if payload.model is not None else p_model
    api_key = payload.api_key if payload.api_key is not None else p_api_key
    if not base_url or not model:
        return {
            "ok": False,
            "model": model,
            "reply": None,
            "latency_ms": 0,
            "error": "请先填写 Base URL 和模型名",
        }
    return llm.test_connection(base_url, model, api_key)
