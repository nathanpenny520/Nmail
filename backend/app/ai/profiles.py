"""AI 配置档案（多模型 / 多 API Key）。

档案存 settings 表（JSON 数组），密钥存 secrets.json（ai_profile_key:{id}）；
密钥永不回传前端，接口只返回 api_key_set 布尔值。
旧版单配置（ai_base_url / ai_model / ai_api_key）在首次读取时自动迁移为「默认」档案，
历史密钥原样搬运，老用户无感。
"""
from __future__ import annotations

from app.db.database import get_setting, set_setting
from app.security import get_secret, has_secret, set_secret

PROFILES_KEY = "ai_profiles"
ACTIVE_KEY = "active_profile_id"
ENABLED_KEY = "ai_enabled"  # "0"=停用（传统邮件模式）；缺省/"1"=启用
LEGACY_SECRET_KEY = "ai_api_key"

DEFAULT_PROFILE_ID = "default"


class ProfileNotConfigured(Exception):
    """无可用档案，或档案不完整（缺 Base URL / 模型名）。"""


def secret_key(profile_id: str) -> str:
    return f"ai_profile_key:{profile_id}"


def ensure_migrated() -> None:
    """旧单配置 → 「默认」档案；幂等，只在档案数据缺失时执行一次。"""
    if get_setting(PROFILES_KEY) is not None:
        return
    profiles = [
        {
            "id": DEFAULT_PROFILE_ID,
            "name": "默认",
            "base_url": (get_setting("ai_base_url", "") or "").strip(),
            "model": (get_setting("ai_model", "") or "").strip(),
        }
    ]
    set_setting(PROFILES_KEY, profiles)
    set_setting(ACTIVE_KEY, DEFAULT_PROFILE_ID)
    legacy = get_secret(LEGACY_SECRET_KEY)
    if legacy and not has_secret(secret_key(DEFAULT_PROFILE_ID)):
        set_secret(secret_key(DEFAULT_PROFILE_ID), legacy)


def list_profiles() -> list[dict]:
    ensure_migrated()
    return get_setting(PROFILES_KEY, [])


def save_profiles(profiles: list[dict]) -> None:
    set_setting(PROFILES_KEY, profiles)


def get_active_id() -> str | None:
    ensure_migrated()
    return get_setting(ACTIVE_KEY, None)


def set_active_id(profile_id: str | None) -> None:
    set_setting(ACTIVE_KEY, profile_id)


def is_enabled() -> bool:
    """AI 总开关：停用后所有 AI 任务一律拒绝（配置档案原样保留）。"""
    return (get_setting(ENABLED_KEY, "1") or "1") != "0"


def set_enabled(enabled: bool) -> None:
    set_setting(ENABLED_KEY, "1" if enabled else "0")


def resolve(profile_id: str | None = None) -> dict:
    """取目标档案：显式指定 > 激活档案 > 第一个；无档案时抛 ProfileNotConfigured。"""
    profiles = list_profiles()
    if not profiles:
        raise ProfileNotConfigured("未配置 AI 端点，请在 设置-AI 配置 中添加")
    wanted = profile_id or get_active_id()
    for p in profiles:
        if p["id"] == wanted:
            return p
    return profiles[0]


def resolve_config(profile_id: str | None = None) -> tuple[str, str, str | None]:
    """返回 (base_url, model, api_key)；AI 停用或档案不完整时抛 ProfileNotConfigured。"""
    if not is_enabled():
        raise ProfileNotConfigured("AI 功能已停用，可在「设置 - AI 配置」重新开启")
    p = resolve(profile_id)
    base_url = (p.get("base_url") or "").strip()
    model = (p.get("model") or "").strip()
    if not base_url or not model:
        raise ProfileNotConfigured(f"AI 配置「{p.get('name')}」不完整，请补全 Base URL 和模型名")
    return base_url, model, get_secret(secret_key(p["id"]))
