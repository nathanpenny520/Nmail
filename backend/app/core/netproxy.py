"""网络代理：让被墙服务商（Gmail/Outlook 等）的 IMAP/SMTP/OAuth 流量走本机代理。

背景（真实用户实测）：大陆网络裸连 imap.gmail.com 直接 10054/10060；浏览器与
httpx 能通是因为它们认代理，而 IMAP/SMTP 是裸 socket。本模块提供：

- 一个全局总开关（settings KV 键 `network_proxy_enabled`）：开=所有账号的
  IMAP/SMTP 收发与 OAuth 令牌交换一律走代理（正常软件语义，无账号级开关）；
  本机回环地址（Proton Bridge 等）始终直连
- 代理地址：手动地址（键 `network_proxy`，socks5/socks5h/socks4/http，可带
  user:pass@）留空时自动检测系统代理（urllib.getproxies：macOS 系统代理/
  Windows 注册表/HTTP(S)_PROXY 环境变量，每次连接现读——代理工具换端口无需改）
- OAuth 令牌交换代理建连失败自动直连兜底（Outlook 直连可达，不因代理配置
  错误被误伤；Gmail 直连必死则如实报错）

实现取舍：不全局替换 socket.socket（会波及 Proton Bridge 等本地回环连接，
且并发线程互相串代理）；改为子类注入——imaplib.IMAP4_SSL 覆盖
`_create_socket`、smtplib 覆盖 `_get_socket`，代理套接字用 PySocks
（纯 Python，零编译依赖；socks5 默认 rdns=True，域名由代理解析，规避 DNS 污染）。
"""
from __future__ import annotations

import imaplib
import smtplib
import socket
from urllib.parse import urlsplit

import socks

PROXY_ENABLED_KEY = "network_proxy_enabled"
PROXY_SETTING_KEY = "network_proxy"

_PROXY_SCHEMES: dict[str, tuple[int, int]] = {
    # scheme: (PySocks 类型, 默认端口)
    "socks5": (socks.SOCKS5, 1080),
    "socks5h": (socks.SOCKS5, 1080),  # h=远端解析；PySocks 默认即 rdns，同 socks5
    "socks4": (socks.SOCKS4, 1080),
    "http": (socks.HTTP, 8080),
}

_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "0.0.0.0"}


def is_local_host(host: str) -> bool:
    """本地回环地址永不走代理（Proton Bridge 等本机服务在代理端点侧不可达）。"""
    return (host or "").strip("[]").lower() in _LOCAL_HOSTS


def parse_proxy_url(raw: str) -> dict | None:
    """解析代理 URL；空串返回 None（直连）。非法输入抛 ValueError（面向用户）。"""
    url = (raw or "").strip()
    if not url:
        return None
    parsed = urlsplit(url)
    scheme = (parsed.scheme or "").lower()
    if scheme not in _PROXY_SCHEMES:
        raise ValueError(f"代理协议不支持：{scheme or '(空)'}，需为 socks5:// socks4:// 或 http://")
    if not parsed.hostname:
        raise ValueError("代理地址缺少主机名，形如 socks5://127.0.0.1:7890")
    ptype, default_port = _PROXY_SCHEMES[scheme]
    return {
        "type": ptype,
        "host": parsed.hostname,
        "port": parsed.port or default_port,
        "username": parsed.username or None,
        "password": parsed.password or None,
    }


def proxy_enabled() -> bool:
    """全局总开关（关=一律直连）。"""
    from app.db.database import get_setting

    return bool(get_setting(PROXY_ENABLED_KEY, False))


def proxy_url_setting() -> str:
    """手动代理地址原文（空=自动检测系统代理）。"""
    from app.db.database import get_setting

    return str(get_setting(PROXY_SETTING_KEY, "") or "")


def detect_system_proxy() -> str | None:
    """读系统代理（macOS 系统代理/Windows 注册表/HTTP(S)_PROXY 环境变量）。

    只是读配置记录——与本进程"会不会自动走代理"无关；读到地址后由本模块
    显式接管（PySocks）。代理工具开「系统代理」即自动识别，无需手抄地址。
    """
    import urllib.request

    proxies = urllib.request.getproxies()
    for scheme in ("https", "http", "socks"):
        url = proxies.get(scheme)
        if url:
            # macOS 系统代理的 SOCKS 项形如 socks://host:port；统一当 socks5 处理
            return f"socks5://{url[len('socks://'):]}" if url.startswith("socks://") else url
    return None


def effective_proxy_url() -> str | None:
    """总开关 ×（手动地址 → 系统探测）→ 实际使用的代理 URL；关/未配置返回 None。"""
    if not proxy_enabled():
        return None
    manual = proxy_url_setting().strip()
    return manual or detect_system_proxy()


def resolve_proxy() -> dict | None:
    """本连接实际使用的代理配置；不代理时返回 None。"""
    url = effective_proxy_url()
    if not url:
        return None
    try:
        return parse_proxy_url(url)
    except ValueError:
        return None  # 配置损坏时静默直连：连不上有 connection_error 兜底，不打断同步


def httpx_proxy_arg() -> str | None:
    """OAuth/autoconfig 等 httpx 调用的 proxy 参数（None=不显式指定，env 仍生效）。"""
    url = effective_proxy_url()
    if not url:
        return None
    try:
        parse_proxy_url(url)
    except ValueError:
        return None
    return url


def connect_socket(address: tuple[str, int], timeout: float | None, proxy: dict | None):
    """按配置建 TCP 连接：无代理/本地地址走系统直连，否则经 PySocks 套接字。"""
    host, port = address
    if proxy is None or is_local_host(host):
        return socket.create_connection(address, timeout)
    sock = socks.socksocket()
    sock.set_proxy(proxy["type"], proxy["host"], proxy["port"], True,
                   proxy["username"], proxy["password"])
    if timeout is not None:
        sock.settimeout(timeout)
    sock.connect((host, port))
    return sock


# ── 协议客户端注入（复刻 3.12+ 标准库行为，仅替换 TCP 建连一环）────

def imap4_ssl_class(proxy: dict | None) -> type[imaplib.IMAP4_SSL]:
    if proxy is None:
        return imaplib.IMAP4_SSL

    class _IMAP4SSLProxy(imaplib.IMAP4_SSL):
        def _create_socket(self, timeout):
            sock = connect_socket((self.host, self.port), timeout, proxy)
            return self.ssl_context.wrap_socket(sock, server_hostname=self.host)

    return _IMAP4SSLProxy


def smtp_class(proxy: dict | None, *, ssl: bool) -> type[smtplib.SMTP]:
    base = smtplib.SMTP_SSL if ssl else smtplib.SMTP
    if proxy is None:
        return base

    class _SMTPProxy(base):
        def _get_socket(self, host, port, timeout):
            sock = connect_socket((host, port), timeout, proxy)
            if ssl:
                return self.context.wrap_socket(sock, server_hostname=self._host)
            return sock

    return _SMTPProxy
