"""nmail-cli 主实现：Nmail 对外 API 薄客户端（AGENT_SKILL_PLAN P2，REDESIGN_PLAN §19）。

契约（skills/SKILL.md 与 README 同源）：
- stdout 只输出 JSON envelope：成功 ``{"ok":true,"data":…}``，失败
  ``{"ok":false,"error":{"code","message",…}}``；人话日志一律走 stderr。
- exit code：0 成功 · 1 上游 5xx（可重试×2）· 2 参数不合规（不重试）· 3 认证失效/未启用
  （走 auth login）· 4 连不上（检查 Nmail/隧道，可重试×2）· 6 业务永久拒绝（不重试）·
  7 限流（按 Retry-After 等待）· 8 需两阶段确认（停下等用户许可，不得同轮自确认）。
- 发送类两阶段确认：``drafts send`` 不带 --confirmed 时打印 summary 并 exit 8；
  用户许可后**原参数 + --confirmed** 重放（服务端建草稿→approve 天然两段，CLI 层确认即可）。
- 配置：~/.config/nmail-cli/config.json（0600）；环境变量 NMAIL_BASE_URL/NMAIL_API_KEY 优先。
- 本机（Host 为 127.0.0.1/localhost/::1）auth login 经内部 /api/extkeys 自动配对建 Key
  （与设置页同信任级）；远程必须 --key 粘贴（管理面不出本机）。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import socket
import sys
import time
from pathlib import Path

EXIT_OK = 0
EXIT_UPSTREAM = 1
EXIT_BAD_PARAMS = 2
EXIT_AUTH = 3
EXIT_NETWORK = 4
EXIT_PERMANENT = 6
EXIT_RATE_LIMIT = 7
EXIT_CONFIRM = 8

DEFAULT_BASE_URL = "http://127.0.0.1:8720"
_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}

_CODE_EXIT = {
    "bad_request": EXIT_BAD_PARAMS,
    "invalid_params": EXIT_BAD_PARAMS,
    "invalid_key": EXIT_AUTH,
    "forbidden": EXIT_AUTH,
    "not_found": EXIT_PERMANENT,
    "rate_limited": EXIT_RATE_LIMIT,
    "upstream": EXIT_UPSTREAM,
    "server_error": EXIT_UPSTREAM,
}
_STATUS_EXIT = {401: EXIT_AUTH, 403: EXIT_AUTH, 404: EXIT_PERMANENT, 429: EXIT_RATE_LIMIT}


class CliError(Exception):
    """业务失败：message 照 error.message 原文透出，code/exit_code 决定 agent 下一步。"""

    def __init__(self, message: str, code: str = "server_error",
                 exit_code: int = EXIT_UPSTREAM, extra: dict | None = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.exit_code = exit_code
        self.extra = extra or {}


def _stderr(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


_PENDING_NOTICE: dict = {}  # 更新检查提示（_probe_update_notice 填充，_emit 消费）


def _emit(data) -> None:  # noqa: ANN001 — envelope data 为任意 JSON 值
    envelope: dict = {"ok": True, "data": data}
    if _PENDING_NOTICE:
        envelope["_notice"] = _PENDING_NOTICE  # 更新检查（SKILL.md「更新检查」节消费）
    print(json.dumps(envelope, ensure_ascii=False), flush=True)


def _semver_tuple(v: str) -> tuple[int, ...]:
    parts: list[int] = []
    for seg in v.strip().lstrip("v").split("."):
        digits = ""
        for ch in seg:
            if ch.isdigit():
                digits += ch
            else:
                break
        parts.append(int(digits or 0))
    return tuple(parts[:3]) if parts else (0, 0, 0)


def _probe_update_notice() -> None:
    """B2 版本协商：服务端 /health 带 version，CLI 落后时在输出附 _notice.update。
    尽力而为——任何失败都静默跳过（旧服务端无 version、离线、隧道断均不扰主流程）。"""
    import nmail_cli

    base_url = None
    try:
        base_url = os.environ.get("NMAIL_BASE_URL") or _load_config().get("base_url")
    except Exception:  # noqa: BLE001
        return
    if not base_url:
        return
    try:
        client = Client(str(base_url))
        status, body, _ = client._call("GET", "/api/ext/v1/health", None, None, None, None)
        server = str((body or {}).get("version") or "").strip()
        if status < 400 and server and _semver_tuple(server) > _semver_tuple(nmail_cli.__version__):
            globals()["_PENDING_NOTICE"] = {
                "update": {"cli": nmail_cli.__version__, "server": server,
                           "hint": "CLI 落后于服务端，建议升级后重新安装 skill",
                           "upgrade": "uvx nmail-cli@latest",
                           "skill": "npx skills add nathanpenny520/Nmail -g -y"},
            }
    except Exception:  # noqa: BLE001 — 更新检查失败不影响命令本身
        return


# ── 配置 ────────────────────────────────────────────────────

def _config_path() -> Path:
    return Path(os.environ.get("NMAIL_CLI_CONFIG_DIR")
                or Path.home() / ".config" / "nmail-cli") / "config.json"


def _load_config() -> dict:
    try:
        return json.loads(_config_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_config(base_url: str, key: str) -> Path:
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    path.write_text(json.dumps({"base_url": base_url, "key": key}, ensure_ascii=False),
                    encoding="utf-8")
    path.chmod(0o600)
    return path


def _resolve_base_url(arg_value: str | None) -> str:
    url = arg_value or os.environ.get("NMAIL_BASE_URL") or _load_config().get("base_url")
    if not url:
        raise CliError("尚未配置：先运行 nmail-cli auth login（或设 NMAIL_BASE_URL）",
                       code="invalid_key", exit_code=EXIT_AUTH)
    return url.rstrip("/")


def _resolve_key(arg_value: str | None) -> str:
    key = arg_value or os.environ.get("NMAIL_API_KEY") or _load_config().get("key")
    if not key:
        raise CliError("尚未配置 API Key：先运行 nmail-cli auth login（或设 NMAIL_API_KEY）",
                       code="invalid_key", exit_code=EXIT_AUTH)
    return key


# ── HTTP 客户端 ─────────────────────────────────────────────

DEFAULT_TRANSPORT = None  # 测试注入点：ASGI TestClient 等替代 requests 传输


class Client:
    """envelope 语义的 API 客户端；transport 可注入（测试用 ASGI TestClient）。

    transport(method, path, headers, json_body, files, params) -> (status, body, content)
    body 为解析后的 JSON（非 JSON 响应为 {}），content 为原始字节（附件下载用）。
    """

    def __init__(self, base_url: str, key: str | None = None, transport=None):
        self.base_url = base_url.rstrip("/")
        self.key = key or ""
        self._transport = transport or DEFAULT_TRANSPORT or self._requests_transport

    def _requests_transport(self, method: str, path: str, headers: dict,
                            json_body=None, files=None, params=None) -> tuple[int, dict, bytes]:
        import requests  # 惰性导入：ASGI 传输（测试）不需要；正常安装已随包带上

        try:
            resp = requests.request(method, self.base_url + path, headers=headers,
                                    json=json_body, files=files, params=params, timeout=60)
        except requests.exceptions.RequestException as exc:
            raise CliError(f"连不上 Nmail（{self.base_url}）：{exc.__class__.__name__}——"
                           "检查 Nmail 是否在运行、隧道是否在位",
                           code="network", exit_code=EXIT_NETWORK) from exc
        try:
            body = resp.json()
        except ValueError:
            body = {}
        return resp.status_code, body, resp.content

    def request(self, method: str, path: str, *, json_body=None, files=None,
                params=None, key: str | None = None):
        status, body, _ = self._call(method, path, json_body, files, params, key)
        if status >= 400:
            raise self._error(status, body)
        return body

    def download(self, path: str) -> bytes:
        status, body, content = self._call("GET", path, None, None, None, None)
        if status >= 400:
            raise self._error(status, body)
        return content

    def _call(self, method: str, path: str, json_body, files, params,
              key: str | None) -> tuple[int, dict, bytes]:
        headers = {"X-Api-Key": key if key is not None else self.key}
        return self._transport(method, path, headers, json_body, files, params)

    @staticmethod
    def _error(status: int, body) -> CliError:
        err = body.get("error") if isinstance(body, dict) else None
        if err:
            code = err.get("code") or "server_error"
            exit_code = _CODE_EXIT.get(code) or _STATUS_EXIT.get(status) or EXIT_UPSTREAM
            extra = {k: v for k, v in err.items() if k not in ("code", "message")}
            return CliError(err.get("message") or f"HTTP {status}",
                            code=code, exit_code=exit_code, extra=extra)
        detail = body.get("detail") if isinstance(body, dict) else None
        return CliError(str(detail) or f"HTTP {status}",
                        code="server_error", exit_code=EXIT_UPSTREAM)


def _fail(exc: CliError) -> int:
    payload = {"ok": False, "error": {"code": exc.code, "message": exc.message, **exc.extra}}
    print(json.dumps(payload, ensure_ascii=False), flush=True)
    return exc.exit_code


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        if getattr(args, "command", None) != "auth":
            _probe_update_notice()  # B2：尽力而为，失败静默
        return args.func(args)
    except CliError as exc:
        return _fail(exc)
    except KeyboardInterrupt:
        _stderr("\n已停止")
        return EXIT_OK


# ── auth ────────────────────────────────────────────────────

def _is_local(base_url: str) -> bool:
    m = re.match(r"https?://([^/:?#]+)", base_url)
    return bool(m) and m.group(1).strip("[]").lower() in _LOCAL_HOSTS


def _confirm(prompt: str, assumed_yes: bool) -> bool:
    if assumed_yes:
        return True
    try:
        return input(prompt).strip().lower() in ("", "y", "yes")
    except EOFError:
        return False


def cmd_auth_login(args) -> int:
    base_url = (args.base_url or DEFAULT_BASE_URL).rstrip("/")
    client = Client(base_url)
    client.request("GET", "/api/ext/v1/health")  # 连通性自测（失败→network exit 4）
    if args.key:
        key = args.key
        _stderr(f"已配置 Key（{base_url}）")
    elif _is_local(base_url):
        name = f"cli-{socket.gethostname()}"
        key = client.request("POST", "/api/extkeys", json_body={
            "name": name, "scopes": [s.strip() for s in args.scopes.split(",") if s.strip()],
        })["key"]["key"]
        _stderr(f"已在本机 Nmail 创建密钥「{name}」（scopes={args.scopes}）")
        try:
            client.request("GET", "/api/ext/v1/accounts", key=key)
        except CliError as exc:
            if exc.code == "forbidden" and "未启用" in exc.message:
                if _confirm("对外 API 未启用，现在打开？（Y/n）", args.yes):
                    client.request("POST", "/api/extkeys/enabled", json_body={"enabled": True})
                    _stderr("已启用对外 API")
            else:
                raise
    else:
        key = input(f"远程模式（{base_url}）：请在 Nmail 设置-API 复制密钥后粘贴: ").strip()
        if not key:
            raise CliError("未输入 Key", code="invalid_key", exit_code=EXIT_AUTH)
    save_config(base_url, key)
    _stderr(f"配置已保存：{_config_path()}")
    _emit({"base_url": base_url, "key": key})  # 所见即所存（本机终端）
    return EXIT_OK


def cmd_auth_status(_args) -> int:
    cfg = _load_config()
    if not cfg.get("base_url") or not cfg.get("key"):
        _emit({"logged_in": False})
        return EXIT_OK
    client = Client(cfg["base_url"], cfg["key"])
    try:
        accounts = client.request("GET", "/api/ext/v1/accounts")
        _emit({"logged_in": True, "base_url": cfg["base_url"], "accounts": accounts["accounts"]})
    except CliError as exc:
        _emit({"logged_in": True, "base_url": cfg["base_url"],
               "reachable": False, "error": {"code": exc.code, "message": exc.message}})
    return EXIT_OK


def cmd_auth_logout(_args) -> int:
    path = _config_path()
    removed = path.exists()
    if removed:
        path.unlink()
    _emit({"cleared": removed})
    return EXIT_OK


def cmd_plus_me(_args) -> int:
    client = _client()
    _emit(client.request("GET", "/api/ext/v1/accounts"))
    return EXIT_OK


def _client(args=None) -> Client:
    base_url = _resolve_base_url(getattr(args, "base_url", None))
    key = _resolve_key(getattr(args, "api_key", None))
    return Client(base_url, key)


# ── emails ──────────────────────────────────────────────────

def _email_list_params(args) -> dict:
    params: dict = {"limit": args.limit, "offset": args.offset}
    if args.account_id is not None:
        params["account_id"] = args.account_id
    if args.folder:
        params["folder"] = args.folder
    if getattr(args, "q", None):
        params["q"] = args.q
    if args.is_read is not None:
        params["is_read"] = "true" if args.is_read else "false"
    if args.starred is not None:
        params["starred"] = "true" if args.starred else "false"
    if args.category:
        params["category"] = args.category
    if args.sender:
        params["sender"] = args.sender
    if args.recipient:
        params["recipient"] = args.recipient
    if args.after:
        params["after"] = args.after
    if args.before:
        params["before"] = args.before
    if args.has_attachments is not None:
        params["has_attachments"] = "true" if args.has_attachments else "false"
    return params


def cmd_emails_list(args) -> int:
    client = _client(args)
    _emit(client.request("GET", "/api/ext/v1/emails", params=_email_list_params(args)))
    return EXIT_OK


def cmd_emails_search(args) -> int:
    args.q = args.query
    return cmd_emails_list(args)


def cmd_emails_read(args) -> int:
    client = _client(args)
    detail = client.request("GET", f"/api/ext/v1/emails/{args.email_id}")
    if args.save_attachments:
        out_dir = Path(args.save_attachments)
        out_dir.mkdir(parents=True, exist_ok=True)
        saved = []
        for att in detail.get("attachments", []):
            content = client.download(
                f"/api/ext/v1/emails/{args.email_id}/attachments/{att['id']}")
            target = out_dir / Path(att["filename"] or f"attachment-{att['id']}").name
            n = 1
            while target.exists():
                target = out_dir / f"{target.stem}-{n}{target.suffix}"
                n += 1
            target.write_bytes(content)
            saved.append(str(target))
        detail = dict(detail, saved_to=saved)
        _stderr(f"已保存 {len(saved)} 个附件到 {out_dir}")
    _emit(detail)
    return EXIT_OK


def cmd_emails_action(args) -> int:
    client = _client(args)
    ids = [int(x) for x in args.ids.split(",") if x.strip()]
    body = client.request("POST", "/api/ext/v1/emails/actions", json_body={
        "ids": ids, "action": args.action,
        **({"folder": args.folder} if args.folder else {}),
    })
    # 服务器移动类异步：轮询 job 至终态（≤60s），agent 拿到的是确定结果
    if body.get("job_id"):
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            job = client.request("GET", f"/api/ext/v1/jobs/{body['job_id']}")
            if job.get("status") in ("done", "failed"):
                body = dict(body, job=job)
                break
            time.sleep(1)
        else:
            body = dict(body, job={"status": "timeout", "job_id": body["job_id"]})
            _stderr("任务仍在后台进行（60s 未到终态），可稍后 jobs get 查询")
    _emit(body)
    return EXIT_OK


def cmd_jobs_get(args) -> int:
    client = _client(args)
    _emit(client.request("GET", f"/api/ext/v1/jobs/{args.job_id}"))
    return EXIT_OK


# ── drafts ──────────────────────────────────────────────────

def _body_kwargs(args) -> dict:
    """--body / --body-file + --body-format → 服务端三选一字段。"""
    if args.body and args.body_file:
        raise CliError("--body 与 --body-file 只能二选一", code="bad_request",
                       exit_code=EXIT_BAD_PARAMS)
    field = {"md": "body_md", "html": "body_html", "text": "body_text"}[args.body_format]
    text = args.body
    if args.body_file:
        text = Path(args.body_file).read_text(encoding="utf-8")
    return {field: text or ""}


def _upload_attachments(client: Client, draft_id: int, paths: list[str]) -> None:
    files = [("files", (Path(p).name, Path(p).read_bytes(), "application/octet-stream"))
             for p in paths]
    client.request("POST", f"/api/ext/v1/drafts/{draft_id}/attachments", files=files)


def _refresh_draft(client: Client, draft_id: int) -> dict:
    return client.request("GET", f"/api/ext/v1/drafts/{draft_id}")["draft"]


def cmd_drafts_create(args) -> int:
    client = _client(args)
    payload = {"account_id": args.account_id, "to": args.to or "", "cc": args.cc or "",
               "bcc": args.bcc or "", "subject": args.subject or "", **_body_kwargs(args)}
    draft = client.request("POST", "/api/ext/v1/drafts", json_body=payload)["draft"]
    if args.attachment:
        _upload_attachments(client, draft["id"], args.attachment)
        draft = _refresh_draft(client, draft["id"])
    _emit(draft)
    return EXIT_OK


def cmd_drafts_reply(args) -> int:
    client = _client(args)
    payload = {"email_id": args.email_id, "reply_all": args.reply_all,
               "cc": args.cc or "", "bcc": args.bcc or "", **_body_kwargs(args)}
    draft = client.request("POST", "/api/ext/v1/drafts/reply", json_body=payload)["draft"]
    if args.attachment:
        _upload_attachments(client, draft["id"], args.attachment)
        draft = _refresh_draft(client, draft["id"])
    _emit(draft)
    return EXIT_OK


def cmd_drafts_forward(args) -> int:
    client = _client(args)
    payload = {"email_id": args.email_id, "to": args.to or "",
               "include_attachments": args.include_attachments,
               "cc": args.cc or "", "bcc": args.bcc or "", **_body_kwargs(args)}
    draft = client.request("POST", "/api/ext/v1/drafts/forward", json_body=payload)["draft"]
    if args.attachment:
        _upload_attachments(client, draft["id"], args.attachment)
        draft = _refresh_draft(client, draft["id"])
    _emit(draft)
    return EXIT_OK


def _strip_tags(html_text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html_text or "")).strip()


def cmd_drafts_send(args) -> int:
    client = _client(args)
    if not args.confirmed:
        # 阶段一：拉草稿打摘要 → exit 8，agent 必须停下等用户许可
        draft = _refresh_draft(client, args.draft_id)
        preview = _strip_tags(draft.get("body_html") or "")
        raise CliError("需要两阶段确认：把 summary 展示给用户并取得明确许可，"
                       "然后原参数加 --confirmed 重放；不得在同一轮自行确认。",
                       code="confirmation_required", exit_code=EXIT_CONFIRM,
                       extra={"summary": {
                           "draft_id": draft["id"], "to": draft.get("to_addrs", ""),
                           "cc": draft.get("cc_addrs", ""), "bcc": draft.get("bcc_addrs", ""),
                           "subject": draft.get("subject", ""),
                           "body_preview": preview[:200],
                           "attachments": [a["filename"] for a in draft.get("attachments", [])],
                       }})
    client.request("POST", f"/api/ext/v1/drafts/{args.draft_id}/approve")
    _emit({"sent": True, "draft_id": args.draft_id})
    return EXIT_OK


def cmd_drafts_delete(args) -> int:
    """删除草稿（服务端仅放行 editing/discarded；在途审批草稿先 discard）。"""
    client = _client(args)
    _emit(client.request("DELETE", f"/api/ext/v1/drafts/{args.draft_id}"))
    return EXIT_OK


# ── 其他 ────────────────────────────────────────────────────

def cmd_contacts_search(args) -> int:
    client = _client(args)
    _emit(client.request("GET", "/api/ext/v1/contacts",
                         params={"q": args.query or "", "limit": args.limit}))
    return EXIT_OK


def cmd_folders_list(args) -> int:
    client = _client(args)
    data = client.request("GET", "/api/ext/v1/folders",
                          params={"account_id": args.account_id})
    _emit(data)
    return EXIT_OK


def cmd_folders_sync(args) -> int:
    """按需同步指定文件夹（wait 模式：完成才返回，之后该文件夹立即可读）。"""
    client = _client(args)
    _stderr(f"同步文件夹 {args.folder}（account {args.account_id}）…")
    _emit(client.request("POST", "/api/ext/v1/folders/sync", params={
        "account_id": args.account_id, "name": args.folder, "wait": "true"}))
    return EXIT_OK


def _agent_collect(out: dict) -> dict:
    """非流式 agent 响应 → 紧凑 envelope：回答 + 待审批 + 暂停态（供 SKILL.md 决策）。"""
    events = out.get("events") or []
    paused = None
    for ev in reversed(events):
        if ev.get("type") == "paused" and ev.get("reason") != "approval":
            paused = {"reason": ev.get("reason"), "run_id": ev.get("run_id")}
            break
    return {"answer": out.get("answer") or "",
            "approvals": out.get("approvals") or [],
            "paused": paused}


def cmd_agent_ask(args) -> int:
    client = _client(args)
    payload = {"question": args.question, "mode": args.mode,
               "account_ids": args.account_id or []}
    if args.session_id is not None:
        payload["session_id"] = args.session_id
    out = _agent_collect(client.request("POST", "/api/ext/v1/agent/chat", json_body=payload))
    _emit(out)
    return EXIT_OK


def cmd_agent_decide(args) -> int:
    if args.approve == args.reject:
        raise CliError("--approve 与 --reject 必须二选一",
                       code="invalid_params", exit_code=EXIT_BAD_PARAMS)
    client = _client(args)
    decision = "approve" if args.approve else "reject"
    out = client.request("POST", f"/api/ext/v1/agent/actions/{args.action_id}/decide",
                         json_body={"decision": decision})
    _emit(out)
    return EXIT_OK


def cmd_agent_resume(args) -> int:
    client = _client(args)
    payload: dict = {"run_id": args.run_id}
    if args.answer:
        payload["answer"] = args.answer
    out = _agent_collect(client.request("POST", "/api/ext/v1/agent/resume", json_body=payload))
    _emit(out)
    return EXIT_OK


def cmd_digest(args) -> int:
    client = _client(args)
    _emit(client.request("GET", "/api/ext/v1/digest"))
    return EXIT_OK


def cmd_watch(args) -> int:
    client = _client(args)
    if args.timeout is not None and args.timeout <= 0:
        raise CliError("--timeout 必须为正数（秒）", code="bad_request",
                       exit_code=EXIT_BAD_PARAMS)
    if args.max_emails is not None and args.max_emails <= 0:
        raise CliError("--max-emails 必须为正整数", code="bad_request",
                       exit_code=EXIT_BAD_PARAMS)
    params: dict = {"limit": 200}
    if args.account_id is not None:
        params["account_id"] = args.account_id
    if args.since_id is None:
        latest = client.request("GET", "/api/ext/v1/emails/recent", params={"limit": 1})
        params["since_id"] = latest["latest_id"]  # 基线：不回放历史
    else:
        params["since_id"] = args.since_id
    stop_hint = "Ctrl-C 停止" if args.timeout is None and args.max_emails is None else "到条件自动停止"
    _stderr(f"watching（base={params['since_id']}，{stop_hint}）…")
    deadline = (time.monotonic() + args.timeout) if args.timeout is not None else None
    received = 0
    while True:
        body = client.request("GET", "/api/ext/v1/emails/recent", params=params)
        for item in body["items"]:
            _emit(item)
            received += 1
        params["since_id"] = body["latest_id"]
        if args.max_emails is not None and received >= args.max_emails:
            _stderr(f"已收到 {received} 封（--max-emails={args.max_emails}），停止监听")
            return EXIT_OK
        if deadline is not None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                _stderr(f"--timeout={args.timeout}s 到，停止监听")
                return EXIT_OK
            time.sleep(min(args.interval, remaining))
        else:
            time.sleep(args.interval)


# ── 参数表 ──────────────────────────────────────────────────

def str2bool(v: str) -> bool:
    if v.lower() in ("true", "1", "yes", "y"):
        return True
    if v.lower() in ("false", "0", "no", "n"):
        return False
    raise argparse.ArgumentTypeError(f"需为 true/false：{v}")


def _add_auth_base(p: argparse.ArgumentParser) -> None:
    p.add_argument("--base-url", help=f"Nmail 地址（默认 {DEFAULT_BASE_URL}；env NMAIL_BASE_URL）")
    p.add_argument("--api-key", help="直接指定 Key（env NMAIL_API_KEY）")


def _add_email_filters(p: argparse.ArgumentParser) -> None:
    p.add_argument("--account-id", type=int)
    p.add_argument("--folder")
    p.add_argument("--is-read", type=str2bool, default=None, metavar="true|false")
    p.add_argument("--starred", type=str2bool, default=None, metavar="true|false")
    p.add_argument("--category")
    p.add_argument("--from", dest="sender", help="发件人过滤（地址或姓名包含匹配）")
    p.add_argument("--to", dest="recipient", help="收件人过滤（包含匹配）")
    p.add_argument("--after", help="起始日期 YYYY-MM-DD（含当天）")
    p.add_argument("--before", help="截止日期 YYYY-MM-DD（含当天）")
    p.add_argument("--has-attachments", type=str2bool, default=None, metavar="true|false")
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--offset", type=int, default=0)


def _add_body(p: argparse.ArgumentParser) -> None:
    p.add_argument("--body", help="正文（与 --body-file 二选一）")
    p.add_argument("--body-file", help="正文文件路径（免 shell 转义，推荐）")
    p.add_argument("--body-format", choices=["md", "html", "text"], default="md",
                   help="--body/--body-file 的格式（默认 md）")
    p.add_argument("--attachment", action="append", metavar="PATH", help="附件路径（可重复）")


def build_parser() -> argparse.ArgumentParser:
    import nmail_cli

    parser = argparse.ArgumentParser(
        prog="nmail-cli",
        description="Nmail 对外 API 客户端（agent/skill 友好：JSON envelope + exit code）")
    parser.add_argument("--version", action="version", version=f"nmail-cli {nmail_cli.__version__}")

    sub = parser.add_subparsers(dest="command")

    auth = sub.add_parser("auth", help="配对/状态/登出")
    auth_sub = auth.add_subparsers(dest="auth_command", required=True)
    login = auth_sub.add_parser("login", help="本机自动配对建 Key；远程 --base-url + --key 粘贴")
    login.add_argument("--base-url", default=None)
    login.add_argument("--key", default=None, help="远程模式粘贴的 API Key")
    login.add_argument("--scopes", default="read", help="本机配对的 scope，逗号分隔（默认 read）")
    login.add_argument("--yes", action="store_true", help="对外 API 未启用时直接打开（免确认）")
    login.set_defaults(func=cmd_auth_login)
    status = auth_sub.add_parser("status", help="查看配置与账号可达性")
    status.set_defaults(func=cmd_auth_status)
    out = auth_sub.add_parser("logout", help="清除本机保存的配置")
    out.set_defaults(func=cmd_auth_logout)

    me = sub.add_parser("+me", help="当前账号列表与健康")
    _add_auth_base(me)
    me.set_defaults(func=cmd_plus_me)

    emails = sub.add_parser("emails", help="邮件列表/搜索/读取/动作")
    emails_sub = emails.add_subparsers(dest="emails_command", required=True)
    lst = emails_sub.add_parser("list", help="列表/过滤")
    _add_email_filters(lst)
    _add_auth_base(lst)
    lst.set_defaults(func=cmd_emails_list)
    sch = emails_sub.add_parser("search", help="关键词搜索（其余过滤同 list）")
    sch.add_argument("query", help="关键词（≥3 字走全文检索）")
    _add_email_filters(sch)
    _add_auth_base(sch)
    sch.set_defaults(func=cmd_emails_search)
    read = emails_sub.add_parser("read", help="读取邮件详情")
    read.add_argument("email_id", type=int)
    read.add_argument("--save-attachments", metavar="DIR", help="保存附件到目录（相对路径）")
    _add_auth_base(read)
    read.set_defaults(func=cmd_emails_read)
    act = emails_sub.add_parser("action", help="批量动作（移动类自动轮询到终态）")
    act.add_argument("--ids", required=True, help="逗号分隔邮件 id")
    act.add_argument("--action", required=True,
                     choices=["read", "unread", "star", "unstar", "archive", "unarchive",
                              "trash", "move"])
    act.add_argument("--folder", help="action=move 的目标文件夹")
    _add_auth_base(act)
    act.set_defaults(func=cmd_emails_action)

    drafts = sub.add_parser("drafts", help="草稿创建/回复/转发/发送")
    drafts_sub = drafts.add_subparsers(dest="drafts_command", required=True)
    create = drafts_sub.add_parser("create", help="新建草稿")
    create.add_argument("--account-id", type=int, required=True)
    create.add_argument("--to")
    create.add_argument("--cc")
    create.add_argument("--bcc")
    create.add_argument("--subject")
    _add_body(create)
    _add_auth_base(create)
    create.set_defaults(func=cmd_drafts_create)
    reply = drafts_sub.add_parser("reply", help="回复：自动 Re: 主题/收件人/引用块")
    reply.add_argument("--email-id", type=int, required=True)
    reply.add_argument("--reply-all", action="store_true", help="原收件人并入 cc")
    reply.add_argument("--cc")
    reply.add_argument("--bcc")
    _add_body(reply)
    _add_auth_base(reply)
    reply.set_defaults(func=cmd_drafts_reply)
    fwd = drafts_sub.add_parser("forward", help="转发：自动 Fwd: 主题/引用块")
    fwd.add_argument("--email-id", type=int, required=True)
    fwd.add_argument("--to", required=True, help="转发收件人（逗号分隔）")
    fwd.add_argument("--include-attachments", action="store_true", help="复制原邮件附件")
    fwd.add_argument("--cc")
    fwd.add_argument("--bcc")
    _add_body(fwd)
    _add_auth_base(fwd)
    fwd.set_defaults(func=cmd_drafts_forward)
    send = drafts_sub.add_parser("send", help="发送草稿（两阶段：先不带 --confirmed 拿摘要）")
    send.add_argument("draft_id", type=int)
    send.add_argument("--confirmed", action="store_true",
                      help="第二阶段：用户明确许可后才传（不得同轮自确认）")
    _add_auth_base(send)
    send.set_defaults(func=cmd_drafts_send)
    ddel = drafts_sub.add_parser("delete", help="删除草稿（仅新建/已丢弃状态；在途审批草稿先 discard）")
    ddel.add_argument("draft_id", type=int)
    _add_auth_base(ddel)
    ddel.set_defaults(func=cmd_drafts_delete)

    contacts = sub.add_parser("contacts", help="通讯录")
    contacts_sub = contacts.add_subparsers(dest="contacts_command", required=True)
    cs = contacts_sub.add_parser("search", help="搜索联系人")
    cs.add_argument("query", nargs="?", default="")
    cs.add_argument("--limit", type=int, default=50)
    _add_auth_base(cs)
    cs.set_defaults(func=cmd_contacts_search)

    dig = sub.add_parser("digest", help="最新每日摘要")
    _add_auth_base(dig)
    dig.set_defaults(func=cmd_digest)

    folders = sub.add_parser("folders", help="账号文件夹列表")
    folders_sub = folders.add_subparsers(dest="folders_command", required=True)
    fl = folders_sub.add_parser("list", help="列出账号的文件夹（move/--folder 过滤的目标名从此查）")
    fl.add_argument("--account-id", type=int, required=True, help="账号 id（+me 查看）")
    _add_auth_base(fl)
    fl.set_defaults(func=cmd_folders_list)
    fs = folders_sub.add_parser("sync", help="按需同步指定文件夹（归档/移动后兜底；完成才返回）")
    fs.add_argument("--account-id", type=int, required=True, help="账号 id（+me 查看）")
    fs.add_argument("--folder", required=True, help="文件夹名（folders list 里查）")
    _add_auth_base(fs)
    fs.set_defaults(func=cmd_folders_sync)

    agent_ = sub.add_parser("agent", help="内置总管家（scope=agent；AI 需已在 Nmail 配置）")
    agent_sub = agent_.add_subparsers(dest="agent_command", required=True)
    ask = agent_sub.add_parser("ask", help="委托总管家处理一件事（写动作会返回待审批清单）")
    ask.add_argument("question", help="要交办的事（自然语言）")
    ask.add_argument("--mode", choices=["approval", "auto"], default="approval",
                     help="approval=写动作逐条待审批（默认），auto=安全约束内直执行")
    ask.add_argument("--account-id", type=int, action="append",
                     help="限定账号 id（可重复；缺省=全部账号）")
    ask.add_argument("--session-id", type=int, help="延续既有会话（多轮交办）")
    _add_auth_base(ask)
    ask.set_defaults(func=cmd_agent_ask)
    dec = agent_sub.add_parser("decide", help="批准/拒绝总管家的待审批动作")
    dec.add_argument("action_id", type=int)
    dec.add_argument("--approve", action="store_true", help="批准执行")
    dec.add_argument("--reject", action="store_true", help="拒绝（总管家会改道）")
    _add_auth_base(dec)
    dec.set_defaults(func=cmd_agent_decide)
    res = agent_sub.add_parser("resume", help="续跑运行（审批决定后/触顶暂停后/澄清回答后）")
    res.add_argument("run_id", type=int)
    res.add_argument("--answer", help="ask_user 澄清问题的回答（waiting_input 时必传）")
    _add_auth_base(res)
    res.set_defaults(func=cmd_agent_resume)

    wat = sub.add_parser("watch", help="新邮件流（NDJSON 每行一封；agent 调用建议带 --timeout）")
    wat.add_argument("--since-id", type=int, default=None,
                     help="起始游标（默认当前最新，不回放历史）")
    wat.add_argument("--account-id", type=int)
    wat.add_argument("--interval", type=float, default=10.0, help="轮询秒数（默认 10）")
    wat.add_argument("--timeout", type=float, default=None,
                     help="最长监听秒数，到点自动退出（缺省一直监听直到 Ctrl-C）")
    wat.add_argument("--max-emails", type=int, default=None,
                     help="收到 N 封后自动退出（缺省不限）")
    _add_auth_base(wat)
    wat.set_defaults(func=cmd_watch)

    jobs = sub.add_parser("jobs", help="后台任务进度")
    jobs_sub = jobs.add_subparsers(dest="jobs_command", required=True)
    jg = jobs_sub.add_parser("get", help="查询单个任务")
    jg.add_argument("job_id", type=int)
    _add_auth_base(jg)
    jg.set_defaults(func=cmd_jobs_get)

    return parser
