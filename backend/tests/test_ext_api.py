"""对外 API 测试（v0.4 P7，REDESIGN_PLAN §7）：Key 认证/scope 分级/限流、
密钥管理往返、Host 豁免边界、调用日志。端点薄壳转调既有实现，这里只测鉴权
与契约；agent 端点未配 AI 时应 400。"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.db import database
from app.main import app

client = TestClient(app, base_url="http://127.0.0.1")

database.run_migrations()  # TestClient 不触发 lifespan，迁移在此显式补跑


def _make_key(scopes: list[str], daily_limit: int | None = None) -> dict:
    resp = client.post("/api/extkeys", json={"name": "t", "scopes": scopes, "daily_limit": daily_limit})
    assert resp.status_code == 200, resp.text
    return resp.json()["key"]


def _headers(key: str | None) -> dict:
    h = {}
    if key:
        h["X-Api-Key"] = key
    return h


def test_health_无认证可用():
    assert client.get("/api/ext/v1/health").status_code == 200


def test_未启用时有效key也403():
    client.post("/api/extkeys/enabled", json={"enabled": False})
    key = _make_key(["read"])
    resp = client.get("/api/ext/v1/accounts", headers=_headers(key["key"]))
    assert resp.status_code == 403
    assert "未启用" in resp.json()["detail"]


def test_启用后缺key与坏key都401():
    client.post("/api/extkeys/enabled", json={"enabled": True})
    assert client.get("/api/ext/v1/accounts").status_code == 401
    assert client.get("/api/ext/v1/accounts", headers=_headers("nmail_wrong")).status_code == 401


def test_read_scope端点往返():
    client.post("/api/extkeys/enabled", json={"enabled": True})
    key = _make_key(["read"])
    for path in ("/api/ext/v1/accounts", "/api/ext/v1/emails",
                 "/api/ext/v1/contacts", "/api/ext/v1/digest",
                 "/api/ext/v1/drafts"):
        resp = client.get(path, headers=_headers(key["key"]))
        assert resp.status_code == 200, f"{path}: {resp.text}"


def test_scope不足403():
    client.post("/api/extkeys/enabled", json={"enabled": True})
    read_key = _make_key(["read"])
    write_key = _make_key(["write"])
    # read 不能写
    resp = client.post("/api/ext/v1/emails/actions", headers=_headers(read_key["key"]),
                       json={"ids": [1], "action": "read"})
    assert resp.status_code == 403
    # write 不能发信
    resp = client.post("/api/ext/v1/drafts/1/approve", headers=_headers(write_key["key"]))
    assert resp.status_code == 403
    # agent 端点需 agent scope
    resp = client.post("/api/ext/v1/agent/chat", headers=_headers(read_key["key"]),
                       json={"question": "hi"})
    assert resp.status_code == 403


def test_write动作参数校验与job返回():
    client.post("/api/extkeys/enabled", json={"enabled": True})
    key = _make_key(["write"])
    resp = client.post("/api/ext/v1/emails/actions", headers=_headers(key["key"]),
                       json={"ids": [], "action": "read"})
    assert resp.status_code == 400
    resp = client.post("/api/ext/v1/emails/actions", headers=_headers(key["key"]),
                       json={"ids": [999999], "action": "read"})
    assert resp.status_code == 200
    assert resp.json()["ok"] is True  # 不存在的 id 按更新 0 封处理（与内部契约一致）
    resp = client.post("/api/ext/v1/emails/actions", headers=_headers(key["key"]),
                       json={"ids": [999999], "action": "move"})
    assert resp.status_code == 400  # move 缺 folder


def test_创建草稿与send_scope发送失败路径():
    client.post("/api/extkeys/enabled", json={"enabled": True})
    full_key = _make_key(["write", "send"])
    # 不存在的发件账号 → 400（先走内部校验，不产生草稿）
    resp = client.post("/api/ext/v1/drafts", headers=_headers(full_key["key"]),
                       json={"account_id": 999999, "to": "a@b.com", "subject": "x"})
    assert resp.status_code == 400
    # 发送不存在的草稿 → 404
    resp = client.post("/api/ext/v1/drafts/999999/approve", headers=_headers(full_key["key"]))
    assert resp.status_code == 404


def test_限流429(monkeypatch):
    from app.api import ext

    monkeypatch.setattr(ext, "RATE_LIMIT_PER_MIN", 2)
    client.post("/api/extkeys/enabled", json={"enabled": True})
    key = _make_key(["read"])
    for _ in range(2):
        assert client.get("/api/ext/v1/contacts", headers=_headers(key["key"])).status_code == 200
    resp = client.get("/api/ext/v1/contacts", headers=_headers(key["key"]))
    assert resp.status_code == 429


def test_每日上限429():
    client.post("/api/extkeys/enabled", json={"enabled": True})
    key = _make_key(["read"], daily_limit=1)
    assert client.get("/api/ext/v1/contacts", headers=_headers(key["key"])).status_code == 200
    assert client.get("/api/ext/v1/contacts", headers=_headers(key["key"])).status_code == 429


def test_密钥管理重置与吊销():
    key = _make_key(["read"])
    old = key["key"]
    # 重置：旧串失效、新串可用
    resp = client.patch(f"/api/extkeys/{key['id']}", json={"reset": True})
    assert resp.status_code == 200
    new = resp.json()["key"]["key"]
    assert new and new != old
    client.post("/api/extkeys/enabled", json={"enabled": True})
    assert client.get("/api/ext/v1/contacts", headers=_headers(old)).status_code == 401
    assert client.get("/api/ext/v1/contacts", headers=_headers(new)).status_code == 200
    # 吊销：立即失效、明文不再回显
    assert client.delete(f"/api/extkeys/{key['id']}").status_code == 200
    assert client.get("/api/ext/v1/contacts", headers=_headers(new)).status_code == 401
    listed = client.get("/api/extkeys").json()["keys"]
    row = next(k for k in listed if k["id"] == key["id"])
    assert row["revoked"] is True and "key" not in row


def test_host豁免只对ext路径():
    # 恶意 Host：ext 路径豁免来源校验（改持 Key），内部路径仍 403
    evil = {"Host": "evil.example.com"}
    assert client.get("/api/ext/v1/health", headers=evil).status_code == 200
    assert client.get("/api/health", headers=evil).status_code == 403
    # ext 无 Key 的 POST 仍被认证挡住（drive-by 兜底）
    resp = client.post("/api/ext/v1/emails/actions", headers=evil,
                       json={"ids": [1], "action": "read"})
    assert resp.status_code == 401


def test_调用日志落库():
    client.post("/api/extkeys/enabled", json={"enabled": True})
    key = _make_key(["read"])
    client.get("/api/ext/v1/contacts", headers=_headers(key["key"]))
    calls = client.get("/api/extkeys/calls").json()["calls"]
    assert calls, "应有调用日志"
    assert calls[0]["path"] == "/api/ext/v1/contacts"
    assert calls[0]["key_name"] == "t"
    # 未带 key 的 401 也留痕（key_id=0）
    client.get("/api/ext/v1/contacts")
    calls = client.get("/api/extkeys/calls").json()["calls"]
    assert calls[0]["status"] == 401


def test_agent未配AI返回400():
    client.post("/api/extkeys/enabled", json={"enabled": True})
    key = _make_key(["agent"])
    resp = client.post("/api/ext/v1/agent/chat", headers=_headers(key["key"]),
                       json={"question": "帮我看看收件箱"})
    assert resp.status_code == 400  # AINotConfigured → 400（未配置 AI）
