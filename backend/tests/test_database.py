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
    assert before == after == 25  # 版本数（最新 v26 回补断点列；v18 跳过——原预留 API key 改走 v20）


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


# ── 保留期与僵尸对账（REDESIGN_PLAN §18.2/§18.3）──────────────────

def test_cleanup_retention_audit_and_runs():
    """ai_actions 分层保留（发送类已执行永久）+ agent_runs 终态清理与 running 对账。"""
    conn = database.get_conn()
    conn.execute("DELETE FROM ai_actions")
    conn.execute("DELETE FROM agent_runs")
    conn.commit()
    for tool, status, days in [
        ("mark_emails", "failed", 31),
        ("mark_emails", "failed", 3),
        ("move_emails", "executed", 91),
        ("send_draft", "executed", 365),
        ("send_draft", "failed", 40),
        ("mark_emails", "executed", 10),
        ("mark_emails", "undone", 91),
    ]:
        conn.execute(
            f"INSERT INTO ai_actions (tool, status, created_at)"
            f" VALUES (?, ?, datetime('now', '-{days} days'))",
            (tool, status),
        )
    for status, age in [("done", "-31 days"), ("waiting_approval", "-100 days"),
                        ("paused_budget", "-100 days"), ("running", "-11 minutes"),
                        ("running", "-2 minutes")]:
        conn.execute(
            f"INSERT INTO agent_runs (mode, status, created_at, updated_at)"
            f" VALUES ('approval', ?, datetime('now', '{age}'), datetime('now', '{age}'))",
            (status,),
        )
    conn.commit()
    database.cleanup_retention()
    # ai_actions：30 天档清失败类（含发送失败）；90 天档清执行类但发送永久
    assert conn.execute(
        "SELECT COUNT(*) n FROM ai_actions WHERE tool = 'mark_emails' AND status = 'failed'"
    ).fetchone()["n"] == 1  # 只剩 3 天那条
    assert conn.execute(
        "SELECT COUNT(*) n FROM ai_actions WHERE tool = 'move_emails' AND status = 'executed'"
    ).fetchone()["n"] == 0
    assert conn.execute(
        "SELECT COUNT(*) n FROM ai_actions WHERE tool = 'send_draft' AND status = 'executed'"
    ).fetchone()["n"] == 1  # 365 天仍保留
    assert conn.execute(
        "SELECT COUNT(*) n FROM ai_actions WHERE tool = 'send_draft' AND status = 'failed'"
    ).fetchone()["n"] == 0
    assert conn.execute(
        "SELECT COUNT(*) n FROM ai_actions WHERE tool = 'mark_emails' AND status = 'executed'"
    ).fetchone()["n"] == 1  # 10 天保留
    assert conn.execute(
        "SELECT COUNT(*) n FROM ai_actions WHERE tool = 'mark_emails' AND status = 'undone'"
    ).fetchone()["n"] == 0
    # agent_runs：终态 30 天清；waiting/paused 保留；running 10 分钟外对账 cancelled
    for status, want in [("done", 0), ("waiting_approval", 1), ("paused_budget", 1),
                         ("cancelled", 1), ("running", 1)]:
        n = conn.execute(
            "SELECT COUNT(*) n FROM agent_runs WHERE status = ?", (status,)
        ).fetchone()["n"]
        assert n == want, f"agent_runs {status} 期望 {want} 实际 {n}"
