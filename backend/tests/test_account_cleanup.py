"""账号删除残留审计测试（2026-09-17）：删除即清干净 + 删光归零序列 + 启动 GC 幂等。

不碰真实用户数据（conftest 数据目录为一次性临时目录）。
"""
from __future__ import annotations

import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from app.db import database
from app.main import app

client = TestClient(app, base_url="http://127.0.0.1")

database.run_migrations()


def _aid(email: str | None = None) -> int:
    conn = database.get_conn()
    cur = conn.execute(
        "INSERT INTO accounts (email, imap_server, imap_port, smtp_server, smtp_port)"
        " VALUES (?, 'imap.test', 993, 'smtp.test', 465)",
        (email or f"del{uuid.uuid4().hex[:8]}@example.com",),
    )
    conn.commit()
    return int(cur.lastrowid)


def _seed_full_footprint(aid: int) -> int:
    """为一个账号铺齐全套从属数据，返回其邮件 id。"""
    conn = database.get_conn()
    cur = conn.execute(
        "INSERT INTO emails (account_id, folder, uid, subject, sender_email, body_text)"
        " VALUES (?, 'INBOX', 1, '残留测试', 's@x.com', '正文')",
        (aid,),
    )
    email_id = int(cur.lastrowid)
    conn.execute(
        "INSERT INTO ai_logs (task_type, account_id, model, prompt_tokens, completion_tokens)"
        " VALUES ('classify', ?, 'm', 1, 1)",
        (aid,),
    )
    conn.execute(
        "INSERT INTO ai_actions (account_id, tool, params_json, mode, origin, status)"
        " VALUES (?, 'archive_emails', '{}', 'approval', 'ui', 'executed')",
        (aid,),
    )
    conn.execute("INSERT INTO jobs (kind, account_id, status) VALUES ('organize', ?, 'done')", (aid,))
    conn.execute(
        "INSERT INTO rule_observations (email_id, account_id, sender_email, action)"
        " VALUES (?, ?, 's@x.com', 'archive')",
        (email_id, aid),
    )
    cur = conn.execute("INSERT INTO chat_sessions (account_id, title) VALUES (?, 't')", (aid,))
    conn.execute(
        "INSERT INTO chat_messages (session_id, role, content) VALUES (?, 'user', 'hi')",
        (int(cur.lastrowid),),
    )
    conn.execute(
        "INSERT INTO agent_runs (account_ids_json, status, mode, origin)"
        " VALUES (?, 'done', 'approval', 'ui')",
        (f"[{aid}]",),
    )
    for n_type, ref in (("new_mail", str(email_id)), ("account_error", str(aid))):
        conn.execute(
            "INSERT INTO notifications (type, title, body, ref_id) VALUES (?, 't', '', ?)",
            (n_type, ref),
        )
    sigs = database.get_setting("compose_signatures", []) or []
    sigs.append({"account_id": aid, "content": "签名"})
    database.set_setting("compose_signatures", sigs)
    conn.commit()
    return email_id


def test_delete_account_cleans_everything_and_keeps_contacts():
    aid = _aid()
    email_id = _seed_full_footprint(aid)
    conn = database.get_conn()
    cur = conn.execute(
        "INSERT INTO contacts (account_id, email, name) VALUES (?, 's@x.com', '保留的联系人')",
        (aid,),
    )
    contact_id = int(cur.lastrowid)
    conn.commit()

    r = client.delete(f"/api/accounts/{aid}")
    assert r.status_code == 200

    # 无 FK 从属数据全部清掉
    for table in ("ai_logs", "ai_actions", "jobs", "rule_observations", "chat_sessions"):
        n = conn.execute(
            f"SELECT COUNT(*) c FROM {table} WHERE account_id = ?", (aid,)
        ).fetchone()["c"]
        assert n == 0, table
    assert conn.execute("SELECT COUNT(*) c FROM agent_runs WHERE account_ids_json = ?", (f"[{aid}]",)).fetchone()["c"] == 0
    assert conn.execute("SELECT COUNT(*) c FROM emails WHERE id = ?", (email_id,)).fetchone()["c"] == 0
    # 悬空通知已清（该账号的 new_mail/account_error 均指向已删对象）
    assert conn.execute(
        "SELECT COUNT(*) c FROM notifications WHERE ref_id IN (?, ?)", (str(email_id), str(aid))
    ).fetchone()["c"] == 0
    # KV 幽灵签名剔除
    sigs = database.get_setting("compose_signatures", []) or []
    assert all(s.get("account_id") != aid for s in sigs)
    # 通讯录保留（用户拍板：删邮箱≠删人脉）
    row = conn.execute("SELECT account_id, email FROM contacts WHERE id = ?", (contact_id,)).fetchone()
    assert row is not None and row["email"] == "s@x.com"


def test_delete_one_of_two_keeps_other_account_data():
    a1, a2 = _aid(), _aid()
    conn = database.get_conn()
    _seed_full_footprint(a1)
    _seed_full_footprint(a2)

    client.delete(f"/api/accounts/{a1}")

    # a2 的从属数据一条不动
    assert conn.execute("SELECT COUNT(*) c FROM ai_logs WHERE account_id = ?", (a2,)).fetchone()["c"] == 1
    assert conn.execute("SELECT COUNT(*) c FROM ai_actions WHERE account_id = ?", (a2,)).fetchone()["c"] == 1
    assert conn.execute("SELECT 1 FROM accounts WHERE id = ?", (a2,)).fetchone() is not None
    # 序列不归零（还有存活账号）
    seq = conn.execute("SELECT seq FROM sqlite_sequence WHERE name = 'accounts'").fetchone()
    assert seq is not None and seq["seq"] >= a2
    # 清理测试足迹（不留孤儿给后续用例）
    client.delete(f"/api/accounts/{a2}")


def test_delete_last_account_resets_sequences():
    # 清空全部账号（测试库隔离环境），确认删光后序列归零、下一个新账号 id=1
    conn = database.get_conn()
    for r in conn.execute("SELECT id FROM accounts").fetchall():
        client.delete(f"/api/accounts/{int(r['id'])}")
    assert conn.execute("SELECT 1 FROM accounts LIMIT 1").fetchone() is None
    assert conn.execute("SELECT seq FROM sqlite_sequence WHERE name = 'accounts'").fetchone() is None

    fresh = _aid()
    assert fresh == 1, f"删光重开后首个账号应为 id=1，实际 {fresh}"
    # 收尾：不留给后续用例幽灵账号
    client.delete("/api/accounts/1")
    assert conn.execute("SELECT 1 FROM accounts LIMIT 1").fetchone() is None


def test_cleanup_orphans_idempotent_and_disk_dir_removed(tmp_path, monkeypatch):
    aid = _aid()
    conn = database.get_conn()
    cur = conn.execute(
        "INSERT INTO user_drafts (account_id, mode, to_addrs, subject, body_html, status, origin)"
        " VALUES (?, 'new', 'x@y.com', 't', '<p></p>', 'discarded', 'human')",
        (aid,),
    )
    draft_id = int(cur.lastrowid)
    # 模拟磁盘孤儿草稿目录（行将被账号删除级联带走，目录要被 GC 清）
    from app.config import get_data_dir

    d = Path(get_data_dir()) / "drafts" / str(draft_id)
    d.mkdir(parents=True, exist_ok=True)
    (d / "att.txt").write_text("x")
    conn.commit()

    client.delete(f"/api/accounts/{aid}")  # 级联删 user_drafts 行 + 内部跑 cleanup_orphans

    assert not d.exists(), "孤儿草稿附件目录应被清理"
    assert database.cleanup_orphans() == {}, "再次运行应为无操作（幂等）"
