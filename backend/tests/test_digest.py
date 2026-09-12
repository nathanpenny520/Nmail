"""每日摘要回归（v0.4 审查 F1）：需要回复判定走 user_drafts（旧 drafts 表已退役）。

_collect_stats 直查共享测试库；账号/邮件用随机 uuid 账号隔离，不依赖执行顺序。
"""
from __future__ import annotations

import uuid

from app.ai import digest
from app.db import database

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
