"""AI 配置档案 CRUD 与模型列表代理。

密钥语义：请求里 api_key 省略 = 保持不变；空字符串 = 清除；非空 = 覆盖。
本地单用户应用（仅绑定 127.0.0.1，密钥本就存于本机 secrets.json），
响应回显 api_key 明文供界面所见即所存——用户要求可见可核对。
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.ai import llm
from app.ai import profiles as profiles_mod
from app.security import get_secret, set_secret

router = APIRouter(prefix="/api/ai", tags=["ai-profiles"])


def _profile_dict(p: dict) -> dict:
    return {
        "id": p["id"],
        "name": p.get("name", ""),
        "base_url": p.get("base_url", ""),
        "model": p.get("model", ""),
        "api_key": get_secret(profiles_mod.secret_key(p["id"])) or "",
    }


def _get_profile_or_404(profile_id: str) -> dict:
    for p in profiles_mod.list_profiles():
        if p["id"] == profile_id:
            return p
    raise HTTPException(404, "AI 配置不存在")


class ProfileCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    base_url: str = ""
    model: str = ""
    api_key: str | None = None


class ProfileUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=40)
    base_url: str | None = None
    model: str | None = None
    api_key: str | None = None  # None=不变；空串=清除


@router.get("/profiles")
def list_profiles() -> dict:
    return {
        "profiles": [_profile_dict(p) for p in profiles_mod.list_profiles()],
        "active_profile_id": profiles_mod.get_active_id(),
        "ai_enabled": profiles_mod.is_enabled(),
    }


class EnabledIn(BaseModel):
    enabled: bool


@router.put("/enabled")
def set_ai_enabled(payload: EnabledIn) -> dict:
    """AI 总开关：停用即回归传统邮件（所有 AI 入口隐藏、任务拒绝），配置档案保留。"""
    profiles_mod.set_enabled(payload.enabled)
    return {"ok": True, "ai_enabled": payload.enabled}


@router.post("/profiles")
def create_profile(payload: ProfileCreateIn) -> dict:
    profiles_list = profiles_mod.list_profiles()
    profile = {
        "id": uuid.uuid4().hex[:8],
        "name": payload.name.strip() or "未命名",
        "base_url": payload.base_url.strip(),
        "model": payload.model.strip(),
    }
    profiles_list.append(profile)
    profiles_mod.save_profiles(profiles_list)
    if payload.api_key:
        set_secret(profiles_mod.secret_key(profile["id"]), payload.api_key.strip())
    if profiles_mod.get_active_id() not in {p["id"] for p in profiles_list}:
        profiles_mod.set_active_id(profile["id"])  # 第一个档案自动成为激活
    return {"profile": _profile_dict(profile)}


@router.patch("/profiles/{profile_id}")
def update_profile(profile_id: str, payload: ProfileUpdateIn) -> dict:
    profiles_list = profiles_mod.list_profiles()
    profile = _get_profile_or_404(profile_id)
    if payload.name is not None:
        profile["name"] = payload.name.strip() or profile.get("name") or "未命名"
    if payload.base_url is not None:
        profile["base_url"] = payload.base_url.strip()
    if payload.model is not None:
        profile["model"] = payload.model.strip()
    profiles_mod.save_profiles(profiles_list)
    if payload.api_key is not None:
        # set_secret 语义：空值即删除
        set_secret(profiles_mod.secret_key(profile_id), payload.api_key.strip() or None)
    return {"profile": _profile_dict(profile)}


@router.delete("/profiles/{profile_id}")
def delete_profile(profile_id: str) -> dict:
    profiles_list = profiles_mod.list_profiles()
    _get_profile_or_404(profile_id)
    profiles_mod.save_profiles([p for p in profiles_list if p["id"] != profile_id])
    set_secret(profiles_mod.secret_key(profile_id), None)
    if profiles_mod.get_active_id() == profile_id:
        remaining = profiles_mod.list_profiles()
        profiles_mod.set_active_id(remaining[0]["id"] if remaining else None)
    return {"ok": True}


@router.put("/profiles/{profile_id}/activate")
def activate_profile(profile_id: str) -> dict:
    _get_profile_or_404(profile_id)
    profiles_mod.set_active_id(profile_id)
    return {"ok": True, "active_profile_id": profile_id}


class ModelsIn(BaseModel):
    profile_id: str | None = None  # 提供时补全该档案已存的 URL/密钥
    base_url: str | None = None    # 显式值优先（支持尚未保存的新配置直接拉取）
    api_key: str | None = None     # 缺省时回退档案已存密钥


@router.post("/models")
def list_models(payload: ModelsIn) -> dict:
    """代理 OpenAI 兼容端点的 GET /models，供前端自动补全模型名。

    解析优先级：显式 base_url > 档案已存 base_url；显式 api_key > 档案已存密钥。
    """
    base_url = (payload.base_url or "").strip()
    api_key = (payload.api_key or "").strip() or None
    if payload.profile_id and not base_url:
        profile = next(
            (p for p in profiles_mod.list_profiles() if p["id"] == payload.profile_id), None
        )
        if profile is None:
            return {"ok": False, "models": [], "error": "AI 配置不存在"}
        base_url = (profile.get("base_url") or "").strip()
        if api_key is None:
            api_key = get_secret(profiles_mod.secret_key(profile["id"]))
    if not base_url:
        return {"ok": False, "models": [], "error": "请先填写 Base URL"}
    try:
        client = llm.build_client(base_url, api_key)
        models = sorted({m.id for m in client.models.list()})
        return {"ok": True, "models": models, "error": None}
    except Exception as exc:  # noqa: BLE001 — 网络/鉴权错误统一转为友好结果
        return {"ok": False, "models": [], "error": str(exc)}
