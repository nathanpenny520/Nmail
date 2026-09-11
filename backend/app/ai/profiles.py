"""AI 配置档案（多模型 / 多 API Key）。

档案存 settings 表（JSON 数组），密钥存 secrets.json（ai_profile_key:{id}）；
本地单用户应用，接口回显 api_key 明文供界面所见即所存。
不预建任何档案：全新安装为空列表，由用户按需创建；旧版单配置
（ai_base_url / ai_model / ai_api_key）首次读取时迁为一个以模型名命名的档案，
历史密钥原样搬运；历史版本自动生成的「默认」档案一次性按模型名重命名。

一致性保证（2026-09-11 档案丢失事故后加固）：
- save_profiles 双写备份键——主值被外力删除/损坏时从备份完整恢复，
  绝不静默走旧配置重建（那会让真实档案消失、旧 key 复活）；
- ensure_migrated 末尾对账：不被任何档案引用的 ai_profile_key:* 一律清除，
  密钥与档案列表永不留残骸。
"""
from __future__ import annotations

from app.db.database import get_setting, set_setting
from app.security import get_secret, has_secret, secret_keys, set_secret

PROFILES_KEY = "ai_profiles"
PROFILES_BACKUP_KEY = "ai_profiles_backup"  # 最后一份有效档案列表，主值丢失时恢复用
ACTIVE_KEY = "active_profile_id"
ENABLED_KEY = "ai_enabled"  # "0"=停用（传统邮件模式）；缺省/"1"=启用
LEGACY_SECRET_KEY = "ai_api_key"

DEFAULT_PROFILE_ID = "default"


class ProfileNotConfigured(Exception):
    """无可用档案，或档案不完整（缺 Base URL / 模型名）。"""


def secret_key(profile_id: str) -> str:
    return f"ai_profile_key:{profile_id}"


def prune_orphan_secrets(valid_ids: set[str]) -> None:
    """清掉不被任何档案引用的 ai_profile_key:*——密钥与档案列表严格对账。"""
    prefix = "ai_profile_key:"
    for k in secret_keys():
        if k.startswith(prefix) and k[len(prefix):] not in valid_ids:
            set_secret(k, None)


def ensure_migrated() -> None:
    """备份恢复 / 旧单配置迁移 / 档案名规范化 / 孤儿密钥对账；幂等。"""
    profiles = get_setting(PROFILES_KEY)
    if not isinstance(profiles, list):
        # 主值缺失/损坏：先试备份恢复。有备份说明档案本来存在——绝不能静默走
        # 旧配置重建（曾导致真实档案全部消失、其密钥成孤儿、失效旧 key 复活成现役）
        backup = get_setting(PROFILES_BACKUP_KEY)
        if isinstance(backup, list) and backup:
            profiles = backup
            set_setting(PROFILES_KEY, profiles)
            if get_setting(ACTIVE_KEY) not in {p["id"] for p in profiles}:
                set_setting(ACTIVE_KEY, profiles[0]["id"])
        else:
            legacy_url = (get_setting("ai_base_url", "") or "").strip()
            legacy_model = (get_setting("ai_model", "") or "").strip()
            if not legacy_url and not legacy_model:
                # 全新安装：不预建「默认」档案（空「默认」只会让切换器出现无意义选项）
                profiles = []
                set_setting(PROFILES_KEY, profiles)
                set_setting(ACTIVE_KEY, None)
            else:
                # 旧版单配置用户：迁为一个以模型名命名的档案，密钥原样搬运，老用户无感
                profiles = [{
                    "id": DEFAULT_PROFILE_ID,
                    "name": legacy_model or "我的配置",
                    "base_url": legacy_url,
                    "model": legacy_model,
                }]
                set_setting(PROFILES_KEY, profiles)
                set_setting(ACTIVE_KEY, DEFAULT_PROFILE_ID)
                legacy = get_secret(LEGACY_SECRET_KEY)
                if legacy and not has_secret(secret_key(DEFAULT_PROFILE_ID)):
                    set_secret(secret_key(DEFAULT_PROFILE_ID), legacy)
    # 历史版本自动生成的「默认」档案：一次性按模型名重命名（用户自行改过名的不动）
    for p in profiles:
        if p.get("id") == DEFAULT_PROFILE_ID and p.get("name") == "默认" \
                and (p.get("model") or "").strip():
            p["name"] = p["model"].strip()
            set_setting(PROFILES_KEY, profiles)
            break
    prune_orphan_secrets({p["id"] for p in profiles})


def list_profiles() -> list[dict]:
    ensure_migrated()
    return get_setting(PROFILES_KEY, [])


def save_profiles(profiles: list[dict]) -> None:
    set_setting(PROFILES_KEY, profiles)
    set_setting(PROFILES_BACKUP_KEY, profiles)


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
