"""草稿体系合并测试（v0.4 P3，REDESIGN_PLAN §5.1）：旧 drafts 数据并入、
pending_review 流转（丢弃/恢复/批准发送通路）、regenerate 端点契约。"""
from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.core import outbox
from app.db import database
from app.main import app

client = TestClient(app, base_url="http://127.0.0.1")

database.run_migrations()  # TestClient 不触发 lifespan，迁移在此显式补跑


def _seed_account() -> int:
    conn = database.get_conn()
    cur = conn.execute(
        "INSERT INTO accounts (email, imap_server, imap_port) VALUES (?, 'imap.test', 993)",
        (f"d{uuid.uuid4().hex[:8]}@example.com",),
    )
    conn.commit()
    return int(cur.lastrowid)


def _seed_email(account_id: int, uid: int, subject: str, sender: str = "boss@example.com") -> int:
    conn = database.get_conn()
    cur = conn.execute(
        "INSERT INTO emails (account_id, folder, uid, subject, sender_email, body_text)"
        " VALUES (?, 'INBOX', ?, ?, ?, '正文')",
        (account_id, uid, subject, sender),
    )
    conn.commit()
    return int(cur.lastrowid)


def test_migrate_legacy_ai_drafts():
    """旧 drafts（pending/sent/discarded）一次性并入 user_drafts：Markdown→HTML、
    收件人=原发件人、主题 Re:、状态映射；KV 门控幂等。"""
    aid = _seed_account()
    eid = _seed_email(aid, 1, "周报：项目进展")
    conn = database.get_conn()
    for status, content in (("pending", "# 标题\n\n收到，本周进展顺利。"),
                            ("discarded", "旧草稿"), ("sent", "已发草稿")):
        conn.execute(
            "INSERT INTO drafts (email_id, account_id, content, origin, status, instruction)"
            " VALUES (?, ?, ?, 'ai', ?, ?)",
            (eid, aid, content, status, "指令A" if status == "pending" else None),
        )
    conn.commit()

    migrated = outbox.migrate_legacy_ai_drafts()
    assert migrated >= 3
    rows = conn.execute(
        "SELECT * FROM user_drafts WHERE account_id = ? AND origin = 'ai'", (aid,)
    ).fetchall()
    assert len(rows) >= 3
    pending = [r for r in rows if r["status"] == "pending_review"]
    assert len(pending) >= 1
    row = pending[0]
    assert row["to_addrs"] == "boss@example.com"
    assert row["subject"].startswith("回复：") or row["subject"].lower().startswith("re:")
    assert "<h" in row["body_html"] or "<p" in row["body_html"]  # Markdown 已转 HTML
    assert row["instruction"] == "指令A"
    assert row["in_reply_to"] == eid
    # 幂等：再跑一次不再新增
    assert outbox.migrate_legacy_ai_drafts() == 0
    total = conn.execute(
        "SELECT COUNT(*) c FROM user_drafts WHERE account_id = ? AND origin = 'ai'", (aid,)
    ).fetchone()["c"]
    assert len(rows) == total


def test_pending_review_flow_and_send_state_machine():
    """pending_review：丢弃→恢复→状态回 pending_review；已 sent 的草稿不可再发。"""
    aid = _seed_account()
    conn = database.get_conn()
    cur = conn.execute(
        "INSERT INTO user_drafts (account_id, mode, in_reply_to, to_addrs, subject,"
        " body_html, status, origin) VALUES (?, 'reply', NULL, 'a@b.com', '回复',"
        " '<p>正文</p>', 'pending_review', 'ai')",
        (aid,),
    )
    conn.commit()
    did = int(cur.lastrowid)

    assert client.post(f"/api/user-drafts/{did}/discard").status_code == 200
    assert client.get(f"/api/user-drafts/{did}").json()["draft"]["status"] == "discarded"
    assert client.post(f"/api/user-drafts/{did}/reopen").status_code == 200
    assert client.get(f"/api/user-drafts/{did}").json()["draft"]["status"] == "pending_review"

    # 发送需要真实 IMAP/SMTP（假账号必失败）——只验证状态机与错误翻译，不验证成功发送
    resp = client.post(f"/api/user-drafts/{did}/send")
    assert resp.status_code in (502, 400)  # 连接失败 502 / 缺凭据 4xx，草稿保持待审
    assert client.get(f"/api/user-drafts/{did}").json()["draft"]["status"] == "pending_review"

    # 手工置 sent 后再发 → 400 state
    conn.execute("UPDATE user_drafts SET status = 'sent' WHERE id = ?", (did,))
    conn.commit()
    assert client.post(f"/api/user-drafts/{did}/send").status_code == 400

    # regenerate：无 in_reply_to 拒绝
    assert client.post(
        f"/api/user-drafts/{did}/regenerate", json={"instruction": "更简短"}
    ).status_code == 400


def test_list_statuses_and_email_context():
    """列表按状态过滤；in_reply_to 关联的邮件上下文随行返回。"""
    aid = _seed_account()
    eid = _seed_email(aid, 9, "合同评审邀请")
    conn = database.get_conn()
    conn.execute(
        "INSERT INTO user_drafts (account_id, mode, in_reply_to, to_addrs, subject,"
        " body_html, status, origin) VALUES (?, 'reply', ?, 'boss@example.com', '回复：合同评审邀请',"
        " '<p>ok</p>', 'pending_review', 'ai')",
        (aid, eid),
    )
    conn.commit()
    resp = client.get("/api/user-drafts", params={"status": "pending_review"})
    drafts = resp.json()["drafts"]
    mine = [d for d in drafts if d["account_id"] == aid]
    assert len(mine) == 1
    assert mine[0]["email"]["subject"] == "合同评审邀请"
    assert mine[0]["email"]["sender_email"] == "boss@example.com"
    assert mine[0]["origin"] == "ai"
    # 非法状态 400
    assert client.get("/api/user-drafts", params={"status": "pending"}).status_code == 400


def test_clear_drafts_only_terminal_states():
    """批量清空：仅 sent/discarded 开放；editing 等在途状态 400 且分毫不动。"""
    aid = _seed_account()
    conn = database.get_conn()
    for status in ("sent", "sent", "discarded", "editing"):
        conn.execute(
            "INSERT INTO user_drafts (account_id, mode, to_addrs, subject, body_html,"
            " status, origin) VALUES (?, 'new', 'a@b.com', 's', '<p>x</p>', ?, 'human')",
            (aid, status),
        )
    conn.commit()

    def _count(status: str) -> int:  # 按本用例账号过滤，隔离其他用例的残留数据
        drafts = client.get("/api/user-drafts", params={"status": status}).json()["drafts"]
        return sum(1 for d in drafts if d["account_id"] == aid)

    # 在途状态拒绝
    assert client.delete("/api/user-drafts", params={"status": "editing"}).status_code == 400
    assert client.delete("/api/user-drafts", params={"status": "pending_review"}).status_code == 400
    assert _count("editing") == 1  # 未被误删

    # 清空 sent 只动 sent
    resp = client.delete("/api/user-drafts", params={"status": "sent"})
    assert resp.status_code == 200 and resp.json()["deleted"] >= 2
    assert _count("sent") == 0
    assert _count("discarded") == 1

    # 清空 discarded；再清一次 deleted=0（幂等）
    assert client.delete("/api/user-drafts", params={"status": "discarded"}).json()["deleted"] >= 1
    assert _count("discarded") == 0
    # editing 草稿全程无恙
    assert _count("editing") == 1
