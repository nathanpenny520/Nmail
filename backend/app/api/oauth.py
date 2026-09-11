"""Gmail / Outlook OAuth2 端点：客户端配置、发起授权、回环回调、流程轮询。

流程：前端 POST /api/oauth/authorize（邮箱+服务商）→ 返回 auth_url → 新窗口
打开；用户在 Google/微软完成登录授权后，浏览器重定向到 GET /oauth/callback
→ 后端用 PKCE code_verifier 换令牌 → 建/更新账号、存令牌、触发首同步 →
返回自关闭 HTML 页；前端轮询 GET /api/oauth/flow/{state} 拿结果刷新列表。

client_id 由用户自建 OAuth 客户端后填入设置页（教程：docs/
自建邮箱客户端 Gmail+Outlook OAuth2 完整教程.md）。回调地址 =
http://localhost:{端口}/oauth/callback——端口随进程监听端口动态生成
（run.py 端口被占时会顺延），桌面型 OAuth 客户端对 localhost 回环不校验端口。
"""
from __future__ import annotations

import html
import re

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from app.api.accounts import COLOR_PALETTE
from app.core import oauth, sync as sync_engine
from app.db.database import get_conn

router = APIRouter(prefix="/api/oauth", tags=["oauth"])
callback_router = APIRouter(tags=["oauth"])

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _redirect_uri(request: Request) -> str:
    server = request.scope.get("server")
    port = server[1] if server else 8720
    return f"http://localhost:{port}{oauth.CALLBACK_PATH}"


@router.get("/status")
def oauth_status(request: Request) -> dict:
    """各服务商配置状态 + 应登记的回调地址（设置页展示与复制）。"""
    providers = []
    for provider in oauth.PROVIDERS.values():
        client = oauth.get_client(provider.key)
        client_id = client["client_id"] if client else ""
        masked = ""
        if client_id:
            masked = (f"{client_id[:6]}…{client_id[-8:]}"
                      if len(client_id) > 18 else client_id)
        providers.append({
            "key": provider.key,
            "name": provider.name,
            "configured": client is not None,
            "client_id_masked": masked,
            "domains": list(provider.domains),
            "imap_server": provider.imap_server,
            "smtp_server": provider.smtp_server,
        })
    return {"redirect_uri": _redirect_uri(request), "providers": providers}


class OauthConfigIn(BaseModel):
    provider: str
    client_id: str = ""
    client_secret: str = ""


@router.put("/config")
def save_oauth_config(payload: OauthConfigIn) -> dict:
    """保存/清除 OAuth 客户端配置（client_id 必填；双空 = 清除）。"""
    if payload.provider not in oauth.PROVIDERS:
        raise HTTPException(400, "未知的服务商")
    if payload.client_id.strip() and payload.client_id.strip() == payload.client_secret.strip():
        raise HTTPException(400, "client_secret 不能与 client_id 相同")
    oauth.save_client(payload.provider, payload.client_id, payload.client_secret)
    return {"ok": True, "configured": oauth.configured(payload.provider)}


class OauthAuthorizeIn(BaseModel):
    email: str
    provider: str


@router.post("/authorize")
def start_authorization(payload: OauthAuthorizeIn, request: Request) -> dict:
    """发起授权：返回浏览器要打开的授权 URL；账号的建/改在回调完成后发生。"""
    email = payload.email.strip().lower()
    if not EMAIL_RE.match(email):
        raise HTTPException(400, "邮箱地址格式不正确")
    if payload.provider not in oauth.PROVIDERS:
        raise HTTPException(400, "未知的服务商")
    provider = oauth.PROVIDERS[payload.provider]
    if not match_email_provider(email, provider):
        raise HTTPException(400, f"邮箱域名不在 {provider.name} 的支持范围内")
    client = oauth.get_client(payload.provider)
    if client is None:
        raise HTTPException(400, f"尚未配置 {provider.name} 的 OAuth 客户端，"
                                 "请先到 设置-邮箱账号-OAuth2 登录 填写 client_id")
    redirect_uri = _redirect_uri(request)
    state, flow = oauth.create_flow(email, payload.provider, redirect_uri)
    auth_url = oauth.build_auth_url(
        provider, client_id=client["client_id"], redirect_uri=redirect_uri,
        state=state, code_challenge=oauth.challenge_from_verifier(flow["code_verifier"]))
    return {"auth_url": auth_url, "state": state}


def match_email_provider(email: str, provider: oauth.OAuthProvider) -> bool:
    domain = email.rsplit("@", 1)[-1].strip().lower()
    return domain in provider.domains


@router.get("/flow/{state}")
def flow_status(state: str) -> dict:
    """前端轮询授权结果：pending | done | error。未知/过期 state 返回 404。"""
    flow = oauth.get_flow(state)
    if flow is None:
        raise HTTPException(404, "授权流程不存在或已过期")
    return {"status": flow["status"], "detail": flow["detail"], "email": flow["email"]}


# ── 回环回调（非 /api 前缀，浏览器直接导航）──────────────────────

@callback_router.get(oauth.CALLBACK_PATH)
def oauth_callback(code: str = "", state: str = "", error: str = "") -> HTMLResponse:
    flow = oauth.get_flow(state)
    if flow is None:
        return _page("授权回调无效", "授权状态不存在或已过期，请回到 Nmail 重新发起授权。", ok=False)
    if error:
        detail = {"access_denied": "你在授权页面取消了授权"}.get(error, f"服务商返回错误：{error}")
        oauth.settle_flow(state, False, detail)
        return _page("授权未完成", detail, ok=False)

    provider = oauth.PROVIDERS[flow["provider"]]
    client = oauth.get_client(flow["provider"]) or {}
    try:
        tokens = oauth.exchange_code(
            provider, client_id=client.get("client_id", ""), code=code,
            code_verifier=flow["code_verifier"], redirect_uri=flow["redirect_uri"],
            client_secret=client.get("client_secret") or None)
        account_id = _upsert_oauth_account(flow["email"], provider)
        oauth.store_tokens(account_id, provider.key, flow["email"], tokens)
    except oauth.OAuthError as exc:
        oauth.settle_flow(state, False, exc.message)
        return _page("授权失败", exc.message, ok=False)

    account = get_conn().execute(
        "SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
    sync_engine.start_sync({"id": account_id, **{k: account[k] for k in
                                                  ("email", "imap_server", "imap_port")}})
    oauth.settle_flow(state, True, f"{flow['email']} 已接入 Nmail")
    return _page("授权成功", f"{flow['email']} 已接入 Nmail，正在后台同步邮件，本页可关闭。",
                 ok=True)


def _upsert_oauth_account(email: str, provider: oauth.OAuthProvider) -> int:
    """已存在的同邮箱账号转为 OAuth 认证并按服务商覆盖服务器参数；否则新建。"""
    conn = get_conn()
    row = conn.execute("SELECT id FROM accounts WHERE email = ?", (email,)).fetchone()
    if row is not None:
        conn.execute(
            "UPDATE accounts SET auth_type='oauth2', oauth_provider=?, provider_name=?,"
            " imap_server=?, imap_port=?, smtp_server=?, smtp_port=?,"
            " status='never_synced', status_detail=NULL WHERE id=?",
            (provider.key, provider.name, provider.imap_server, provider.imap_port,
             provider.smtp_server, provider.smtp_port, int(row["id"])),
        )
        conn.commit()
        return int(row["id"])
    count = conn.execute("SELECT COUNT(*) AS n FROM accounts").fetchone()["n"]
    color = COLOR_PALETTE[int(count) % len(COLOR_PALETTE)]
    cursor = conn.execute(
        "INSERT INTO accounts (email, provider_name, imap_server, imap_port, smtp_server,"
        " smtp_port, color, status, auth_type, oauth_provider)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, 'never_synced', 'oauth2', ?)",
        (email, provider.name, provider.imap_server, provider.imap_port,
         provider.smtp_server, provider.smtp_port, color, provider.key),
    )
    conn.commit()
    return int(cursor.lastrowid)


def _page(title: str, detail: str, *, ok: bool) -> HTMLResponse:
    """回调结果页：不携带任何令牌内容，成功时提示后自关窗口。"""
    color = "#10b981" if ok else "#ef4444"
    return HTMLResponse(
        f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>{html.escape(title)} · Nmail</title>
<style>
body{{font-family:system-ui,-apple-system,'Segoe UI',sans-serif;margin:0;min-height:100vh;
display:flex;align-items:center;justify-content:center;background:#f9fafb}}
.card{{background:#fff;border-radius:16px;box-shadow:0 10px 30px rgba(0,0,0,.08);
padding:36px 44px;max-width:420px;text-align:center}}
h1{{font-size:18px;color:{color};margin:0 0 12px}}
p{{color:#4b5563;font-size:14px;line-height:1.7;margin:0;word-break:break-all}}
</style></head><body><div class="card"><h1>{html.escape(title)}</h1>
<p>{html.escape(detail)}</p></div>
<script>if (window.opener) setTimeout(() => window.close(), 2000)</script>
</body></html>""")
