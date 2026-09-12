"""账号 PATCH 服务器配置编辑测试：试连通过才落库、OAuth2 拒改、服务器变更清空本地邮件重同步。"""
from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.db import database
from app.main import app

client = TestClient(app, base_url="http://127.0.0.1")

database.run_migrations()


def _pwd_account() -> int:
    conn = database.get_conn()
    cur = conn.execute(
        "INSERT INTO accounts (email, provider_name, imap_server, imap_port,"
        " smtp_server, smtp_port, color, status)"
        " VALUES (?, '自定义', 'old.imap.test', 993, 'old.smtp.test', 465, '#6366f1', 'ok')",
        (f"acc{uuid.uuid4().hex[:8]}@example.com",),
    )
    conn.commit()
    return int(cur.lastrowid)


def _oauth_account() -> int:
    conn = database.get_conn()
    cur = conn.execute(
        "INSERT INTO accounts (email, imap_server, imap_port, auth_type) VALUES (?, 'imap.gmail.com', 993, 'oauth2')",
        (f"o{uuid.uuid4().hex[:8]}@gmail.com",),
    )
    conn.commit()
    return int(cur.lastrowid)


def test_patch_server_requires_connection_and_wipes_on_change(monkeypatch):
    import app.api.accounts as accounts_api

    calls: list[str] = []
    monkeypatch.setattr(
        accounts_api.imap_client, "test_connection",
        lambda cfg: (calls.append(cfg.imap_server) or (True, "ok")),
    )
    started: list[int] = []
    monkeypatch.setattr(accounts_api.sync_engine, "start_sync", lambda account, **kw: started.append(account["id"]) or {"started": True})

    aid = _pwd_account()
    conn = database.get_conn()
    conn.execute(
        "INSERT INTO emails (account_id, folder, uid, message_id) VALUES (?, 'INBOX', 1, 'm1')",
        (aid,),
    )
    conn.execute("INSERT INTO sync_state (account_id, folder, last_uid) VALUES (?, 'INBOX', 42)", (aid,))
    conn.commit()

    # 试连失败 → 400 且配置不变
    monkeypatch.setattr(accounts_api.imap_client, "test_connection", lambda cfg: (False, "连不上"))
    resp = client.patch(f"/api/accounts/{aid}", json={"imap_server": "new.imap.test"})
    assert resp.status_code == 400
    assert database.get_conn().execute(
        "SELECT imap_server FROM accounts WHERE id = ?", (aid,)
    ).fetchone()["imap_server"] == "old.imap.test"

    # 试连成功 → 落库 + 本地邮件/断点清空 + 后台重同步
    monkeypatch.setattr(
        accounts_api.imap_client, "test_connection",
        lambda cfg: (calls.append(cfg.imap_server) or (True, "ok")),
    )
    resp = client.patch(
        f"/api/accounts/{aid}",
        json={"imap_server": "new.imap.test", "imap_port": 993,
              "smtp_server": "new.smtp.test", "smtp_port": 465},
    )
    assert resp.status_code == 200
    row = database.get_conn().execute("SELECT * FROM accounts WHERE id = ?", (aid,)).fetchone()
    assert row["imap_server"] == "new.imap.test" and row["smtp_server"] == "new.smtp.test"
    assert database.get_conn().execute(
        "SELECT COUNT(*) c FROM emails WHERE account_id = ?", (aid,)
    ).fetchone()["c"] == 0
    assert database.get_conn().execute(
        "SELECT COUNT(*) c FROM sync_state WHERE account_id = ?", (aid,)
    ).fetchone()["c"] == 0
    assert started == [aid]
    assert calls[-1] == "new.imap.test"  # 试连用的是新服务器

    # 端口改回同值（服务器未变）不触发清空重同步
    started.clear()
    assert client.patch(f"/api/accounts/{aid}", json={"imap_port": 993}).status_code == 200
    assert started == []


def test_patch_server_rejected_for_oauth2(monkeypatch):
    import app.api.accounts as accounts_api

    monkeypatch.setattr(accounts_api.imap_client, "test_connection", lambda cfg: (True, "ok"))
    oid = _oauth_account()
    resp = client.patch(f"/api/accounts/{oid}", json={"imap_server": "evil.imap.test"})
    assert resp.status_code == 400
    assert database.get_conn().execute(
        "SELECT imap_server FROM accounts WHERE id = ?", (oid,)
    ).fetchone()["imap_server"] == "imap.gmail.com"


def test_list_accounts_echoes_password_plaintext():
    """授权码明文回显（所见即所存，用户 2026-09-12 要求，同 AI key 口径）：有码回码，无码空串。"""
    from app.security import get_secret, set_secret

    aid = _pwd_account()
    set_secret(f"account_pwd:{aid}", "smtp-auth-code-123")
    row = next(a for a in client.get("/api/accounts").json()["accounts"] if a["id"] == aid)
    assert row["password"] == "smtp-auth-code-123"
    assert get_secret(f"account_pwd:{aid}") == "smtp-auth-code-123"

    oauth_aid = _oauth_account()
    o_row = next(a for a in client.get("/api/accounts").json()["accounts"] if a["id"] == oauth_aid)
    assert o_row["password"] == ""  # OAuth2 账号无授权码，不误显
