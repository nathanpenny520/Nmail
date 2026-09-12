"""AI 总管家 Agent 测试（v0.4 P6，REDESIGN_PLAN §6）：读工具直执行与循环回灌、
审批模式出卡与批准执行、权限门控、自动模式发送降级、审计落库与撤销。
LLM 打桩脚本化（不出网）；IMAP 类操作走 create_draft/mark_emails 等可桩化路径。
"""
from __future__ import annotations

import json
import uuid

from fastapi.testclient import TestClient

from app.ai import agent
from app.db import database
from app.main import app

client = TestClient(app, base_url="http://127.0.0.1")

database.run_migrations()


def _aid(*, readonly: bool = False, grants: str | None = None) -> int:
    conn = database.get_conn()
    cur = conn.execute(
        "INSERT INTO accounts (email, imap_server, imap_port, ai_permission, ai_grants)"
        " VALUES (?, 'imap.test', 993, ?, ?)",
        (
            f"a{uuid.uuid4().hex[:8]}@example.com",
            "readonly" if readonly else "draft_review",
            grants,
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def _seed_email(aid: int, uid: int, subject: str, sender: str = "s@x.com") -> int:
    conn = database.get_conn()
    cur = conn.execute(
        "INSERT INTO emails (account_id, folder, uid, subject, sender_email, body_text)"
        " VALUES (?, 'INBOX', ?, ?, ?, '正文')",
        (aid, uid, subject, sender),
    )
    conn.commit()
    return int(cur.lastrowid)


def _script(monkeypatch, replies: list[str]) -> None:
    """按序回放 LLM 输出（tools JSON 或纯文本）；AI 配置打桩（不出网）。"""
    monkeypatch.setattr(agent.tasks, "_ai_config", lambda pid=None: ("http://x", "test-model", None))
    calls = {"n": 0}

    def fake_chat(base_url, model, api_key, messages):
        idx = min(calls["n"], len(replies) - 1)
        calls["n"] += 1
        return replies[idx], {"prompt_tokens": 1, "completion_tokens": 1}

    monkeypatch.setattr(agent.llm, "chat_messages", fake_chat)


def _collect(events: list[dict], etype: str) -> list[dict]:
    return [e for e in events if e.get("type") == etype]


def test_read_tool_loop_and_final_answer(monkeypatch):
    """读类工具直执行：搜索 → 结果回灌 → 最终文本回答；无审计行（读不落 ai_actions）。"""
    aid = _aid()
    _seed_email(aid, 1, "招新合作洽谈")
    _script(monkeypatch, [
        json.dumps({"tool": "search_emails", "args": {"q": "招新", "account_id": aid}}),
        "收件箱里有 1 封与招新相关的邮件：《招新合作洽谈》。",
    ])
    events = list(agent.run_stream("帮我找招新相关的邮件", None, None, [aid], "approval", None))
    calls = _collect(events, "tool_call")
    results = _collect(events, "tool_result")
    texts = _collect(events, "text")
    assert calls and calls[0]["tool"] == "search_emails"
    assert results[0]["ok"] is True
    assert texts and "招新" in texts[-1]["text"]
    assert database.get_conn().execute("SELECT COUNT(*) c FROM ai_actions").fetchone()["c"] == 0


def test_native_tool_markup_extraction():
    """部分模型把原生工具标记（DSML）当文本输出 → 二次提取为标准动作，不泄漏给用户。"""
    text = ('<|DSML|calls><|DSML|invoke name="list_folders">'
            '<|DSML|parameter name="args" string="false">{"account_id": "3"}'
            '</|DSML|parameter></|DSML|invoke></|DSML|calls>')
    action = agent._parse_model_action(text)
    assert action == {"tool": "list_folders", "args": {"account_id": "3"}}
    # 纯文本（非 JSON 非标记）→ None，作为最终回答展示
    assert agent._parse_model_action("这是给用户的普通回答。") is None


def test_write_tool_requires_approval_then_execute(monkeypatch):
    """审批模式：create_draft 出审批卡（pending 落库）→ 批准后执行并审计。"""
    aid = _aid()
    _seed_email(aid, 2, "会议邀请")
    _script(monkeypatch, [
        json.dumps({"tool": "create_draft",
                    "args": {"email_id": None, "to": "s@x.com", "subject": "回复：会议邀请",
                             "body": "收到，届时参加。"}}),
    ])
    events = list(agent.run_stream("回复这封会议邀请", None, None, [aid], "approval", None))
    approvals = _collect(events, "approval_required")
    assert len(approvals) == 1 and approvals[0]["tool"] == "create_draft"
    action_id = approvals[0]["action_id"]
    row = database.get_conn().execute(
        "SELECT status FROM ai_actions WHERE id = ?", (action_id,)).fetchone()
    assert row["status"] == "pending"

    result = agent.execute_action(action_id, "approve")
    assert result.get("status") == "executed" and result["result"].get("draft_id")
    drafts = database.get_conn().execute(
        "SELECT status, origin FROM user_drafts WHERE id = ?",
        (result["result"]["draft_id"],)).fetchone()
    assert drafts["status"] == "pending_review" and drafts["origin"] == "ai"
    assert database.get_conn().execute(
        "SELECT status FROM ai_actions WHERE id = ?", (action_id,)).fetchone()["status"] == "executed"

    # 拒绝路径：另一个 pending 被拒
    result2 = agent.execute_action(action_id, "reject")
    assert result2.get("error")  # 已执行的动作不能再 reject


def test_grant_denial(monkeypatch):
    """readonly 账号（仅 read 授权）执行整理类工具 → 权限不足回灌，不落 pending。"""
    aid = _aid(readonly=True)
    eid = _seed_email(aid, 3, "待归档")
    _script(monkeypatch, [
        json.dumps({"tool": "archive_emails", "args": {"ids": [eid]}}),
    ])
    events = list(agent.run_stream("把这封邮件归档", None, None, [aid], "approval", None))
    results = _collect(events, "tool_result")
    assert results and results[0]["ok"] is False
    assert "权限不足" in results[0]["summary"]
    assert not _collect(events, "approval_required")
    assert database.get_conn().execute(
        "SELECT COUNT(*) c FROM ai_actions WHERE account_id = ?", (aid,)
    ).fetchone()["c"] == 0


def test_auto_mode_send_draft_requires_recipient_allowlist(monkeypatch):
    """自动模式：草稿收件人不在通讯录/历史往来 → 降级审批卡（防注入外发）。"""
    aid = _aid(grants='{"read":true,"draft":true,"organize":true,"send":true}')
    conn = database.get_conn()
    conn.execute(
        "INSERT INTO user_drafts (account_id, mode, to_addrs, subject, body_html, status, origin)"
        " VALUES (?, 'reply', 'stranger@evil.com', 'Re: x', '<p>ok</p>', 'pending_review', 'ai')",
        (aid,),
    )
    conn.commit()
    draft_id = conn.execute("SELECT id FROM user_drafts WHERE account_id = ?", (aid,)).fetchone()["id"]
    _script(monkeypatch, [
        json.dumps({"tool": "send_draft", "args": {"draft_id": draft_id}}),
    ])
    events = list(agent.run_stream("把这条草稿发出去", None, None, [aid], "auto", None))
    approvals = _collect(events, "approval_required")
    assert len(approvals) == 1
    assert "不在通讯录与历史往来" in approvals[0]["reason"]


def test_auto_mode_send_allowed_for_known_recipient(monkeypatch):
    """自动模式：收件人在通讯录 → 直接执行并落审计（executed + 不可撤销）。"""
    aid = _aid(grants='{"read":true,"draft":true,"organize":true,"send":true}')
    conn = database.get_conn()
    conn.execute(
        "INSERT INTO user_drafts (account_id, mode, to_addrs, subject, body_html, status, origin)"
        " VALUES (?, 'reply', 'old@friend.com', 'Re: x', '<p>ok</p>', 'pending_review', 'ai')",
        (aid,),
    )
    draft_id = conn.execute("SELECT id FROM user_drafts WHERE account_id = ?", (aid,)).fetchone()["id"]
    contacts_core_upsert("old@friend.com", "老友", aid)
    _script(monkeypatch, [
        json.dumps({"tool": "send_draft", "args": {"draft_id": draft_id}}),
        "已发送给老友。",
    ])
    # 发送需要真实 SMTP——打桩 outbox.send_user_draft 只验证流程与审计
    monkeypatch.setattr("app.core.outbox.send_user_draft", lambda _id: None)
    events = list(agent.run_stream("发送", None, None, [aid], "auto", None))
    results = _collect(events, "tool_result")
    assert results and results[0]["ok"] is True
    row = database.get_conn().execute(
        "SELECT status, undo_json FROM ai_actions WHERE tool = 'send_draft' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert row["status"] == "executed" and row["undo_json"] is None  # 发送不可撤销


def contacts_core_upsert(email: str, name: str, account_id: int) -> None:
    from app.core import contacts as contacts_core

    contacts_core.upsert_contact(email, name, account_id)


def test_undo_mark_emails(monkeypatch):
    """撤销：标记已读后 undo 恢复原未读状态（IMAP 打桩，只验证本地状态机）。"""
    aid = _aid()
    eid = _seed_email(aid, 4, "可撤销")
    monkeypatch.setattr("app.ai.tools.mailbox.load_account", lambda _aid: object())
    monkeypatch.setattr("app.ai.tools.mailbox.open_imap", lambda _h: _FakeMB())
    _script(monkeypatch, [
        json.dumps({"tool": "mark_emails", "args": {"ids": [eid], "read": True}}),
        "已标记完成。",
    ])
    events = list(agent.run_stream("标记已读", None, None, [aid], "auto", None))
    assert _collect(events, "tool_result")[0]["ok"] is True
    row = database.get_conn().execute(
        "SELECT id, undo_json FROM ai_actions WHERE tool = 'mark_emails' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert row["undo_json"] is not None
    result = agent.undo_action(row["id"])
    assert result.get("undone") == 1
    assert database.get_conn().execute(
        "SELECT is_read FROM emails WHERE id = ?", (eid,)).fetchone()["is_read"] == 0


class _FakeMB:
    """IMAP 桩：folder.set / flag 无操作（本地状态机验证用）。"""

    def __init__(self):
        self.folder = self

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def set(self, folder):
        return None

    def flag(self, uids, flags, value):
        return None


# ── 会话范围越权防护（v0.4 审查 F2 回归）─────────────────────

def test_account_id_out_of_scope_rejected(monkeypatch):
    """会话限定账号 A，模型传账号 B 的 account_id → 读类工具也拒绝。"""
    aid_a = _aid()
    aid_b = _aid()
    _seed_email(aid_b, 21, "B 账号私有邮件")
    _script(monkeypatch, [
        json.dumps({"tool": "search_emails", "args": {"q": "私有", "account_id": aid_b}}),
        "好的。",
    ])
    events = list(agent.run_stream("看看另一个账号", None, None, [aid_a], "approval", None))
    results = _collect(events, "tool_result")
    assert results and results[0]["ok"] is False
    assert "不在当前会话范围" in results[0]["summary"]


def test_digest_stats_scoped_to_session_accounts():
    """digest_stats 只统计会话范围账号（原先汇总全部账号）。"""
    from app.ai import tools as T

    aid_a = _aid()
    aid_b = _aid()
    conn = database.get_conn()
    conn.execute(
        "INSERT INTO emails (account_id, folder, uid, subject, sender_email, is_read)"
        " VALUES (?, 'INBOX', 31, 'A 的邮件', 'a@x.com', 0)", (aid_a,))
    conn.execute(
        "INSERT INTO emails (account_id, folder, uid, subject, sender_email, is_read)"
        " VALUES (?, 'INBOX', 32, 'B 的邮件', 'b@x.com', 0)", (aid_b,))
    conn.commit()
    result = T.execute("digest_stats", {}, aid_a, [aid_a])
    assert result["收件箱邮件数"] == 1 and result["未读"] == 1
    out_of_scope = T.execute("digest_stats", {"account_id": aid_b}, aid_a, [aid_a])
    assert "error" in out_of_scope


def test_email_id_tools_reject_cross_account():
    """按邮件 id 的工具对范围外账号的邮件拒绝（宁紧勿松）。"""
    from app.ai import tools as T

    aid_a = _aid()
    eid_b = _seed_email(_aid(), 41, "别家的邮件")
    result = T.execute("mark_emails", {"ids": [eid_b], "read": True}, aid_a, [aid_a])
    assert "error" in result and "会话" in result["error"]


# ── 参数归一化与审批校验（v0.4 审查 S1/S2 回归）──────────────

def test_normalize_args_coercion_and_rejection():
    """类型矫正：ids/整数字符串可转、布尔只认真值拼写；必填缺失/错型拒绝。"""
    from app.ai import tools as T

    assert T.normalize_args("mark_emails", {"ids": ["1", 2], "read": "false"}) == {
        "ids": [1, 2], "read": False}
    assert T.normalize_args("send_draft", {"draft_id": "9"}) == {"draft_id": 9}
    import pytest

    with pytest.raises(ValueError, match="draft_id"):
        T.normalize_args("send_draft", {})
    with pytest.raises(ValueError, match="draft_id"):
        T.normalize_args("send_draft", {"draft_id": "abc"})
    with pytest.raises(ValueError, match="folder"):
        T.normalize_args("move_emails", {"ids": [1]})


def test_execute_action_validates_args_override(monkeypatch):
    """审批「改参数后批准」：必填缺失 → failed 落库，不执行。"""
    aid = _aid()
    _seed_email(aid, 62, "参数校验")
    _script(monkeypatch, [
        json.dumps({"tool": "move_emails", "args": {"ids": [1], "folder": "INBOX"}}),
    ])
    events = list(agent.run_stream("移动邮件", None, None, [aid], "approval", None))
    action_id = _collect(events, "approval_required")[0]["action_id"]
    result = agent.execute_action(action_id, "approve", {"ids": [1]})
    assert "参数校验失败" in result.get("error", "")
    assert database.get_conn().execute(
        "SELECT status, error FROM ai_actions WHERE id = ?", (action_id,)
    ).fetchone()["status"] == "failed"


def test_recipient_allowed_parses_display_name():
    """自动模式收件人约束解析「Name <邮箱>」（原先整串比对必不命中 → 恒降级审批）。"""
    from app.ai import tools as T

    aid = _aid()
    contacts_core_upsert("old@friend.com", "老友", aid)
    allowed, why = T.recipient_allowed("Old Friend <old@friend.com>", aid)
    assert allowed and not why
    denied, why2 = T.recipient_allowed("Stranger <stranger@evil.com>", aid)
    assert not denied and "不在通讯录" in why2
