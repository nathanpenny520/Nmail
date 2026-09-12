"""AI 档案一致性：备份自愈语义——主值缺失/损坏/被外力清空均恢复，故意删空保持空。

回归背景（S-0912-0034）：主值被旧版 ensure_migrated 静默清空后，空列表曾被当作
"用户故意删光"而不触发备份恢复，导致真实档案消失、密钥成孤儿后被清。
"""
from __future__ import annotations

import pytest

from app.ai import profiles
from app.db import database

PROFILE = {"id": "p1", "name": "deepseek",
           "base_url": "https://api.deepseek.com", "model": "deepseek-flash"}


@pytest.fixture()
def kv_guard():
    """测试前后保存/还原档案相关 KV，避免污染同会话其他用例。"""
    keys = (profiles.PROFILES_KEY, profiles.PROFILES_BACKUP_KEY, profiles.ACTIVE_KEY,
            "ai_base_url", "ai_model")
    before = {k: database.get_setting(k) for k in keys}
    yield
    for k, v in before.items():
        database.set_setting(k, v)


def test_restore_when_main_emptied(kv_guard):
    """主值被外力清空（绕过 save_profiles）但备份非空 → 从备份恢复并设激活。"""
    profiles.save_profiles([PROFILE])
    database.set_setting(profiles.PROFILES_KEY, [])
    assert profiles.list_profiles() == [PROFILE]
    assert profiles.get_active_id() == "p1"


def test_intentional_delete_stays_empty(kv_guard):
    """UI 删空走 save_profiles（备份同步为空）→ 保持空，不被误恢复。"""
    profiles.save_profiles([])
    assert profiles.list_profiles() == []


def test_restore_when_main_corrupt(kv_guard):
    """主值损坏（非法 JSON → 读侧为 None）→ 从备份恢复（既有行为回归）。"""
    profiles.save_profiles([PROFILE])
    database.set_setting(profiles.PROFILES_KEY, "{bad json")
    assert profiles.list_profiles() == [PROFILE]


def test_save_profiles_mirrors_backup(kv_guard):
    """故意删空安全性的前提：save_profiles 必须始终同步双写备份。"""
    profiles.save_profiles([PROFILE])
    assert database.get_setting(profiles.PROFILES_BACKUP_KEY) == [PROFILE]
    profiles.save_profiles([])
    assert database.get_setting(profiles.PROFILES_BACKUP_KEY) == []


def test_first_install_no_profiles(kv_guard):
    """全新安装（主值空 + 备份空 + 无旧配置）→ 保持空，不预建档案。"""
    profiles.list_profiles()
    assert profiles.list_profiles() == []
