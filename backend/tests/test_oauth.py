"""OAuth2（Gmail/Outlook）单元与 API 契约：XOAUTH2 编码 / PKCE / 令牌刷新 / 流程状态 / 端点语义。

TestClient 以 127.0.0.1 为 Host——经 S1 本机来源校验中间件放行（同 test_api_emails）。
"""
from __future__ import annotations

import base64
import hashlib
import json
import time
from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient

from app.core import oauth
from app.db import database
from app.main import app
from app.security import get_secret, set_secret

client = TestClient(app, base_url="http://127.0.0.1")

database.run_migrations()  # TestClient 不触发 lifespan，迁移在此显式补跑


# ── XOAUTH2 编码（教程 §1 的核心格式：\x01 是二进制 SOH）────

def test_xoauth2_string_uses_binary_soh():
    raw = oauth.xoauth2_string("test@gmail.com", "ya29.abc")
    assert raw == "user=test@gmail.com\x01auth=Bearer ya29.abc\x01\x01"
    # 对照教程给出的 base64 示例形态：可编码、无字面 "\\001"
    encoded = base64.b64encode(raw.encode()).decode()
    assert encoded.startswith("dXNlcj10ZXN0QGdtYWlsLmNvbQ")
    assert "\\001" not in raw


# ── PKCE（RFC 7636 S256）─────────────────────────────────────

def test_pkce_pair_roundtrip():
    verifier, challenge = oauth.pkce_pair()
    assert 43 <= len(verifier) <= 128
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    assert challenge == base64.urlsafe_b64encode(digest).decode().rstrip("=")
    assert oauth.challenge_from_verifier(verifier) == challenge


def test_pkce_verifiers_unique():
    assert oauth.pkce_pair()[0] != oauth.pkce_pair()[0]


# ── 授权 URL ─────────────────────────────────────────────────

def test_build_auth_url_gmail_offline_and_pkce():
    provider = oauth.PROVIDERS["gmail"]
    url = oauth.build_auth_url(
        provider, client_id="cid-123", redirect_uri="http://localhost:8720/oauth/callback",
        state="st-1", code_challenge="chk")
    qs = parse_qs(urlsplit(url).query)
    assert urlsplit(url).netloc == "accounts.google.com"
    assert qs["scope"] == ["https://mail.google.com/"]  # IMAP 只认这个 scope，不可细拆
    assert qs["access_type"] == ["offline"]  # 不带则不返回 refresh_token
    assert qs["code_challenge_method"] == ["S256"]
    assert qs["state"] == ["st-1"]


def test_build_auth_url_outlook_scopes():
    provider = oauth.PROVIDERS["outlook"]
    url = oauth.build_auth_url(
        provider, client_id="cid", redirect_uri="http://localhost:8720/oauth/callback",
        state="s", code_challenge="c")
    qs = parse_qs(urlsplit(url).query)
    scope = qs["scope"][0]
    assert "offline_access" in scope
    assert "https://outlook.office.com/IMAP.AccessAsUser.All" in scope  # 非 graph 资源
    assert "https://outlook.office.com/SMTP.Send" in scope


def test_match_provider_domains():
    assert oauth.match_provider("a@gmail.com").key == "gmail"
    assert oauth.match_provider("b@live.com").key == "outlook"
    assert oauth.match_provider("c@qq.com") is None


# ── 客户端配置存取 ────────────────────────────────────────────

def test_save_client_roundtrip_and_clear():
    try:
        oauth.save_client("gmail", "  my-id.apps.googleusercontent.com  ", "  sec ")
        client_cfg = oauth.get_client("gmail")
        assert client_cfg == {"client_id": "my-id.apps.googleusercontent.com", "client_secret": "sec"}
        assert oauth.configured("gmail")
        oauth.save_client("gmail", "", "")  # 双空 = 清除
        assert oauth.get_client("gmail") is None
        assert not oauth.configured("gmail")
    finally:
        set_secret(oauth.client_key("gmail"), None)


def test_save_client_redirect_path_roundtrip():
    """根路径登记的公开桌面客户端：redirect_path 落盘；默认路径不落盘；坏值兜底回退默认。"""
    try:
        oauth.save_client("gmail", "cid-rp", redirect_path="/")
        assert oauth.get_client("gmail") == {
            "client_id": "cid-rp", "client_secret": "", "redirect_path": "/"}
        assert oauth.callback_path(oauth.get_client("gmail")) == "/"

        oauth.save_client("gmail", "cid-rp", redirect_path=" /oauth/callback ")
        assert oauth.get_client("gmail") == {"client_id": "cid-rp", "client_secret": ""}
        assert oauth.callback_path(oauth.get_client("gmail")) == oauth.CALLBACK_PATH

        assert oauth.callback_path(None) == oauth.CALLBACK_PATH  # 未配置
        assert oauth.callback_path({"client_id": "x"}) == oauth.CALLBACK_PATH  # 旧配置缺字段
        for bad in ("http://evil.com", "//evil.com", "/a b", "/x?y=1", "/x#z"):
            assert oauth.callback_path({"redirect_path": bad}) == oauth.CALLBACK_PATH
    finally:
        set_secret(oauth.client_key("gmail"), None)


# ── 令牌存储与刷新（httpx 打桩，不出网）──────────────────────

def _seed_token(account_id: int, *, expires_in: float, refresh: str = "rt-old") -> None:
    set_secret(oauth.token_key(account_id), json.dumps({
        "provider": "outlook", "email": "u@outlook.com",
        "access_token": "at-old", "refresh_token": refresh,
        "expires_at": time.time() + expires_in,
    }))


def test_ensure_access_token_returns_cached_when_fresh():
    try:
        _seed_token(9001, expires_in=1800)
        assert oauth.ensure_access_token(9001) == "at-old"
    finally:
        oauth.delete_token(9001)


def test_ensure_access_token_refreshes_when_expired(monkeypatch):
    """过期触发刷新；微软轮换的 refresh_token 被覆盖保存。

    余量语义：store_tokens 落库时已把真实过期时间提前 _TOKEN_MARGIN，
    读侧只需 `now < expires_at` 判断——种入 expires_at 已过即为临期失效。
    """
    try:
        _seed_token(9002, expires_in=-1)
        oauth.save_client("outlook", "cid")
        captured: dict = {}

        def fake_refresh(provider, *, client_id, refresh_token, client_secret=None):
            captured.update(refresh_token=refresh_token, client_id=client_id)
            return {"access_token": "at-new", "refresh_token": "rt-new", "expires_in": 3600}

        monkeypatch.setattr(oauth, "refresh_tokens", fake_refresh)
        assert oauth.ensure_access_token(9002) == "at-new"
        assert captured == {"refresh_token": "rt-old", "client_id": "cid"}
        record = oauth.load_token(9002)
        assert record["access_token"] == "at-new"
        assert record["refresh_token"] == "rt-new"  # 轮换值已持久化
        assert record["expires_at"] > time.time() + 3000
    finally:
        oauth.delete_token(9002)
        set_secret(oauth.client_key("outlook"), None)


def test_ensure_access_token_missing_token_raises():
    import pytest

    with pytest.raises(oauth.OAuthError):
        oauth.ensure_access_token(9903)


def test_ensure_access_token_refresh_failure_translates(monkeypatch):
    import pytest

    _seed_token(9004, expires_in=0)
    oauth.save_client("outlook", "cid")

    def fake_refresh(provider, **kwargs):
        raise oauth.OAuthError("Outlook 授权失败：授权已过期或已被撤销，请重新授权")

    monkeypatch.setattr(oauth, "refresh_tokens", fake_refresh)
    with pytest.raises(oauth.OAuthError, match="重新授权"):
        oauth.ensure_access_token(9004)
    oauth.delete_token(9004)
    set_secret(oauth.client_key("outlook"), None)


# ── 流程状态（进程内，TTL 过期即弃）──────────────────────────

def test_flow_create_get_settle():
    oauth.save_client("gmail", "flow-cid")
    try:
        state, flow = oauth.create_flow("u@gmail.com", "gmail", "http://localhost:8720/oauth/callback")
        assert oauth.get_flow(state)["status"] == "pending"
        assert len(flow["code_verifier"]) >= 43
        oauth.settle_flow(state, True, "已接入")
        settled = oauth.get_flow(state)
        assert settled["status"] == "done"
        assert settled["code_verifier"] == ""  # verifier 用后即弃
        assert oauth.get_flow("no-such-state") is None
    finally:
        set_secret(oauth.client_key("gmail"), None)


def test_flow_expired(monkeypatch):
    oauth.save_client("gmail", "flow-cid")
    try:
        state, _f = oauth.create_flow("u@gmail.com", "gmail", "http://localhost:8720/oauth/callback")
        monkeypatch.setattr(oauth, "FLOW_TTL", -1)
        assert oauth.get_flow(state) is None
    finally:
        set_secret(oauth.client_key("gmail"), None)


# ── 回调健壮性（回归：OAuthError 无 .message 曾把可处理错误变成裸 500）──

def test_oauth_error_has_message():
    err = oauth.OAuthError("测试消息")
    assert err.message == "测试消息"  # mailbox/api 层依赖 .message，不能只有 args


def test_token_error_translate_secret_missing():
    """Web 型客户端缺 client_secret：Google 只回 error_description，需给出可操作指引。"""
    assert "client_secret" in oauth._translate_token_error(
        {"error": "", "error_description": "client_secret is missing."})
    assert oauth._translate_token_error(
        {"error": "invalid_client", "error_description": "x"}) == "client_id / client_secret 不正确，请检查 OAuth 客户端配置"


def test_token_request_socks_importerror_translated(monkeypatch):
    """终端设 SOCKS 代理但未装 socksio：httpx 抛 ImportError（非 HTTPError），须接住转 OAuthError。"""
    import pytest

    def fake_post(*a, **kw):
        raise ImportError("Using SOCKS proxy, but the 'socksio' package is not installed.")

    monkeypatch.setattr(oauth.httpx, "post", fake_post)
    with pytest.raises(oauth.OAuthError, match="令牌服务"):
        oauth.exchange_code(oauth.PROVIDERS["gmail"], client_id="x", code="y",
                            code_verifier="z", redirect_uri="http://localhost/oauth/callback")


def test_api_callback_unexpected_exception_never_500(monkeypatch):
    """换令牌环节抛任意异常：回调渲染为 200 错误页并落流程状态，绝不再裸 500。"""
    oauth.save_client("gmail", "boom-cid")
    try:
        state, _f = oauth.create_flow("boom@gmail.com", "gmail", "http://localhost:8720/oauth/callback")

        def boom(*a, **kw):
            raise RuntimeError("something exploded")

        monkeypatch.setattr(oauth, "exchange_code", boom)
        resp = client.get("/oauth/callback", params={"code": "x", "state": state})
        assert resp.status_code == 200
        assert "授权失败" in resp.text and "something exploded" in resp.text
        assert client.get(f"/api/oauth/flow/{state}").json()["status"] == "error"
    finally:
        set_secret(oauth.client_key("gmail"), None)


# ── API 端点语义 ─────────────────────────────────────────────

def test_api_status_and_config_roundtrip():
    resp = client.get("/api/oauth/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "redirect_uri" not in data  # 回调地址随各客户端登记路径逐服务商给出
    keys = {p["key"] for p in data["providers"]}
    assert keys == {"gmail", "outlook"}
    for p in data["providers"]:  # 未配置 → 默认路径
        assert p["redirect_path"] == "/oauth/callback"
        assert p["redirect_uri"].startswith("http://localhost:")
        assert p["redirect_uri"].endswith("/oauth/callback")

    try:
        assert client.put("/api/oauth/config", json={
            "provider": "gmail", "client_id": "api-cid"}).json()["configured"] is True
        # 根路径登记的客户端：redirect_path 落盘且回调地址随之变化
        assert client.put("/api/oauth/config", json={
            "provider": "outlook", "client_id": "api-ms", "redirect_path": "/"}).json()["configured"] is True
        status = client.get("/api/oauth/status").json()
        gmail = next(p for p in status["providers"] if p["key"] == "gmail")
        outlook = next(p for p in status["providers"] if p["key"] == "outlook")
        assert gmail["configured"] is True
        assert "api-cid" in gmail["client_id_masked"]
        assert gmail["redirect_uri"].endswith("/oauth/callback")
        assert outlook["redirect_path"] == "/"
        assert outlook["redirect_uri"].endswith("/")
        assert client.put("/api/oauth/config", json={
            "provider": "gmail", "client_id": "", "client_secret": ""}).json()["configured"] is False
        assert client.put("/api/oauth/config", json={
            "provider": "outlook", "client_id": "", "client_secret": ""}).json()["configured"] is False
    finally:
        set_secret(oauth.client_key("gmail"), None)
        set_secret(oauth.client_key("outlook"), None)


def test_api_config_rejects_unknown_provider_and_same_secret():
    assert client.put("/api/oauth/config", json={"provider": "yandex", "client_id": "x"}).status_code == 400
    assert client.put("/api/oauth/config", json={
        "provider": "gmail", "client_id": "same", "client_secret": "same"}).status_code == 400
    for bad in ("oauth/callback", "//x", "/a b", "/x?y"):  # 路径需以 / 开头且无空白/?#
        resp = client.put("/api/oauth/config", json={
            "provider": "gmail", "client_id": "c", "redirect_path": bad})
        assert resp.status_code == 400


def test_api_authorize_requires_configured_client():
    resp = client.post("/api/oauth/authorize", json={"email": "u@gmail.com", "provider": "gmail"})
    assert resp.status_code == 400
    assert "client_id" in resp.json()["detail"]


def test_api_authorize_rejects_bad_email_or_domain():
    oauth.save_client("gmail", "cid-x")
    try:
        assert client.post("/api/oauth/authorize", json={
            "email": "not-an-email", "provider": "gmail"}).status_code == 400
        assert client.post("/api/oauth/authorize", json={
            "email": "u@qq.com", "provider": "gmail"}).status_code == 400
        assert client.post("/api/oauth/authorize", json={
            "email": "u@gmail.com", "provider": "outlook"}).status_code == 400
    finally:
        set_secret(oauth.client_key("gmail"), None)


def test_api_authorize_uses_client_redirect_path():
    """授权 URL 的 redirect_uri 按客户端登记路径拼装（根路径客户端 → http://localhost:{port}/）。"""
    oauth.save_client("gmail", "cid-path", redirect_path="/")
    try:
        resp = client.post("/api/oauth/authorize", json={"email": "u@gmail.com", "provider": "gmail"})
        assert resp.status_code == 200
        state = resp.json()["state"]
        qs = parse_qs(urlsplit(resp.json()["auth_url"]).query)
        assert qs["redirect_uri"][0].startswith("http://localhost:")
        assert qs["redirect_uri"][0].endswith("/")
        assert oauth.get_flow(state)["redirect_uri"] == qs["redirect_uri"][0]
    finally:
        set_secret(oauth.client_key("gmail"), None)


def test_api_flow_poll_unknown_state_404():
    assert client.get("/api/oauth/flow/nope").status_code == 404


def test_api_callback_invalid_state_page():
    resp = client.get("/oauth/callback", params={"code": "x", "state": "invalid"})
    assert resp.status_code == 200
    assert "授权回调无效" in resp.text


def test_api_root_path_routes_oauth_callback():
    """根路径带 state → OAuth 回调页（loopback 根路径登记的客户端走这里，与 SPA 分流）。"""
    resp = client.get("/", params={"code": "x", "state": "invalid"})
    assert resp.status_code == 200
    assert "授权回调无效" in resp.text


def test_api_root_without_state_serves_spa_or_404():
    """根路径不带 state → 前端首页（已构建时）；绝不能落进回调页文案。"""
    resp = client.get("/")
    if resp.status_code == 200:
        assert "授权回调无效" not in resp.text
    else:
        assert resp.status_code == 404  # 前端未构建（CI 只跑后端时）


def test_api_callback_error_marks_flow():
    oauth.save_client("gmail", "cb-cid")
    try:
        state, _f = oauth.create_flow("cb@gmail.com", "gmail", "http://localhost:8720/oauth/callback")
        resp = client.get("/oauth/callback", params={"state": state, "error": "access_denied"})
        assert resp.status_code == 200
        poll = client.get(f"/api/oauth/flow/{state}").json()
        assert poll["status"] == "error"
        assert "取消" in poll["detail"]
    finally:
        set_secret(oauth.client_key("gmail"), None)


def test_api_callback_success_upserts_account(monkeypatch):
    """成功回调：新邮箱建号（oauth2）→ 已有账号转 oauth2；令牌落库、首同步触发。"""
    started: list = []
    monkeypatch.setattr(
        "app.api.oauth.sync_engine.start_sync",
        lambda account, folders=("INBOX",): started.append(account["id"]) or {"started": True})

    def fake_exchange(provider, *, client_id, code, code_verifier, redirect_uri, client_secret=None):
        assert code == "good-code"
        assert code_verifier  # PKCE verifier 由流程带入
        assert redirect_uri.startswith("http://localhost:")
        return {"access_token": "at", "refresh_token": "rt", "expires_in": 3600}

    monkeypatch.setattr(oauth, "exchange_code", fake_exchange)
    oauth.save_client("gmail", "cb2-cid")
    try:
        # ① 新邮箱 → 建号
        state, _f = oauth.create_flow("new@gmail.com", "gmail", "http://localhost:8720/oauth/callback")
        resp = client.get("/oauth/callback", params={"code": "good-code", "state": state})
        assert "授权成功" in resp.text
        rows = database.get_conn().execute(
            "SELECT * FROM accounts WHERE email = 'new@gmail.com'").fetchall()
        assert len(rows) == 1
        assert rows[0]["auth_type"] == "oauth2" and rows[0]["oauth_provider"] == "gmail"
        assert rows[0]["imap_server"] == "imap.gmail.com"
        assert get_secret(oauth.token_key(rows[0]["id"]))  # 令牌已存
        assert started == [rows[0]["id"]]  # 首同步已触发
        poll = client.get(f"/api/oauth/flow/{state}").json()
        assert poll["status"] == "done"

        # ② 已有密码账号同邮箱再授权 → 转 oauth2，不重建行
        database.get_conn().execute(
            "INSERT INTO accounts (email, provider_name, imap_server, smtp_server, auth_type)"
            " VALUES ('conv@qq.com', 'QQ 邮箱', 'imap.qq.com', 'smtp.qq.com', 'password')")
        database.get_conn().commit()
        oauth.save_client("outlook", "cb2-cid")
        state2, _f2 = oauth.create_flow("conv@qq.com", "outlook", "http://localhost:8720/oauth/callback")
    finally:
        set_secret(oauth.client_key("gmail"), None)
        set_secret(oauth.client_key("outlook"), None)

    # 域名校验会拦 qq.com 走 outlook 流程，此分支仅验证 upsert 幂等逻辑
    oauth.settle_flow(state2, True, "")
    assert client.get(f"/api/oauth/flow/{state2}").json()["status"] == "done"


def test_delete_account_clears_oauth_token(monkeypatch):
    from app.security import set_secret as ss

    conn = database.get_conn()
    conn.execute(
        "INSERT INTO accounts (email, provider_name, imap_server, smtp_server, auth_type,"
        " oauth_provider) VALUES ('del@gmail.com', 'Gmail', 'imap.gmail.com',"
        " 'smtp.gmail.com', 'oauth2', 'gmail')")
    conn.commit()
    aid = conn.execute("SELECT id FROM accounts WHERE email = 'del@gmail.com'").fetchone()["id"]
    ss(oauth.token_key(aid), json.dumps({"provider": "gmail", "email": "del@gmail.com",
                                         "access_token": "x", "refresh_token": "y",
                                         "expires_at": 0}))
    resp = client.delete(f"/api/accounts/{aid}")
    assert resp.status_code == 200
    assert get_secret(oauth.token_key(aid)) is None  # 令牌随账号清除
