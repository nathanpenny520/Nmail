"""Gmail / Outlook.com OAuth2（XOAUTH2）授权与令牌管理。

授权码 + PKCE 流程：浏览器在 Google/微软完成登录后，回环回调打到本机
/oauth/callback（API 层），后端凭 code + code_verifier 换令牌。OAuth 客户端
由用户自建（client_id 填在设置页，教程见 docs/自建邮箱客户端
Gmail+Outlook OAuth2 完整教程.md），Nmail 不内置凭据。

存储约定（secrets.json）：
- oauth_client:{provider} → JSON {client_id, client_secret?, redirect_path?}
  （secret 可选：桌面型客户端走纯 PKCE 不需要；Web 型客户端必填。redirect_path
  为该客户端在服务商控制台登记的回调路径，缺省 CALLBACK_PATH——登记为
  loopback 根路径的公开桌面客户端填 "/"，Google/微软只豁免端口不豁免路径）
- oauth_token:{account_id} → JSON {provider, email, access_token, refresh_token,
  expires_at}（expires_at 为本地 Unix 时间戳，提前 _TOKEN_MARGIN 秒刷新；
  微软 v2 端点轮换 refresh_token，轮换值随保存覆盖）

XOAUTH2 编码（Gmail/Outlook 共用，\x01 为二进制 SOH，教程 §1）：
user=<email>\\x01auth=Bearer <token>\\x01\\x01 → base64
"""
from __future__ import annotations

import base64
import hashlib
import json
import secrets as _secrets
import threading
import time
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

from app.core import netproxy
from app.security import get_secret, has_secret, set_secret

CALLBACK_PATH = "/oauth/callback"
FLOW_TTL = 600  # 授权流程状态有效期（秒），过期即弃
# 根路径（TB 等公开桌面客户端的 loopback 登记）。api 层据此在 "/" 上挂回调，
# 以 state 参数与 SPA 首页分流
ROOT_CALLBACK_PATH = "/"


def callback_path(client: dict | None) -> str:
    """客户端登记的回调路径；未配置或旧配置缺省时用默认值。

    校验宽松放行：仅接受以单个 / 开头、无空白/查询串的路径，其余一律回退默认——
    坏值不应让授权流程瘫痪，且用户能从设置页回显的完整地址立刻看出问题。
    """
    if client:
        path = str(client.get("redirect_path") or "").strip()
        if path.startswith("/") and not path.startswith("//") \
                and not any(c.isspace() or c in "?#" for c in path):
            return path
    return CALLBACK_PATH
_TOKEN_MARGIN = 120  # access_token 提前刷新余量（秒）

_TOKEN_ERR_HINT = {
    "invalid_grant": "授权已过期或已被撤销，请重新授权",
    "invalid_client": "client_id / client_secret 不正确，请检查 OAuth 客户端配置",
    "redirect_uri_mismatch": "回调地址与 OAuth 客户端登记的不一致，请按设置页显示的地址登记",
    "unauthorized_client": "该 OAuth 客户端类型不允许此流程，请检查客户端创建时的类型选择",
}


class OAuthError(Exception):
    """面向用户的 OAuth 错误（消息不含令牌内容）。"""

    def __init__(self, message: str, *, transport: bool = False):
        super().__init__(message)
        self.message = message
        # transport=True 表示建连失败（代理/网络不可达），调用方可换通道重试；
        # 业务拒绝（invalid_client 等）重试无意义
        self.transport = transport


@dataclass(frozen=True)
class OAuthProvider:
    key: str
    name: str
    domains: tuple[str, ...]
    auth_url: str
    token_url: str
    scope: str
    imap_server: str
    imap_port: int
    smtp_server: str
    smtp_port: int
    extra_auth_params: dict[str, str]  # 拼进授权 URL 的额外参数


PROVIDERS: dict[str, OAuthProvider] = {
    # Gmail：IMAP/SMTP XOAUTH2 只认 https://mail.google.com/ 这一个 scope，
    # access_type=offline 保证返回 refresh_token（教程 §2 坑点 4）
    "gmail": OAuthProvider(
        key="gmail", name="Gmail", domains=("gmail.com", "googlemail.com"),
        auth_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",
        scope="https://mail.google.com/",
        imap_server="imap.gmail.com", imap_port=993,
        smtp_server="smtp.gmail.com", smtp_port=465,
        extra_auth_params={"access_type": "offline", "prompt": "consent"},
    ),
    # Outlook：scope 必须是 outlook.office.com 资源（graph 资源换的 token 鉴权失败），
    # offline_access 拿 refresh_token；个人账号 SMTP 走 smtp-mail.outlook.com:587 STARTTLS
    "outlook": OAuthProvider(
        key="outlook", name="Outlook", domains=("outlook.com", "hotmail.com", "live.com", "msn.com"),
        auth_url="https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        token_url="https://login.microsoftonline.com/common/oauth2/v2.0/token",
        scope="offline_access https://outlook.office.com/IMAP.AccessAsUser.All"
              " https://outlook.office.com/SMTP.Send",
        imap_server="outlook.office365.com", imap_port=993,
        smtp_server="smtp-mail.outlook.com", smtp_port=587,
        extra_auth_params={},
    ),
}


def match_provider(email: str) -> OAuthProvider | None:
    """按邮箱域名匹配 OAuth 服务商；未覆盖域名返回 None。"""
    domain = email.rsplit("@", 1)[-1].strip().lower()
    for provider in PROVIDERS.values():
        if domain in provider.domains:
            return provider
    return None


def xoauth2_string(email: str, access_token: str) -> str:
    """SASL XOAUTH2 初始响应串（IMAP/SMTP 共用；注意 \\x01 是二进制字节）。"""
    return f"user={email}\x01auth=Bearer {access_token}\x01\x01"


# ── OAuth 客户端配置（用户在设置页填写）──────────────────────────

def client_key(provider_key: str) -> str:
    return f"oauth_client:{provider_key}"


def get_client(provider_key: str) -> dict | None:
    raw = get_secret(client_key(provider_key))
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    return data if data.get("client_id") else None


def configured(provider_key: str) -> bool:
    return get_client(provider_key) is not None


def save_client(provider_key: str, client_id: str, client_secret: str = "",
                redirect_path: str = "") -> None:
    if not client_id.strip() and not client_secret.strip():
        set_secret(client_key(provider_key), None)  # 双空 = 清除配置
        return
    record = {
        "client_id": client_id.strip(),
        "client_secret": client_secret.strip(),
    }
    path = redirect_path.strip()
    if path and path != CALLBACK_PATH:
        record["redirect_path"] = path  # 默认路径不落盘，保持旧配置结构不变
    set_secret(client_key(provider_key), json.dumps(record))


# ── PKCE 与授权 URL ──────────────────────────────────────────────

def pkce_pair() -> tuple[str, str]:
    """返回 (code_verifier, code_challenge)：RFC 7636 S256，verifier 64 字符。"""
    verifier = base64.urlsafe_b64encode(_secrets.token_bytes(48)).decode().rstrip("=")
    return verifier, challenge_from_verifier(verifier)


def challenge_from_verifier(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def build_auth_url(provider: OAuthProvider, *, client_id: str, redirect_uri: str,
                   state: str, code_challenge: str) -> str:
    params: dict[str, str] = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": provider.scope,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    params.update(provider.extra_auth_params)
    return f"{provider.auth_url}?{urlencode(params)}"


def _token_request(provider: OAuthProvider, data: dict[str, str]) -> dict:
    """POST token 端点；失败按错误码翻译为面向用户的文案。

    代理策略：全局代理地址非空时优先走代理（大陆直连 Gmail 必死）；代理建连
    失败（工具没开/端口填错，典型 10061 拒绝）自动降级**直连**兜底——Outlook
    等直连可达的服务商不受代理配置错误影响，Gmail 则把错误如实报出来。
    显式传 proxy 同时覆盖终端环境变量，行为与「开没开终端代理」解耦。
    """
    proxy = netproxy.httpx_proxy_arg()
    if proxy is not None:
        try:
            return _request_via(provider, data, proxy)
        except OAuthError as exc:
            if not exc.transport:
                raise  # 业务拒绝（secret 错等）：直连也一样被拒，不重试
    return _request_via(provider, data, None)


def _request_via(provider: OAuthProvider, data: dict[str, str], proxy: str | None) -> dict:
    try:
        resp = httpx.post(provider.token_url, data=data,
                          headers={"Content-Type": "application/x-www-form-urlencoded"},
                          timeout=30, proxy=proxy)
    except (httpx.HTTPError, ImportError, OSError) as exc:
        # ImportError：终端设了 SOCKS 代理环境变量但未装 socksio（httpx 构建传输层时抛，
        # 不是 HTTPError 子类——不接住就会以裸 500 冒出来）
        raise OAuthError(f"无法连接 {provider.name} 令牌服务：{exc}", transport=True) from exc
    try:
        payload = resp.json()
    except ValueError as exc:
        raise OAuthError(f"{provider.name} 令牌服务返回异常（HTTP {resp.status_code}）",
                         transport=False) from exc
    if resp.status_code != 200 or "access_token" not in payload:
        raise OAuthError(f"{provider.name} 授权失败：{_translate_token_error(payload)}")
    return payload


def _translate_token_error(payload: dict) -> str:
    """错误码/描述 → 用户可操作的人话（覆盖高频踩坑，未命中回退原文）。"""
    err = payload.get("error", "")
    desc = payload.get("error_description") or ""
    hint = _TOKEN_ERR_HINT.get(err)
    if hint is None and "client_secret" in f"{err} {desc}":
        hint = ("该 OAuth 客户端是 Web 类型，换令牌必须附 client_secret：到 "
                "设置-邮箱账号-OAuth2 点「修改」补填后重新授权；或改用「桌面应用」类型的客户端 ID")
    return hint or desc or err or "未知错误"


def exchange_code(provider: OAuthProvider, *, client_id: str, code: str,
                  code_verifier: str, redirect_uri: str,
                  client_secret: str | None = None) -> dict:
    """授权码换令牌：PKCE 必带 verifier；Web 型客户端需附 client_secret。"""
    data = {
        "client_id": client_id,
        "code": code,
        "code_verifier": code_verifier,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }
    if client_secret:
        data["client_secret"] = client_secret
    return _token_request(provider, data)


def refresh_tokens(provider: OAuthProvider, *, client_id: str, refresh_token: str,
                   client_secret: str | None = None) -> dict:
    data = {
        "client_id": client_id,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }
    if client_secret:
        data["client_secret"] = client_secret
    return _token_request(provider, data)


# ── 令牌存储与刷新 ────────────────────────────────────────────────

def token_key(account_id: int) -> str:
    return f"oauth_token:{account_id}"


def load_token(account_id: int) -> dict | None:
    raw = get_secret(token_key(account_id))
    if not raw:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return None


def has_token(account_id: int) -> bool:
    return has_secret(token_key(account_id))


def delete_token(account_id: int) -> None:
    set_secret(token_key(account_id), None)


def store_tokens(account_id: int, provider_key: str, email: str, tokens: dict) -> None:
    """落库令牌（expires_at 提前 _TOKEN_MARGIN 秒，刷新轮换值覆盖保存）。"""
    expires_in = int(tokens.get("expires_in") or 3600)
    record = {
        "provider": provider_key,
        "email": email,
        "access_token": tokens["access_token"],
        "refresh_token": tokens.get("refresh_token"),
        "expires_at": time.time() + expires_in - _TOKEN_MARGIN,
    }
    set_secret(token_key(account_id), json.dumps(record))


_token_locks: dict[int, threading.Lock] = {}
_token_locks_guard = threading.Lock()


def _account_lock(account_id: int) -> threading.Lock:
    """按账号加锁：同步线程与发信线程同时发现令牌过期时只刷一次。

    微软 v2 端点轮换 refresh_token——并发刷新会让先返回的 refresh_token 失效。
    """
    with _token_locks_guard:
        lock = _token_locks.get(account_id)
        if lock is None:
            lock = _token_locks.setdefault(account_id, threading.Lock())
        return lock


def ensure_access_token(account_id: int) -> str:
    """取有效 access_token：未过期直接用，临期/已过期则刷新并保存。

    令牌缺失或刷新失败（含 refresh_token 失效）抛 OAuthError，调用方翻译为
    「请重新授权」类文案。
    """
    with _account_lock(account_id):
        record = load_token(account_id)
        if not record or not record.get("refresh_token"):
            raise OAuthError("缺少 OAuth 令牌，请重新授权")
        if record.get("access_token") and time.time() < record.get("expires_at", 0):
            return record["access_token"]

        provider = PROVIDERS.get(record.get("provider") or "")
        if provider is None:
            raise OAuthError("OAuth 服务商标识无效，请重新授权")
        client = get_client(provider.key)
        if client is None:
            raise OAuthError(f"{provider.name} 的 OAuth 客户端配置已被移除，请在设置页重新填写")
        try:
            tokens = refresh_tokens(
                provider, client_id=client["client_id"],
                refresh_token=record["refresh_token"],
                client_secret=client.get("client_secret"))
        except OAuthError:
            raise
        store_tokens(account_id, provider.key, record["email"], tokens)
        return tokens["access_token"]


# ── 授权流程状态（进程内；单用户本地应用无需持久化）───────────────

_FLOWS: dict[str, dict] = {}
_FLOW_LOCK = threading.Lock()


def _prune_flows(now: float) -> None:
    expired = [k for k, v in _FLOWS.items() if now - v["created"] > FLOW_TTL]
    for k in expired:
        _FLOWS.pop(k, None)


def create_flow(email: str, provider_key: str, redirect_uri: str) -> tuple[str, dict]:
    """新建授权流程，返回 (state, 流程信息)。state 供回调防伪（RFC 6749 §10.12）。"""
    client = get_client(provider_key)
    assert client  # 调用方（API 层）已预检
    verifier, challenge = pkce_pair()
    state = _secrets.token_urlsafe(24)
    flow = {
        "email": email, "provider": provider_key,
        "code_verifier": verifier, "redirect_uri": redirect_uri,
        "created": time.time(), "status": "pending", "detail": "",
    }
    with _FLOW_LOCK:
        _prune_flows(time.time())
        _FLOWS[state] = flow
    return state, flow


def get_flow(state: str) -> dict | None:
    with _FLOW_LOCK:
        flow = _FLOWS.get(state)
        if flow is None or time.time() - flow["created"] > FLOW_TTL:
            return None
        return flow


def settle_flow(state: str, ok: bool, detail: str) -> None:
    """回调处理完毕：标记结果供前端轮询（verifier 用后即弃，state 保留到过期）。"""
    with _FLOW_LOCK:
        flow = _FLOWS.get(state)
        if flow is not None:
            flow["code_verifier"] = ""
            flow["status"] = "done" if ok else "error"
            flow["detail"] = detail
