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
    assert before == after == 17  # 版本数（最新 v19；17-18 预留给 AI 授权/API key）


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


def test_get_conn_per_thread_isolation():
    """回归（S-0912-0040）：共享单连接时并发 execute 会炸语句绑定竞态
    （InterfaceError / IndexError，实测 16 线程稳定复现）——每线程独立连接后
    必须零错误，且线程内连接稳定、线程间互不相同。"""
    import threading

    conns = {}

    def worker(i: int) -> None:
        first = database.get_conn()
        for _ in range(300):
            assert database.get_setting("poll_interval_minutes", 5) in (5, None)
            database.get_conn().execute("SELECT * FROM accounts").fetchall()
        conns[i] = (id(first), id(database.get_conn()))  # 线程首尾应为同一连接

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert all(first == last for first, last in conns.values())  # 线程内复用
    assert len({first for first, _ in conns.values()}) == 16     # 线程间独立


def test_close_thread_conn_resets():
    first = database.get_conn()
    database.close_thread_conn()
    second = database.get_conn()
    assert second is not first  # 旧连接已关、下次取到新连接
    assert database.get_setting("smoke_after_reopen", 1) == 1  # 新连接可用
