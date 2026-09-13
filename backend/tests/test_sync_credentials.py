"""start_sync 凭据缺失语义测试：OAuth 账号令牌丢失要置 auth_error+通知（可见），
密码账号维持静默跳过（老号未存授权码属正常态，不打扰）。"""
from __future__ import annotations

import uuid

from app.core.sync import start_sync
from app.db import database

database.run_migrations()


def _account(auth_type: str) -> int:
    conn = database.get_conn()
    cur = conn.execute(
        "INSERT INTO accounts (email, imap_server, imap_port, auth_type, status)"
        " VALUES (?, 'imap.test', 993, ?, 'ok')",
        (f"s{uuid.uuid4().hex[:8]}@example.com", auth_type),
    )
    conn.commit()
    return int(cur.lastrowid)


def _error_notifications(aid: int) -> int:
    conn = database.get_conn()
    return conn.execute(
        "SELECT COUNT(*) AS n FROM notifications WHERE type = 'account_error' AND ref_id = ?",
        (str(aid),),
    ).fetchone()["n"]


def test_oauth_missing_token_flags_auth_error_and_notifies_once():
    aid = _account("oauth2")
    assert start_sync({"id": aid, "email": "x@example.com"}) == {
        "started": False,
        "reason": "no_credentials",
    }
    conn = database.get_conn()
    row = conn.execute(
        "SELECT status, status_detail FROM accounts WHERE id = ?", (aid,)
    ).fetchone()
    assert row["status"] == "auth_error"
    assert "重新授权" in (row["status_detail"] or "")
    assert _error_notifications(aid) == 1
    # 再触发：状态未迁移，不重复打扰
    start_sync({"id": aid, "email": "x@example.com"})
    assert _error_notifications(aid) == 1


def test_password_account_missing_credentials_stays_silent():
    aid = _account("password")
    assert start_sync({"id": aid, "email": "x@example.com"}) == {
        "started": False,
        "reason": "no_credentials",
    }
    row = database.get_conn().execute(
        "SELECT status FROM accounts WHERE id = ?", (aid,)
    ).fetchone()
    assert row["status"] == "ok"
    assert _error_notifications(aid) == 0
