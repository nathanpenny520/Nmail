"""db 层测试：迁移幂等、tx() 事务语义、get_setting 容错（IMPROVEMENT_PLAN T1）。"""
from __future__ import annotations

import pytest

from app.db import database


def test_migrations_idempotent():
    database.run_migrations()
    before = database.get_conn().execute(
        "SELECT COUNT(*) c FROM schema_migrations"
    ).fetchone()["c"]
    database.run_migrations()  # 第二遍连跑：不抛异常、不重复记版本
    after = database.get_conn().execute(
        "SELECT COUNT(*) c FROM schema_migrations"
    ).fetchone()["c"]
    assert before == after == 13  # 当前最新版本 v13


def test_tx_commit_atomic():
    with database.tx() as conn:
        conn.execute("INSERT INTO settings (key, value) VALUES ('tx_ok', '1')")
        conn.execute("INSERT INTO settings (key, value) VALUES ('tx_ok2', '2')")
    # 直插的裸值经 get_setting 的 json.loads 还原：'1' → 整数 1
    assert database.get_setting("tx_ok") == 1
    assert database.get_setting("tx_ok2") == 2


def test_tx_rollback_on_exception():
    with pytest.raises(RuntimeError):
        with database.tx() as conn:
            conn.execute("INSERT INTO settings (key, value) VALUES ('tx_bad', '1')")
            raise RuntimeError("boom")
    assert database.get_conn().execute(
        "SELECT COUNT(*) c FROM settings WHERE key = 'tx_bad'"
    ).fetchone()["c"] == 0


def test_get_setting_corrupt_json_falls_back():
    database.set_setting("corrupt", {"a": 1})
    database.get_conn().execute("UPDATE settings SET value = '{bad json' WHERE key = 'corrupt'")
    assert database.get_setting("corrupt", "fallback") == "fallback"
