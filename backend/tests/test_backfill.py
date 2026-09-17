"""全量同步引擎测试（EXPERIENCE_PLAN B1）：首翻最新一页立即可用 + 回补断点续传补齐历史。

用最小 FakeMb 假件走真函数（_sync_folder / _backfill_folder_pass），不碰真实 IMAP；
数据目录由 conftest 指向一次性临时目录。
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime
from types import SimpleNamespace

from app.core import imap_client, sync
from app.db import database

database.run_migrations()


def _make_parsed(uid: int) -> imap_client.ParsedMessage:
    return imap_client.ParsedMessage(
        uid=uid, message_id=f"<m{uid}@t>", subject=f"邮件{uid}",
        sender_name="发件人", sender_email=f"u{uid}@example.com",
        recipients=["me@example.com"], cc=[], date=datetime(2020, 1, 1),
        body_text=f"正文{uid}", body_html="", attachments=[], flags=frozenset(),
    )


class _Folder:
    def __init__(self, mb: FakeMb) -> None:
        self._mb = mb

    def set(self, name: str) -> None:
        self._mb.current = name


class FakeMb:
    """最小 IMAP 假件：store[folder] 存在的 UID 集合；只支持引擎用到的搜索条件。"""

    def __init__(self, store: dict[str, list[int]]) -> None:
        self.store = store
        self.current: str | None = None
        self.folder = _Folder(self)

    def uids(self, criteria: str) -> list[int]:
        uids = sorted(self.store.get(self.current, []))
        if criteria == "ALL":
            return uids
        m = re.fullmatch(r"UID (\d+):(\d+|\*)", criteria)
        lo, hi = int(m.group(1)), m.group(2)
        if hi == "*":
            # IMAP 语义：x > 最大 UID 时返回最后一封（iter_new_mail 再按 uid>last_uid 过滤）
            return [u for u in uids if u >= lo] or ([uids[-1]] if uids else [])
        return [u for u in uids if lo <= u <= int(hi)]

    def fetch(self, criteria: str, mark_seen: bool = False, bulk: bool = True):
        m = re.fullmatch(r"UID (\d+)(?::(\d+))?", criteria)
        lo, hi = int(m.group(1)), int(m.group(2) or m.group(1))
        return [SimpleNamespace(uid=u) for u in self.store.get(self.current, []) if lo <= u <= hi]


def _account() -> int:
    conn = database.get_conn()
    cur = conn.execute(
        "INSERT INTO accounts (email, provider_name, imap_server, imap_port,"
        " smtp_server, smtp_port, color, status)"
        " VALUES (?, '自定义', 't.imap.test', 993, 't.smtp.test', 465, '#6366f1', 'ok')",
        (f"bf{uuid.uuid4().hex[:8]}@example.com",),
    )
    conn.commit()
    return int(cur.lastrowid)


def _state(aid: int, folder: str):
    return database.get_conn().execute(
        "SELECT last_uid, backfill_uid, backfill_done FROM sync_state"
        " WHERE account_id = ? AND folder = ?",
        (aid, folder),
    ).fetchone()


def _count(aid: int, folder: str) -> int:
    return database.get_conn().execute(
        "SELECT COUNT(*) c FROM emails WHERE account_id = ? AND folder = ?",
        (aid, folder),
    ).fetchone()["c"]


def test_first_sync_pulls_newest_page_and_marks_backfill_pending(monkeypatch):
    monkeypatch.setattr(imap_client, "_parse_message", lambda msg, uid: _make_parsed(uid))
    aid = _account()
    mb = FakeMb({"INBOX": list(range(1, 61))})  # 60 封：首翻应只拉最新一页（36..60）

    result = sync._sync_folder(mb, aid, "INBOX")

    assert result["new_count"] == 25
    assert _count(aid, "INBOX") == 25
    state = _state(aid, "INBOX")
    assert state["last_uid"] == 60
    assert state["backfill_uid"] == 60
    assert state["backfill_done"] == 0


def test_first_sync_small_folder_history_complete(monkeypatch):
    monkeypatch.setattr(imap_client, "_parse_message", lambda msg, uid: _make_parsed(uid))
    aid = _account()
    mb = FakeMb({"INBOX": list(range(1, 11))})  # 10 封：一页装下，历史即齐

    result = sync._sync_folder(mb, aid, "INBOX")

    assert result["new_count"] == 10
    state = _state(aid, "INBOX")
    assert state["backfill_done"] == 1


def test_backfill_pass_completes_remaining_history(monkeypatch):
    monkeypatch.setattr(imap_client, "_parse_message", lambda msg, uid: _make_parsed(uid))
    aid = _account()
    mb = FakeMb({"INBOX": list(range(1, 61))})
    sync._sync_folder(mb, aid, "INBOX")

    outcome = sync._backfill_folder_pass(mb, aid, "INBOX")

    assert outcome == "done"
    assert _count(aid, "INBOX") == 60  # 首翻 25 + 回补 35
    assert _state(aid, "INBOX")["backfill_done"] == 1


def test_backfill_pass_resumes_from_checkpoint(monkeypatch):
    monkeypatch.setattr(imap_client, "_parse_message", lambda msg, uid: _make_parsed(uid))
    aid = _account()
    mb = FakeMb({"INBOX": list(range(1, 3001))})  # 3000 封：一趟（2000）装不下
    sync._sync_folder(mb, aid, "INBOX")

    assert sync._backfill_folder_pass(mb, aid, "INBOX") == "progress"
    state = _state(aid, "INBOX")
    assert state["backfill_uid"] == 1000  # 首翻页(2976..3000)+一趟2000封(1000..2999)，剩 1..999
    assert _count(aid, "INBOX") == 2001  # 25 + 2000，其中 2976..2999 与首翻页重叠去重

    assert sync._backfill_folder_pass(mb, aid, "INBOX") == "done"
    assert _count(aid, "INBOX") == 3000
    assert _state(aid, "INBOX")["backfill_done"] == 1


def test_backfill_todo_inbox_first(monkeypatch):
    monkeypatch.setattr(imap_client, "_parse_message", lambda msg, uid: _make_parsed(uid))
    aid = _account()
    conn = database.get_conn()
    for folder in ("Sent", "INBOX", "Archived"):
        conn.execute(
            "INSERT INTO sync_state (account_id, folder, last_uid, backfill_done)"
            " VALUES (?, ?, 0, 0)",
            (aid, folder),
        )
    conn.execute(
        "UPDATE sync_state SET backfill_done = 1 WHERE account_id = ? AND folder = 'Sent'",
        (aid,),
    )
    conn.commit()

    assert sync._backfill_todo(aid) == ["INBOX", "Archived"]


def test_incremental_sync_still_limited_to_new_uids(monkeypatch):
    monkeypatch.setattr(imap_client, "_parse_message", lambda msg, uid: _make_parsed(uid))
    aid = _account()
    mb = FakeMb({"INBOX": list(range(1, 11))})
    sync._sync_folder(mb, aid, "INBOX")  # 首翻：10 封全进
    mb.store["INBOX"] = list(range(1, 16))  # 服务器新到 5 封

    result = sync._sync_folder(mb, aid, "INBOX")

    assert result["new_count"] == 5
    assert _count(aid, "INBOX") == 15
