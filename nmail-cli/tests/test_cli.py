"""nmail-cli 契约测试：envelope/exit code、两阶段确认、配置、命令链路。

Client 以 ASGI TestClient 为传输（DEFAULT_TRANSPORT 注入），全链路打到真实
FastAPI app（与 backend/tests 同一夹具口径）；不发真实邮件——send --confirmed
路径以无 SMTP 凭据的上游失败（exit 1）验证到达 outbox。
"""
from __future__ import annotations

import json
import uuid

import pytest
from fastapi.testclient import TestClient

from app.db import database
from app.main import app

from nmail_cli import cli
from nmail_cli.cli import (
    EXIT_AUTH,
    EXIT_BAD_PARAMS,
    EXIT_CONFIRM,
    EXIT_OK,
    EXIT_PERMANENT,
    EXIT_UPSTREAM,
    Client,
    CliError,
    _config_path,
    _load_config,
    main,
    save_config,
)

client = TestClient(app, base_url="http://127.0.0.1")
database.run_migrations()  # TestClient 不触发 lifespan，迁移在此显式补跑


@pytest.fixture(autouse=True)
def _asgi_transport(monkeypatch, tmp_path):
    """全部命令走 ASGI 传输；配置目录指向临时目录。"""
    def transport(method, path, headers, json_body=None, files=None, params=None):
        r = client.request(method, path, headers=headers, json=json_body,
                           files=files, params=params)
        try:
            body = r.json()
        except ValueError:
            body = {}
        return r.status_code, body, r.content

    monkeypatch.setattr(cli, "DEFAULT_TRANSPORT", transport)
    monkeypatch.setenv("NMAIL_CLI_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.delenv("NMAIL_BASE_URL", raising=False)
    monkeypatch.delenv("NMAIL_API_KEY", raising=False)
    yield


def _out_lines(capsys) -> list:
    return [json.loads(line) for line in capsys.readouterr().out.strip().splitlines()]


def _make_key(scopes: list[str]) -> str:
    resp = client.post("/api/extkeys", json={"name": "cli-test", "scopes": scopes})
    assert resp.status_code == 200
    return resp.json()["key"]["key"]


def _seed_account() -> int:
    conn = database.get_conn()
    cur = conn.execute(
        "INSERT INTO accounts (email, imap_server, imap_port) VALUES (?, 'imap.test', 993)",
        (f"c{uuid.uuid4().hex[:8]}@example.com",),
    )
    conn.commit()
    return int(cur.lastrowid)


def _seed_email(account_id: int, uid: int, subject: str, **extra) -> int:
    conn = database.get_conn()
    cols = {"account_id": account_id, "folder": "INBOX", "uid": uid, "subject": subject,
            "sender_email": "boss@example.com", "body_text": "原始正文"}
    cols.update(extra)
    cur = conn.execute(
        f"INSERT INTO emails ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
        tuple(cols.values()),
    )
    conn.commit()
    return int(cur.lastrowid)


def _cleanup_drafts(account_id: int) -> None:
    for d in client.get("/api/user-drafts", params={"status": "editing"}).json()["drafts"]:
        if d["account_id"] == account_id:
            client.delete(f"/api/user-drafts/{d['id']}")


# ── 单元：契约映射 ──────────────────────────────────────────

def test_错误映射():
    e = Client._error(401, {"error": {"code": "invalid_key", "message": "x"}})
    assert e.exit_code == EXIT_AUTH
    e = Client._error(404, {"error": {"code": "not_found", "message": "x"}})
    assert e.exit_code == EXIT_PERMANENT
    e = Client._error(502, {"error": {"code": "upstream", "message": "x"}})
    assert e.exit_code == EXIT_UPSTREAM
    e = Client._error(422, {"detail": [{"loc": ["query", "limit"], "msg": "bad"}]})
    assert e.exit_code == EXIT_UPSTREAM  # 非 envelope 的 422 视为服务器侧异常形态
    assert e.exit_code == Client._error(500, {}).exit_code


def test_is_local判定():
    assert cli._is_local("http://127.0.0.1:8720")
    assert cli._is_local("http://localhost:8720")
    assert not cli._is_local("https://nmail.example.com")


def test_配置读写与权限(tmp_path):
    path = save_config("http://127.0.0.1:9999", "nmail_k")
    assert json.loads(path.read_text())["key"] == "nmail_k"
    assert path.stat().st_mode & 0o777 == 0o600
    assert _load_config()["base_url"] == "http://127.0.0.1:9999"


def test_未配置时exit3(capsys):
    assert main(["+me"]) == EXIT_AUTH
    body = _out_lines(capsys)[0]
    assert body["ok"] is False and body["error"]["code"] == "invalid_key"


# ── 集成：真实 app 链路 ─────────────────────────────────────

def test_auth_login本机自动配对(capsys):
    client.post("/api/extkeys/enabled", json={"enabled": True})
    rc = main(["auth", "login", "--base-url", "http://127.0.0.1:8720", "--yes"])
    assert rc == EXIT_OK
    envelope = _out_lines(capsys)[0]
    assert envelope["ok"] is True and envelope["data"]["key"].startswith("nmail_")
    cfg = _load_config()
    assert cfg["base_url"] == "http://127.0.0.1:8720"
    assert cfg["key"] == envelope["data"]["key"]


def test_emails_list过滤与read(capsys):
    client.post("/api/extkeys/enabled", json={"enabled": True})
    save_config("http://127.0.0.1:8720", _make_key(["read"]))
    aid = _seed_account()
    e1 = _seed_email(aid, 1, "张三的周报", sender_email="zhangsan@example.com")

    assert main(["emails", "list", "--account-id", str(aid), "--from", "zhangsan@",
                 "--limit", "10"]) == EXIT_OK
    items = _out_lines(capsys)[0]["data"]["items"]
    assert [i["id"] for i in items] == [e1]

    assert main(["emails", "read", str(e1)]) == EXIT_OK
    detail = _out_lines(capsys)[0]["data"]
    assert detail["subject"] == "张三的周报" and detail["body_text"] == "原始正文"

    assert main(["emails", "read", "999999"]) == EXIT_PERMANENT
    assert _out_lines(capsys)[0]["error"]["code"] == "not_found"


def test_drafts全链路与两阶段确认(capsys, tmp_path):
    client.post("/api/extkeys/enabled", json={"enabled": True})
    save_config("http://127.0.0.1:8720", _make_key(["read", "write", "send"]))
    aid = _seed_account()
    eid = _seed_email(aid, 1, "项目排期")
    body_file = tmp_path / "reply.md"
    body_file.write_text("**收到**，明天回复。", encoding="utf-8")

    # 回复（--body-file md）
    assert main(["drafts", "reply", "--email-id", str(eid),
                 "--body-file", str(body_file)]) == EXIT_OK
    draft = _out_lines(capsys)[0]["data"]
    assert draft["mode"] == "reply" and draft["to_addrs"] == "boss@example.com"
    assert "<strong>收到</strong>" in draft["body_html"]

    # 阶段一：无 --confirmed → exit 8 + summary
    assert main(["drafts", "send", str(draft["id"])]) == EXIT_CONFIRM
    fail = _out_lines(capsys)[0]
    assert fail["ok"] is False and fail["error"]["code"] == "confirmation_required"
    summary = fail["error"]["summary"]
    assert summary["draft_id"] == draft["id"] and summary["to"] == "boss@example.com"
    assert "收到" in summary["body_preview"]

    # 阶段二：--confirmed → 到达 outbox；测试账号无 SMTP 凭据（smtp_missing→400 业务错，
    # exit 2）——路径已打通，真实发送由用户真机验证
    assert main(["drafts", "send", str(draft["id"]), "--confirmed"]) == EXIT_BAD_PARAMS
    assert _out_lines(capsys)[0]["error"]["code"] == "bad_request"

    # 建稿：body 与 body-file 同给 → exit 2
    assert main(["drafts", "create", "--account-id", str(aid), "--to", "a@b.com",
                 "--body", "x", "--body-file", str(body_file)]) == EXIT_BAD_PARAMS
    _cleanup_drafts(aid)


def test_emails_action带job轮询(capsys):
    client.post("/api/extkeys/enabled", json={"enabled": True})
    save_config("http://127.0.0.1:8720", _make_key(["read", "write"]))
    aid = _seed_account()
    e = _seed_email(aid, 1, "打标")
    assert main(["emails", "action", "--ids", str(e), "--action", "read"]) == EXIT_OK
    body = _out_lines(capsys)[0]["data"]
    # 打标类同步返回（无 job_id）；测试账号无 IMAP 凭据 → 该账号按失败计数（服务器
    # 打标失败的 data 层语义：ok=false + failed 计数，HTTP 200，CLI 照实透传）
    assert "job_id" not in body and body["ok"] is False and body["failed"] == 1


def test_watch基线不回放(capsys, monkeypatch):
    client.post("/api/extkeys/enabled", json={"enabled": True})
    save_config("http://127.0.0.1:8720", _make_key(["read"]))
    aid = _seed_account()
    _seed_email(aid, 1, "历史邮件")

    # 基线后 sleep 直接打断循环（KeyboardInterrupt → exit 0）
    monkeypatch.setattr(cli.time, "sleep", lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    assert main(["watch", "--account-id", str(aid), "--interval", "0"]) == EXIT_OK
    assert _out_lines(capsys) == []  # 基线轮不输出历史邮件


# ── B1 folders / B2 更新提示 / B3 agent 通道 ─────────────────

def _seed_folder(account_id: int, name: str = "INBOX") -> None:
    conn = database.get_conn()
    conn.execute(
        "INSERT INTO folders (account_id, name, delim, special_use, subscribed)"
        " VALUES (?, ?, '/', '', 1)", (account_id, name),
    )
    conn.commit()


def test_folders_list(capsys):
    "B1：folders list 走文件夹缓存（不触发服务器 LIST）。"
    client.post("/api/extkeys/enabled", json={"enabled": True})
    save_config("http://127.0.0.1:8720", _make_key(["read"]))
    aid = _seed_account()
    _seed_folder(aid)
    _seed_folder(aid, "Archived")
    assert main(["folders", "list", "--account-id", str(aid)]) == EXIT_OK
    envelope = _out_lines(capsys)[0]
    assert envelope["ok"] is True and "folders" in envelope["data"]


def test_drafts_delete(capsys):
    "v0.4.1：drafts delete 删新建草稿；AI 待审（pending_review）草稿业务拒绝。"
    client.post("/api/extkeys/enabled", json={"enabled": True})
    save_config("http://127.0.0.1:8720", _make_key(["read", "write"]))
    aid = _seed_account()

    # 新建 → 删除 → 再读 exit 6（资源不存在）
    assert main(["drafts", "create", "--account-id", str(aid), "--to", "a@b.com",
                 "--subject", "待删草稿", "--body", "x"]) == EXIT_OK
    draft = _out_lines(capsys)[0]["data"]
    assert main(["drafts", "delete", str(draft["id"])]) == EXIT_OK
    assert main(["drafts", "send", str(draft["id"])]) == EXIT_PERMANENT

    # 在途审批草稿不开放删除 → exit 2 业务拒绝（防 agent 误清审批队列）
    conn = database.get_conn()
    cur = conn.execute(
        "INSERT INTO user_drafts (account_id, mode, status, to_addrs, subject, body_html)"
        " VALUES (?, 'ai', 'pending_review', 'x@y.com', '审批中', '<p>z</p>')", (aid,))
    conn.commit()
    assert main(["drafts", "delete", str(int(cur.lastrowid))]) == EXIT_BAD_PARAMS
    conn.execute("DELETE FROM user_drafts WHERE id = ?", (int(cur.lastrowid),))
    conn.commit()


def test_folders_sync_wait模式(capsys):
    "v0.4.1：folders sync 带 wait=true 同步执行；无 IMAP 凭据的种子账号按业务失败透传。"
    client.post("/api/extkeys/enabled", json={"enabled": True})
    save_config("http://127.0.0.1:8720", _make_key(["write"]))
    aid = _seed_account()
    _seed_folder(aid)
    assert main(["folders", "sync", "--account-id", str(aid), "--folder", "INBOX"]) == EXIT_OK
    envelope = _out_lines(capsys)[0]
    # HTTP 成功（CLI envelope ok），data 里是同步结果；种子账号缺凭据 → ok=false 如实透出
    assert envelope["ok"] is True and envelope["data"]["ok"] is False
    assert "started" not in envelope["data"]  # wait 模式：不是后台线程的 {started} 响应


def test_watch_max_emails自动退出(capsys, monkeypatch):
    "v0.4.1：--max-emails 收满自动退出（agent 调用防挂起），不再必须 Ctrl-C。"
    client.post("/api/extkeys/enabled", json={"enabled": True})
    save_config("http://127.0.0.1:8720", _make_key(["read"]))
    aid = _seed_account()
    _seed_email(aid, 1, "历史邮件")

    # 首轮轮询为空，sleep 时注入一封新邮件 → 下轮输出 1 封即达 --max-emails 退出。
    # 注：cli.time 是全局 time 模块（anyio/限流器也在用 monotonic），不要 mock 它。
    def _seed_and_return(*_a):
        _seed_email(aid, 2, "新邮件")
    monkeypatch.setattr(cli.time, "sleep", _seed_and_return)
    assert main(["watch", "--account-id", str(aid), "--interval", "0",
                 "--max-emails", "1"]) == EXIT_OK
    lines = _out_lines(capsys)
    assert len(lines) == 1 and lines[0]["data"]["subject"] == "新邮件"


def test_agent_ask_未配置AI(capsys):
    "B3：AI 未配置时 agent ask 返回明确错误（exit 2，agent 据此告知用户）。"
    client.post("/api/extkeys/enabled", json={"enabled": True})
    save_config("http://127.0.0.1:8720", _make_key(["agent"]))
    assert main(["agent", "ask", "概况"]) == EXIT_BAD_PARAMS
    envelope = _out_lines(capsys)[0]
    assert envelope["ok"] is False


def test_agent_decide参数互斥():
    "B3：decide 必须二选一，缺省/双选都 exit 2（不发请求）。"
    assert main(["agent", "decide", "1"]) == EXIT_BAD_PARAMS
    assert main(["agent", "decide", "1", "--approve", "--reject"]) == EXIT_BAD_PARAMS


def test_semver比较与更新提示(monkeypatch, capsys):
    "B2：服务端版本高于 CLI 时输出附 _notice.update。"
    import nmail_cli

    assert cli._semver_tuple("0.10.0") > cli._semver_tuple("0.9.9") > cli._semver_tuple("0.9.8")
    client.post("/api/extkeys/enabled", json={"enabled": True})
    save_config("http://127.0.0.1:8720", _make_key(["read"]))
    monkeypatch.setattr(nmail_cli, "__version__", "0.0.1")
    cli._PENDING_NOTICE.clear()
    cli._probe_update_notice()
    assert cli._PENDING_NOTICE["update"]["server"].startswith("0.")
    aid = _seed_account()
    _seed_folder(aid)
    assert main(["folders", "list", "--account-id", str(aid)]) == EXIT_OK
    envelope = _out_lines(capsys)[-1]
    assert envelope["ok"] is True and envelope["_notice"]["update"]["cli"] == "0.0.1"
