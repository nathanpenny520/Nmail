"""对外 API 测试（v0.4 P7，REDESIGN_PLAN §7）：Key 认证/scope 分级/限流、
密钥管理往返、Host 豁免边界、调用日志。端点薄壳转调既有实现，这里只测鉴权
与契约；agent 端点未配 AI 时应 400。
P1 补全（AGENT_SKILL_PLAN，2026-09-15）：错误 envelope、搜索过滤透传、
recent 游标、回复/转发草稿、正文三选一、草稿附件。"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

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


def _seed_account() -> int:
    conn = database.get_conn()
    cur = conn.execute(
        "INSERT INTO accounts (email, imap_server, imap_port) VALUES (?, 'imap.test', 993)",
        (f"x{uuid.uuid4().hex[:8]}@example.com",),
    )
    conn.commit()
    return int(cur.lastrowid)


def _seed_email(account_id: int, uid: int, subject: str, **extra) -> int:
    conn = database.get_conn()
    cols: dict = {
        "account_id": account_id, "folder": "INBOX", "uid": uid,
        "subject": subject, "sender_email": "boss@example.com", "body_text": "正文",
    }
    cols.update(extra)
    keys = ",".join(cols)
    cur = conn.execute(
        f"INSERT INTO emails ({keys}) VALUES ({','.join('?' * len(cols))})",
        tuple(cols.values()),
    )
    conn.commit()
    return int(cur.lastrowid)


def test_health_无认证可用():
    assert client.get("/api/ext/v1/health").status_code == 200


def test_未启用时有效key也403():
    client.post("/api/extkeys/enabled", json={"enabled": False})
    key = _make_key(["read"])
    resp = client.get("/api/ext/v1/accounts", headers=_headers(key["key"]))
    assert resp.status_code == 403
    body = resp.json()
    assert body["ok"] is False and "未启用" in body["error"]["message"]
    assert body["error"]["code"] == "forbidden"


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


# ── P1 补全（AGENT_SKILL_PLAN，2026-09-15）──────────────────────

def test_错误envelope统一():
    client.post("/api/extkeys/enabled", json={"enabled": True})
    # 401 → invalid_key
    resp = client.get("/api/ext/v1/accounts")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "invalid_key"
    # 404 → not_found
    key = _make_key(["read"])
    resp = client.get("/api/ext/v1/emails/999999", headers=_headers(key["key"]))
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"
    # 422（query 校验失败）→ invalid_params
    resp = client.get("/api/ext/v1/emails", params={"limit": "abc"}, headers=_headers(key["key"]))
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "invalid_params"
    # 内部 API 不受影响，仍 {"detail"} 原样
    resp = client.get("/api/emails", params={"after": "bad-date"})
    assert resp.status_code == 400
    assert "detail" in resp.json() and "ok" not in resp.json()


def test_限流429带Retry_After(monkeypatch):
    from app.api import ext

    monkeypatch.setattr(ext, "RATE_LIMIT_PER_MIN", 1)
    client.post("/api/extkeys/enabled", json={"enabled": True})
    key = _make_key(["read"])
    assert client.get("/api/ext/v1/contacts", headers=_headers(key["key"])).status_code == 200
    resp = client.get("/api/ext/v1/contacts", headers=_headers(key["key"]))
    assert resp.status_code == 429
    assert resp.json()["error"]["code"] == "rate_limited"
    assert resp.headers.get("retry-after") == "60"


def test_search_filters经ext透传():
    aid = _seed_account()
    e1 = _seed_email(aid, 1, "带附件的合同", sender_email="boss@example.com", has_attachments=1)
    _seed_email(aid, 2, "普通邮件", sender_email="other@example.com")
    client.post("/api/extkeys/enabled", json={"enabled": True})
    h = _headers(_make_key(["read"])["key"])
    resp = client.get("/api/ext/v1/emails", headers=h,
                      params={"account_id": aid, "sender": "boss@", "has_attachments": "true"})
    assert resp.status_code == 200
    assert [i["id"] for i in resp.json()["items"]] == [e1]
    # 非法日期 → 400 envelope
    resp = client.get("/api/ext/v1/emails", headers=h, params={"account_id": aid, "after": "bad"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "bad_request"


def test_吊销后彻底删除():
    """活跃行 DELETE=吊销（行保留）；已吊销行再 DELETE=彻底删除（列表消失，404 兜底）。"""
    key = _make_key(["read"])
    kid = key["id"]
    assert client.delete(f"/api/extkeys/{kid}").json() == {"ok": True, "purged": False}
    listed = client.get("/api/extkeys").json()["keys"]
    row = next(k for k in listed if k["id"] == kid)
    assert row["revoked"] is True and "key" not in row
    assert client.delete(f"/api/extkeys/{kid}").json() == {"ok": True, "purged": True}
    assert all(k["id"] != kid for k in client.get("/api/extkeys").json()["keys"])
    assert client.delete(f"/api/extkeys/{kid}").status_code == 404


def test_单条草稿读取_CLi发送摘要用():
    client.post("/api/extkeys/enabled", json={"enabled": True})
    key = _make_key(["read"])
    aid = _seed_account()
    resp = client.post("/api/user-drafts", json={"account_id": aid, "to_addrs": "a@b.com",
                                                 "subject": "s", "body_html": "<p>x</p>"})
    assert resp.status_code == 200
    did = resp.json()["draft"]["id"]
    r = client.get(f"/api/ext/v1/drafts/{did}", headers=_headers(key["key"]))
    assert r.status_code == 200
    assert r.json()["draft"]["id"] == did
    assert client.get("/api/ext/v1/drafts/999999", headers=_headers(key["key"])).status_code == 404
    client.delete(f"/api/user-drafts/{did}")


def test_recent游标轮询():
    aid = _seed_account()
    e1 = _seed_email(aid, 1, "第一封")
    e2 = _seed_email(aid, 2, "第二封")
    client.post("/api/extkeys/enabled", json={"enabled": True})
    h = _headers(_make_key(["read"])["key"])
    body = client.get("/api/ext/v1/emails/recent", headers=h,
                      params={"account_id": aid}).json()
    assert body["latest_id"] >= e2
    # since_id=e1 → 只返回 e2
    body = client.get("/api/ext/v1/emails/recent", headers=h,
                      params={"account_id": aid, "since_id": e1}).json()
    assert [i["id"] for i in body["items"]] == [e2]
    # 推进到 latest 后空轮询，游标不回退
    body = client.get("/api/ext/v1/emails/recent", headers=h,
                      params={"account_id": aid, "since_id": body["latest_id"]}).json()
    assert body["items"] == [] and body["latest_id"] >= e2


def test_正文三选一():
    aid = _seed_account()
    client.post("/api/extkeys/enabled", json={"enabled": True})
    h = _headers(_make_key(["write"])["key"])
    # 多选 → 400
    resp = client.post("/api/ext/v1/drafts", headers=h,
                       json={"account_id": aid, "to": "a@b.com",
                             "body_html": "<p>x</p>", "body_md": "# x"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "bad_request"
    # md → 带样式 HTML
    resp = client.post("/api/ext/v1/drafts", headers=h,
                       json={"account_id": aid, "to": "a@b.com", "body_md": "# 标题\n\n正文"})
    assert resp.status_code == 200, resp.text
    assert "<h1>" in resp.json()["draft"]["body_html"]
    # text → 转义 + 换行
    resp = client.post("/api/ext/v1/drafts", headers=h,
                       json={"account_id": aid, "to": "a@b.com", "body_text": "a<b\nc"})
    body = resp.json()["draft"]["body_html"]
    assert "&lt;b" in body and "<br />" in body
    # 清理测试草稿，零残留
    for d in client.get("/api/user-drafts", params={"status": "editing"}).json()["drafts"]:
        if d["account_id"] == aid:
            assert client.delete(f"/api/user-drafts/{d['id']}").status_code == 200


def test_reply_forward草稿():
    aid = _seed_account()
    eid = _seed_email(aid, 1, "项目排期", sender_email="boss@example.com",
                      recipients='["me@example.com"]', cc="[]")
    client.post("/api/extkeys/enabled", json={"enabled": True})
    h = _headers(_make_key(["write"])["key"])
    # 回复：Re: 主题、to=原发件人、in_reply_to、引用块、body_md 转 HTML
    resp = client.post("/api/ext/v1/drafts/reply", headers=h,
                       json={"email_id": eid, "body_md": "**收到**，明天回复。"})
    assert resp.status_code == 200, resp.text
    draft = resp.json()["draft"]
    assert draft["mode"] == "reply" and draft["in_reply_to"] == eid
    assert draft["to_addrs"] == "boss@example.com"
    assert draft["subject"].startswith("Re:")
    assert "<strong>收到</strong>" in draft["body_html"]
    assert "-------- 原始邮件 --------" in draft["body_html"]
    # reply_all：原收件人入 cc（剔除原发件人与本账号地址，与写信台同语义）
    conn = database.get_conn()
    own_email = conn.execute("SELECT email FROM accounts WHERE id = ?", (aid,)).fetchone()["email"]
    conn.execute("UPDATE emails SET recipients = ? WHERE id = ?",
                 (json.dumps([own_email, "colleague@example.com"]), eid))
    conn.commit()
    resp = client.post("/api/ext/v1/drafts/reply", headers=h,
                       json={"email_id": eid, "body_text": "好的", "reply_all": True})
    draft = resp.json()["draft"]
    assert draft["to_addrs"] == "boss@example.com"
    assert "colleague@example.com" in draft["cc_addrs"]
    assert own_email not in draft["cc_addrs"]
    # 转发：Fwd: 主题、不设 in_reply_to、引用块为「转发邮件」
    resp = client.post("/api/ext/v1/drafts/forward", headers=h,
                       json={"email_id": eid, "to": "a@x.com, b@x.com", "body_text": "请查收"})
    draft = resp.json()["draft"]
    assert draft["mode"] == "forward" and draft["in_reply_to"] is None
    assert draft["subject"].startswith("Fwd:")
    assert draft["to_addrs"] == "a@x.com,b@x.com"
    assert "-------- 转发邮件 --------" in draft["body_html"]
    # 边界：转发缺收件人 400 / 原邮件不存在 404
    resp = client.post("/api/ext/v1/drafts/forward", headers=h,
                       json={"email_id": eid, "body_text": "x"})
    assert resp.status_code == 400
    resp = client.post("/api/ext/v1/drafts/reply", headers=h, json={"email_id": 999999})
    assert resp.status_code == 404
    # 清理测试草稿
    for d in client.get("/api/user-drafts", params={"status": "editing"}).json()["drafts"]:
        if d["account_id"] == aid:
            assert client.delete(f"/api/user-drafts/{d['id']}").status_code == 200


def test_草稿附件上传与转发复制(tmp_path):
    aid = _seed_account()
    eid = _seed_email(aid, 1, "带附件的原始邮件")
    src = tmp_path / "report.pdf"
    src.write_bytes(b"%PDF-1.4 test")
    conn = database.get_conn()
    conn.execute(
        "INSERT INTO attachments (email_id, filename, mime, size, path)"
        " VALUES (?, 'report.pdf', 'application/pdf', ?, ?)",
        (eid, src.stat().st_size, str(src)),
    )
    conn.commit()
    client.post("/api/extkeys/enabled", json={"enabled": True})
    h = _headers(_make_key(["write"])["key"])
    # 建稿 + multipart 上传附件
    resp = client.post("/api/ext/v1/drafts", headers=h,
                       json={"account_id": aid, "to": "a@b.com", "subject": "s", "body_text": "正文"})
    draft_id = resp.json()["draft"]["id"]
    resp = client.post(f"/api/ext/v1/drafts/{draft_id}/attachments", headers=h,
                       files={"files": ("hello.txt", b"hello world", "text/plain")})
    assert resp.status_code == 200, resp.text
    atts = resp.json()["draft"]["attachments"]
    assert len(atts) == 1 and atts[0]["filename"] == "hello.txt" and atts[0]["size"] == 11
    # 转发复制原附件到草稿存储
    resp = client.post("/api/ext/v1/drafts/forward", headers=h,
                       json={"email_id": eid, "to": "c@x.com", "include_attachments": True})
    assert resp.status_code == 200, resp.text
    fwd_id = resp.json()["draft"]["id"]
    fwd_atts = resp.json()["draft"]["attachments"]
    assert len(fwd_atts) == 1 and fwd_atts[0]["filename"] == "report.pdf"
    row = conn.execute("SELECT path FROM user_draft_attachments WHERE id = ?",
                       (fwd_atts[0]["id"],)).fetchone()
    assert Path(row["path"]).read_bytes() == b"%PDF-1.4 test"
    # 清理测试草稿（磁盘文件随 delete_draft 清除）
    assert client.delete(f"/api/user-drafts/{draft_id}").status_code == 200
    assert client.delete(f"/api/user-drafts/{fwd_id}").status_code == 200
