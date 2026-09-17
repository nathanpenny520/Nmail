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

# 新用户初始化默认（2026-09-13 用户定版）：仅 get_setting 的回退值，老用户已存值不受影响
DEFAULT_SETTINGS: dict[str, object] = {
    "poll_interval_minutes": 1,
    "digest_time": "07:00",
    "ui_font": "large",       # compact | standard | large
    "body_font": "standard",  # small | standard | large
    "allow_remote_images": False,  # 全局放行邮件远程图片（默认拦截防追踪）
    "update_check_enabled": True,  # 应用内更新检查（匿名版本对比，可关）
    "auto_update_enabled": True,  # 自动安装更新：检查到新版本后台下载换身，重启时生效（UPDATE_AND_DESKTOP.md §3.3）
    "contacts_auto_collect": False,  # 通讯录自动采集（收发往来地址自动入册；关=仅手动）
    "desktop_notifications_enabled": True,  # 桌面通知总开关（应用内铃铛与角标不受影响）
    "shortcuts_enabled": True,  # 键盘快捷键总开关（只屏蔽动作类键；Esc 与 ? 帮助不受控）
    # 桌面通知按类型细分（读侧与默认合并，缺省键视为开）；其余系统通知（更新/黑名单归档）不受控
    "notify_types": {"new_mail": True, "ai_draft": True, "digest": True, "account_error": True},
    "auto_insert_signature": False,  # 写信/回复自动带该账号签名（设置页「写信」管理签名内容）
    # AI 摘要（§18.6）：digest_time 到点由调度触发 agent 运行（总结未读+拟稿进待审），
    # 开启时替代纯统计摘要；工具白名单硬边界（SCHEDULER_ALLOWED）
    "agent_brief_enabled": False,
}

NOTIFY_TYPE_KEYS = ("new_mail", "ai_draft", "digest", "account_error")


class SettingsIn(BaseModel):
    poll_interval_minutes: int | None = Field(default=None, ge=1, le=60)
    digest_time: str | None = None
    ui_font: str | None = None
    body_font: str | None = None
    allow_remote_images: bool | None = None
    update_check_enabled: bool | None = None
    auto_update_enabled: bool | None = None
    contacts_auto_collect: bool | None = None
    desktop_notifications_enabled: bool | None = None
    shortcuts_enabled: bool | None = None
    notify_types: dict[str, bool] | None = None
    auto_insert_signature: bool | None = None
    agent_brief_enabled: bool | None = None

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

    @field_validator("notify_types")
    @classmethod
    def _validate_notify_types(cls, v: dict[str, bool] | None) -> dict[str, bool] | None:
        if v is None:
            return v
        out = {k: bool(v[k]) for k in NOTIFY_TYPE_KEYS if k in v}
        return out or None  # 全空=无有效改动；关闭全部类型应传四个 false（非空 dict 不受影响）


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
        "auto_update_enabled": get_setting(
            "auto_update_enabled", DEFAULT_SETTINGS["auto_update_enabled"]
        ),
        # 只读展示：系统代理探测结果 + 实际生效通道（设置页状态行实时轮询，均不入库）
        "detected_proxy": netproxy.detect_system_proxy(),
        "effective_proxy": netproxy.effective_proxy_url(),
        "contacts_auto_collect": get_setting(
            "contacts_auto_collect", DEFAULT_SETTINGS["contacts_auto_collect"]
        ),
        "desktop_notifications_enabled": get_setting(
            "desktop_notifications_enabled", DEFAULT_SETTINGS["desktop_notifications_enabled"]
        ),
        "shortcuts_enabled": get_setting(
            "shortcuts_enabled", DEFAULT_SETTINGS["shortcuts_enabled"]
        ),
        # 与默认合并：老用户 KV 里缺新键时回退 True（缺省视为开）
        "notify_types": {
            **DEFAULT_SETTINGS["notify_types"],
            **get_setting("notify_types", {}),
        },
        "auto_insert_signature": get_setting(
            "auto_insert_signature", DEFAULT_SETTINGS["auto_insert_signature"]
        ),
        "agent_brief_enabled": get_setting(
            "agent_brief_enabled", DEFAULT_SETTINGS["agent_brief_enabled"]
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
    if payload.auto_update_enabled is not None:
        set_setting("auto_update_enabled", payload.auto_update_enabled)
    if payload.contacts_auto_collect is not None:
        set_setting("contacts_auto_collect", payload.contacts_auto_collect)
    if payload.desktop_notifications_enabled is not None:
        set_setting("desktop_notifications_enabled", payload.desktop_notifications_enabled)
    if payload.shortcuts_enabled is not None:
        set_setting("shortcuts_enabled", payload.shortcuts_enabled)
    if payload.notify_types is not None:
        set_setting("notify_types", payload.notify_types)
    if payload.auto_insert_signature is not None:
        set_setting("auto_insert_signature", payload.auto_insert_signature)
    if payload.agent_brief_enabled is not None:
        set_setting("agent_brief_enabled", payload.agent_brief_enabled)
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
