"""网络代理（Gmail/Outlook 被墙场景）：URL 解析 / 直连豁免 / 套接字注入 / 总开关契约。

不建真实网络连接；建连行为以「传给 connect_socket 的配置」断言。
"""
from __future__ import annotations

import socks
from contextlib import suppress

from fastapi.testclient import TestClient

from app.core import imap_client, netproxy, oauth
from app.db import database
from app.main import app

client = TestClient(app, base_url="http://127.0.0.1")

database.run_migrations()


# ── URL 解析 ─────────────────────────────────────────────────

def test_parse_proxy_url_forms():
    assert netproxy.parse_proxy_url("") is None
    assert netproxy.parse_proxy_url("   ") is None
    p = netproxy.parse_proxy_url("socks5://127.0.0.1:7890")
    assert p == {"type": socks.SOCKS5, "host": "127.0.0.1", "port": 7890,
                 "username": None, "password": None}
    p = netproxy.parse_proxy_url("socks5h://u:p@proxy.lan")
    assert p["type"] == socks.SOCKS5 and p["port"] == 1080  # 默认端口
    assert p["username"] == "u" and p["password"] == "p"
    p = netproxy.parse_proxy_url("http://192.168.1.1:8888")
    assert p["type"] == socks.HTTP and p["port"] == 8888
    p = netproxy.parse_proxy_url("socks4://a.b")
    assert p["type"] == socks.SOCKS4 and p["port"] == 1080


def test_parse_proxy_url_rejects_bad():
    import pytest

    for bad in ("ftp://x", "socks5://", "plain-host:7890", "https://x"):
        with pytest.raises(ValueError):
            netproxy.parse_proxy_url(bad)


def test_is_local_host_never_proxied():
    for host in ("127.0.0.1", "localhost", "::1", "[::1]"):
        assert netproxy.is_local_host(host)
    assert not netproxy.is_local_host("imap.gmail.com")


# ── resolve：总开关 ×（手动地址 → 系统探测）──────────────────

def test_resolve_proxy_by_enabled_and_url(monkeypatch):
    try:
        database.set_setting(netproxy.PROXY_SETTING_KEY, "socks5://127.0.0.1:7890")
        database.set_setting(netproxy.PROXY_ENABLED_KEY, False)
        assert netproxy.resolve_proxy() is None  # 开关未开 → 直连（地址存着也不走）

        database.set_setting(netproxy.PROXY_ENABLED_KEY, True)
        assert netproxy.resolve_proxy()["port"] == 7890

        database.set_setting(netproxy.PROXY_SETTING_KEY, "")
        monkeypatch.setattr(netproxy, "detect_system_proxy", lambda: "http://192.168.1.1:8888")
        assert netproxy.resolve_proxy()["port"] == 8888  # 手动留空 → 系统探测兜底
        monkeypatch.setattr(netproxy, "detect_system_proxy", lambda: None)
        assert netproxy.resolve_proxy() is None          # 手动/探测都没有 → 直连

        database.set_setting(netproxy.PROXY_SETTING_KEY, "broken-url")
        monkeypatch.setattr(netproxy, "detect_system_proxy", lambda: "http://x:1")
        assert netproxy.resolve_proxy() is None  # 手动地址损坏 → 静默直连，不炸同步
    finally:
        database.set_setting(netproxy.PROXY_SETTING_KEY, "")
        database.set_setting(netproxy.PROXY_ENABLED_KEY, False)


def test_detect_system_proxy(monkeypatch):
    import urllib.request

    monkeypatch.setattr(urllib.request, "getproxies",
                        lambda: {"http": "http://127.0.0.1:7890", "https": "http://127.0.0.1:7890"})
    assert netproxy.detect_system_proxy() == "http://127.0.0.1:7890"
    monkeypatch.setattr(urllib.request, "getproxies", lambda: {"socks": "socks://127.0.0.1:1080"})
    assert netproxy.detect_system_proxy() == "socks5://127.0.0.1:1080"  # socks:// 归一为 socks5
    monkeypatch.setattr(urllib.request, "getproxies", lambda: {})
    assert netproxy.detect_system_proxy() is None


def test_httpx_proxy_arg_follows_setting():
    try:
        database.set_setting(netproxy.PROXY_SETTING_KEY, "socks5://127.0.0.1:7890")
        database.set_setting(netproxy.PROXY_ENABLED_KEY, True)
        assert netproxy.httpx_proxy_arg() == "socks5://127.0.0.1:7890"
        database.set_setting(netproxy.PROXY_ENABLED_KEY, False)
        assert netproxy.httpx_proxy_arg() is None  # 关=直连
    finally:
        database.set_setting(netproxy.PROXY_SETTING_KEY, "")
        database.set_setting(netproxy.PROXY_ENABLED_KEY, False)


# ── 建连注入：IMAP/SMTP 客户端类选择与 PySocks 套接字 ────────

def test_connect_socket_direct_vs_proxied(monkeypatch):
    made: list[dict] = []
    direct: list[tuple] = []

    class FakeSock:
        def set_proxy(self, ptype, host, port, rdns, user, pwd):
            made.append({"type": ptype, "host": host, "port": port, "rdns": rdns})

        def settimeout(self, t):
            made[-1]["timeout"] = t

        def connect(self, addr):
            made[-1]["addr"] = addr

    monkeypatch.setattr(netproxy.socks, "socksocket", FakeSock)
    monkeypatch.setattr(netproxy.socket, "create_connection",
                        lambda addr, timeout=None: direct.append(addr) or FakeSock())

    netproxy.connect_socket(("imap.qq.com", 993), 8, None)  # 无代理 → 系统直连
    assert made == [] and direct == [("imap.qq.com", 993)]

    proxy = netproxy.parse_proxy_url("socks5://127.0.0.1:7890")
    netproxy.connect_socket(("imap.gmail.com", 993), 8, proxy)
    assert made[-1] == {"type": socks.SOCKS5, "host": "127.0.0.1", "port": 7890,
                        "rdns": True, "timeout": 8, "addr": ("imap.gmail.com", 993)}

    netproxy.connect_socket(("127.0.0.1", 1143), 8, proxy)  # 本地回环（Proton Bridge）→ 直连豁免
    assert len(made) == 1 and direct[-1] == ("127.0.0.1", 1143)


def test_client_class_selection(monkeypatch):
    proxy = netproxy.parse_proxy_url("socks5://127.0.0.1:7890")
    assert netproxy.imap4_ssl_class(None) is stdlib_imap4_ssl()
    assert netproxy.imap4_ssl_class(proxy) is not stdlib_imap4_ssl()
    assert netproxy.smtp_class(None, ssl=True) is smtp_ssl()
    assert netproxy.smtp_class(None, ssl=False) is smtp_plain()
    assert netproxy.smtp_class(proxy, ssl=True) is not smtp_ssl()


def stdlib_imap4_ssl():
    import imaplib
    return imaplib.IMAP4_SSL


def smtp_ssl():
    import smtplib
    return smtplib.SMTP_SSL


def smtp_plain():
    import smtplib
    return smtplib.SMTP


def test_connect_imap_uses_proxied_class_when_enabled(monkeypatch):
    """connect_imap 按总开关选代理客户端类并完成装配（FakeIMAP4 拦截真连）。"""
    calls: list[tuple] = []

    class FakeIMAP4:
        def __init__(self, host, port, ssl_context=None, timeout=None):  # noqa: ANN001
            calls.append((host, port, timeout))

    monkeypatch.setattr(netproxy, "resolve_proxy", lambda: {"t": 1})
    monkeypatch.setattr(netproxy, "imap4_ssl_class", lambda proxy: FakeIMAP4)
    cfg = imap_client.MailConfig(email="x@gmail.com", password="p",
                                 imap_server="imap.gmail.com")
    with suppress(Exception):  # 登录在假客户端上必然报错，只验建连装配
        imap_client.connect_imap(cfg)
    assert calls == [("imap.gmail.com", 993, 60)]


# ── OAuth 换令牌通道降级（Outlook 不该被坏代理配置误伤）──────

def _token_response(payload: dict, status: int = 200):
    import httpx as _httpx
    return _httpx.Response(status, json=payload)


def test_token_exchange_proxy_dead_falls_back_to_direct(monkeypatch):
    """代理端口拒绝（10061 类）：自动降级直连再试一次——Outlook 直连可达。"""
    import httpx as httpx_mod

    calls: list = []

    def fake_post(url, data, headers=None, timeout=None, proxy=None):
        calls.append(proxy)
        if proxy is not None:
            raise httpx_mod.ConnectError("[WinError 10061] 由于目标计算机积极拒绝，无法连接。")
        return _token_response({"access_token": "at", "refresh_token": "rt", "expires_in": 3600})

    monkeypatch.setattr(oauth.httpx, "post", fake_post)
    database.set_setting(netproxy.PROXY_SETTING_KEY, "socks5://127.0.0.1:7890")
    database.set_setting(netproxy.PROXY_ENABLED_KEY, True)
    try:
        tokens = oauth.exchange_code(oauth.PROVIDERS["outlook"], client_id="c", code="x",
                                     code_verifier="v", redirect_uri="http://localhost/cb")
        assert tokens["access_token"] == "at"
        assert calls[0] == "socks5://127.0.0.1:7890"  # 先走代理
        assert calls[1] is None                        # 代理拒绝后直连兜底
    finally:
        database.set_setting(netproxy.PROXY_SETTING_KEY, "")
        database.set_setting(netproxy.PROXY_ENABLED_KEY, False)


def test_token_exchange_business_error_no_direct_retry(monkeypatch):
    """代理通但业务拒绝（invalid_client）：直连结果相同，不浪费一次重试。"""
    calls: list = []

    def fake_post(url, data, headers=None, timeout=None, proxy=None):
        calls.append(proxy)
        return _token_response({"error": "invalid_client"}, status=401)

    monkeypatch.setattr(oauth.httpx, "post", fake_post)
    database.set_setting(netproxy.PROXY_SETTING_KEY, "socks5://127.0.0.1:7890")
    database.set_setting(netproxy.PROXY_ENABLED_KEY, True)
    try:
        import pytest
        # invalid_client 被翻译为人话提示，见 _translate_token_error
        with pytest.raises(oauth.OAuthError, match="不正确"):
            oauth.exchange_code(oauth.PROVIDERS["outlook"], client_id="c", code="x",
                                code_verifier="v", redirect_uri="http://localhost/cb")
        assert calls == ["socks5://127.0.0.1:7890"]  # 只试了代理一次
    finally:
        database.set_setting(netproxy.PROXY_SETTING_KEY, "")
        database.set_setting(netproxy.PROXY_ENABLED_KEY, False)


def test_token_exchange_no_proxy_stays_direct(monkeypatch):
    """未配置代理：只直连一次（环境变量仍由 httpx trust_env 生效），不折腾。"""
    calls: list = []

    def fake_post(url, data, headers=None, timeout=None, proxy=None):
        calls.append(proxy)
        return _token_response({"access_token": "at", "expires_in": 3600})

    monkeypatch.setattr(oauth.httpx, "post", fake_post)
    database.set_setting(netproxy.PROXY_SETTING_KEY, "")
    tokens = oauth.exchange_code(oauth.PROVIDERS["gmail"], client_id="c", code="x",
                                 code_verifier="v", redirect_uri="http://localhost/cb")
    assert tokens["access_token"] == "at" and calls == [None]


# ── SMTP XOAUTH2 回调契约（回归：smtplib 首次无参调用曾致发信必败）──

def test_smtp_auth_callback_accepts_initial_and_challenge():
    """smtplib.auth 先无参调用取初始响应、334 挑战时带参调用（XOAUTH2 回空串）。"""
    cfg = imap_client.MailConfig(
        email="x@gmail.com", password="", imap_server="imap.gmail.com",
        smtp_server="smtp.gmail.com", access_token="tok123")
    captured: dict = {}

    class FakeServer:
        def auth(self, mechanism, authobject, *, initial_response_ok=True):
            captured["mech"] = mechanism
            captured["initial"] = authobject()          # 无参：初始响应
            captured["challenge"] = authobject(b"err")  # 334 挑战：应回空串

    imap_client._smtp_auth(FakeServer(), cfg)
    assert captured["mech"] == "XOAUTH2"
    assert captured["initial"] == oauth.xoauth2_string("x@gmail.com", "tok123")
    assert captured["challenge"] == ""


# ── 设置 API ─────────────────────────────────────────────────

def test_settings_network_proxy_roundtrip():
    try:
        resp = client.put("/api/settings", json={"network_proxy": "socks5://127.0.0.1:7890",
                                                 "network_proxy_enabled": True},
                          headers={"Origin": "http://127.0.0.1"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["network_proxy"] == "socks5://127.0.0.1:7890"
        assert body["network_proxy_enabled"] is True
        assert "detected_proxy" in body  # 系统探测结果只读回传（供设置页展示）
        bad = client.put("/api/settings", json={"network_proxy": "ftp://x"},
                         headers={"Origin": "http://127.0.0.1"})
        assert bad.status_code == 422  # 非法协议即时拒绝（与 digest_time 等校验同型）
    finally:
        client.put("/api/settings", json={"network_proxy": "", "network_proxy_enabled": False},
                   headers={"Origin": "http://127.0.0.1"})
