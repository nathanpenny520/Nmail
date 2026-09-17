"""v27 迁移语义测试（EXPERIENCE_PLAN B1 修正）：存量 sync_state 行的回补锚点初始化。

直接执行 MIGRATIONS 里 v27 的原句 SQL，验证「从本地最小 UID 缺口开始回补」：
- 有本地邮件的行 → backfill_uid = MIN(uid)；
- 无本地邮件但有 last_uid 的行 → backfill_uid = last_uid；
- 已有锚点/已完成/last_uid=0 的行不受影响。
"""
from __future__ import annotations

import uuid

from app.db import database

database.run_migrations()


def _account() -> int:
    conn = database.get_conn()
    cur = conn.execute(
        "INSERT INTO accounts (email, imap_server, imap_port)"
        f" VALUES ('m{uuid.uuid4().hex[:8]}@example.com', 'imap.test', 993)"
    )
    conn.commit()
    return int(cur.lastrowid)


def _seed_email(aid: int, folder: str, uid: int) -> None:
    conn = database.get_conn()
    conn.execute(
        "INSERT INTO emails (account_id, folder, uid, subject, sender_email)"
        f" VALUES (?, ?, ?, 't', 's@x.com')",
        (aid, folder, uid),
    )
    conn.commit()


def _row(aid: int, folder: str):
    return database.get_conn().execute(
        "SELECT last_uid, backfill_uid, backfill_done FROM sync_state"
        " WHERE account_id = ? AND folder = ?",
        (aid, folder),
    ).fetchone()


def _run_v27() -> None:
    sql = next(sql for version, sql in database.MIGRATIONS if version == 27)
    conn = database.get_conn()
    conn.executescript(sql)
    conn.commit()


def test_v27_anchors_legacy_rows_from_local_gap():
    aid = _account()
    conn = database.get_conn()
    # 模拟存量账号：INBOX 已有 30 天窗口邮件（最小 UID=900），sync_state 无锚点
    for uid in (900, 1000, 1100):
        _seed_email(aid, "INBOX", uid)
    conn.execute(
        "INSERT INTO sync_state (account_id, folder, last_uid) VALUES (?, 'INBOX', 1100)",
        (aid,),
    )
    # Sent：last_uid 有值但本地空（旧账号从未同步成功过该夹）→ 回退 last_uid
    conn.execute(
        "INSERT INTO sync_state (account_id, folder, last_uid) VALUES (?, 'Sent', 500)",
        (aid,),
    )
    # Trash：last_uid=0 的空夹 → 不动（保持 NULL/0）
    conn.execute(
        "INSERT INTO sync_state (account_id, folder, last_uid) VALUES (?, 'Trash', 0)",
        (aid,),
    )
    conn.commit()

    _run_v27()

    inbox = _row(aid, "INBOX")
    assert inbox["backfill_uid"] == 900  # 从本地最小 UID（真正缺口）开始
    assert inbox["backfill_done"] == 0
    sent = _row(aid, "Sent")
    assert sent["backfill_uid"] == 500
    assert sent["backfill_done"] == 0
    trash = _row(aid, "Trash")
    assert trash["backfill_uid"] is None
    assert trash["backfill_done"] == 0


def test_v27_leaves_anchored_and_done_rows_alone():
    aid = _account()
    conn = database.get_conn()
    _seed_email(aid, "INBOX", 42)
    conn.execute(
        "INSERT INTO sync_state (account_id, folder, last_uid, backfill_uid, backfill_done)"
        " VALUES (?, 'INBOX', 42, 42, 1)",  # 新代码已完成的行
        (aid,),
    )
    conn.commit()

    _run_v27()

    row = _row(aid, "INBOX")
    assert row["backfill_uid"] == 42 and row["backfill_done"] == 1  # 不回退
