"""每日摘要回归（v0.4 审查 F1）：需要回复判定走 user_drafts（旧 drafts 表已退役）。

_collect_stats 直查共享测试库；账号/邮件用随机 uuid 账号隔离，不依赖执行顺序。
"""
from __future__ import annotations

import json
import uuid

from fastapi.testclient import TestClient

from app.ai import digest
from app.db import database
from app.main import app

database.run_migrations()


def _aid() -> int:
    conn = database.get_conn()
    cur = conn.execute(
        "INSERT INTO accounts (email, imap_server, imap_port, ai_permission)"
        " VALUES (?, 'imap.test', 993, 'draft_review')",
        (f"digest{uuid.uuid4().hex[:8]}@example.com",),
    )
    conn.commit()
    return int(cur.lastrowid)


def _seed_email(aid: int, uid: int, subject: str) -> int:
    conn = database.get_conn()
    cur = conn.execute(
        "INSERT INTO emails (account_id, folder, uid, subject, sender_email, body_text, needs_reply)"
        " VALUES (?, 'INBOX', ?, ?, 'boss@x.com', '正文', 1)",
        (aid, uid, subject),
    )
    conn.commit()
    return int(cur.lastrowid)


def _need_reply_ids() -> set[int]:
    return {i["email_id"] for i in digest._collect_stats()["need_reply"]}


def test_replied_email_excluded_by_user_drafts_sent():
    """user_drafts 已发送回复（in_reply_to 指向原邮件）→ 不再出现在「需要回复」。"""
    aid = _aid()
    eid = _seed_email(aid, 51, "待回复邮件")
    assert eid in _need_reply_ids()

    conn = database.get_conn()
    conn.execute(
        "INSERT INTO user_drafts (account_id, mode, in_reply_to, to_addrs, subject,"
        " body_html, status, origin)"
        " VALUES (?, 'reply', ?, 'boss@x.com', 'Re: 待回复邮件', '<p>ok</p>', 'sent', 'ai')",
        (aid, eid),
    )
    conn.commit()
    assert eid not in _need_reply_ids()


def test_has_draft_flag_reflects_user_drafts():
    """「已有草稿」标记：pending_review 草稿也算（旧实现查退役 drafts 表恒 False）。"""
    aid = _aid()
    eid = _seed_email(aid, 52, "还没写草稿")
    stats = digest._collect_stats()
    item = next(i for i in stats["need_reply"] if i["email_id"] == eid)
    assert item["has_draft"] is False

    conn = database.get_conn()
    conn.execute(
        "INSERT INTO user_drafts (account_id, mode, in_reply_to, to_addrs, subject,"
        " body_html, status, origin)"
        " VALUES (?, 'reply', ?, 'boss@x.com', 'Re: 还没写草稿', '<p>草稿</p>',"
        " 'pending_review', 'ai')",
        (aid, eid),
    )
    conn.commit()
    stats = digest._collect_stats()
    item = next(i for i in stats["need_reply"] if i["email_id"] == eid)
    assert item["has_draft"] is True  # 待审草稿保持「需要回复」但标记已有草稿


# ── 重要邮件清除（✕ 按钮）─────────────────────────────────────

client = TestClient(app, base_url="http://127.0.0.1")


def _seed_important(aid: int, uid: int, subject: str) -> int:
    conn = database.get_conn()
    cur = conn.execute(
        "INSERT INTO emails (account_id, folder, uid, subject, sender_email, body_text, importance)"
        " VALUES (?, 'INBOX', ?, ?, 'security@google.com', '正文', 'critical')",
        (aid, uid, subject),
    )
    conn.commit()
    return int(cur.lastrowid)


def test_dismiss_important_persists_and_survives_rebuild():
    """✕ 清除重要邮件：GET 即时消失，同日重新生成不复活（跨天随新摘要重置）。"""
    aid = _aid()
    eid = _seed_important(aid, 61, "Security alert")
    digest.build_digest(force=True)
    body = client.get("/api/digest").json()["digest"]
    assert any(i["email_id"] == eid for i in body["important"])

    assert client.post(f"/api/digest/important/{eid}/dismiss").json() == {"ok": True}
    body = client.get("/api/digest").json()["digest"]
    assert not any(i["email_id"] == eid for i in body["important"])

    digest.build_digest(force=True)
    body = client.get("/api/digest").json()["digest"]
    assert not any(i["email_id"] == eid for i in body["important"])


def test_dismiss_important_unknown_id_404():
    assert client.post("/api/digest/important/99999999/dismiss").status_code == 404


def test_store_agent_brief():
    """§18.6：晨报正文存独立键 agent_brief（不顶替 AI 综述），结构化统计照常。"""
    aid = _aid()
    _seed_email(aid, 1, "晨报测试邮件")
    stats = digest.store_agent_brief("**晨报**：一切正常。")
    assert stats["agent_brief"] == "**晨报**：一切正常。"
    row = database.get_conn().execute(
        "SELECT content_json FROM digest_history WHERE date = date('now', 'localtime')"
    ).fetchone()
    assert row is not None
    data = json.loads(row["content_json"])
    assert data["agent_brief"] == "**晨报**：一切正常。" and "need_reply" in data
    assert "ai_overview" not in data  # 晨报日不生成常规综述（省一次 LLM）
