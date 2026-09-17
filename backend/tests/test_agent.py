"""AI 总管家 Agent 测试（v0.4 P6，REDESIGN_PLAN §6）：读工具直执行与循环回灌、
审批模式出卡与批准执行、权限门控、自动模式发送降级、审计落库与撤销。
LLM 打桩脚本化（不出网）；IMAP 类操作走 create_draft/mark_emails 等可桩化路径。
"""
from __future__ import annotations

import json
import uuid

from fastapi.testclient import TestClient

from app.ai import agent
from app.ai import tools as T
from app.core import rule_proposals
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
    """按序回放 LLM 输出（tools JSON 或纯文本）；AI 配置打桩（不出网）。
    v2 默认走原生 function calling——这里强制探测为不支持，走 JSON 降级路径。"""
    monkeypatch.setattr(agent.tasks, "_ai_config", lambda pid=None: ("http://x", "test-model", None))
    monkeypatch.setattr(agent, "_native_supported", lambda *a, **k: False)
    calls = {"n": 0}

    def fake_chat(base_url, model, api_key, messages, max_tokens=2000, temperature=0.3):
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
    # 全角竖线变体（压测 run 33 实测：deepseek 在 JSON 降级模式下输出｜｜DSML｜｜）
    fullwidth = ('<｜｜DSML｜｜ calls> <｜｜DSML｜｜ invoke name="read_email"> '
                 '<｜｜DSML｜｜ parameter name="args" string="false">{"email_id": "460"}'
                 '</｜｜DSML｜｜ parameter> </｜｜DSML｜｜ invoke> </｜｜DSML｜｜ calls>')
    action2 = agent._parse_model_action(fullwidth)
    assert action2 == {"tool": "read_email", "args": {"email_id": "460"}}
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


# ── 操作历史管理（REDESIGN_PLAN §18.3 瘦身版）：审计行可删可清 ──

def test_delete_and_clear_actions():
    """单条删除 + 批量清理三档（old 保留已发送审计 / failed / all）。"""
    conn = database.get_conn()
    a_fail = agent._record_action(None, None, "mark_emails", {}, "auto", "ui", "failed", error="x")
    a_send = agent._record_action(None, None, "send_draft", {}, "auto", "ui", "executed",
                                  result={"sent": True})
    a_mark = agent._record_action(None, None, "mark_emails", {}, "auto", "ui", "executed",
                                  result={"updated": 1})
    conn.execute("UPDATE ai_actions SET created_at = datetime('now', '-100 days') WHERE id IN (?, ?)",
                 (a_send, a_mark))
    conn.commit()

    assert agent.delete_action(a_fail) == {"deleted": 1}
    assert agent.delete_action(999999) == {"error": "记录不存在"}

    # old：90 天前清掉，但 send_draft executed 审计永久保留
    assert agent.clear_actions("old") == {"deleted": 1}
    assert conn.execute("SELECT COUNT(*) n FROM ai_actions WHERE id = ?", (a_send,)).fetchone()["n"] == 1
    assert conn.execute("SELECT COUNT(*) n FROM ai_actions WHERE id = ?", (a_mark,)).fetchone()["n"] == 0

    assert "error" in agent.clear_actions("bad")
    agent._record_action(None, None, "mark_emails", {}, "auto", "ui", "rejected")
    assert agent.clear_actions("failed")["deleted"] >= 1
    total = conn.execute("SELECT COUNT(*) n FROM ai_actions").fetchone()["n"]
    assert agent.clear_actions("all") == {"deleted": total}
    assert conn.execute("SELECT COUNT(*) n FROM ai_actions").fetchone()["n"] == 0


# ── 跨会话记忆（REDESIGN_PLAN §18.5）──────────────────────────────

def test_memory_tools_crud():
    """save/list/delete + 同文去重更新 + evidence 硬要求。"""
    conn = database.get_conn()
    conn.execute("DELETE FROM agent_memory")
    conn.commit()
    assert "error" in T.execute("save_memory", {"content": "正式"}, 0)  # 缺 evidence
    r1 = T.execute("save_memory", {"content": "给张总回信要正式", "evidence": "给张总回信要正式一点"}, 0)
    assert "saved" in r1
    r2 = T.execute("save_memory", {"content": "给张总回信要正式", "evidence": "对张总正式些"}, 0)
    assert "updated" in r2 and r2["updated"] == r1["saved"]  # 同文去重更新
    r3 = T.execute("save_memory", {"content": "广告邮件直接归档", "evidence": "广告类直接归档"}, 0)
    assert "saved" in r3
    lst = T.execute("list_memory", {}, 0)
    assert lst["count"] == 2
    assert any(m["evidence"] == "对张总正式些" for m in lst["memories"])
    assert T.execute("delete_memory", {"memory_id": r3["saved"]}, 0) == {"deleted": r3["saved"]}
    assert "error" in T.execute("delete_memory", {"memory_id": r3["saved"]}, 0)
    conn.execute("DELETE FROM agent_memory")
    conn.commit()


def test_memory_in_system_prompt():
    """有记忆注入系统提示词尾部；清空后无该块。"""
    conn = database.get_conn()
    conn.execute("DELETE FROM agent_memory")
    conn.commit()
    assert "用户长期偏好" not in agent._system_prompt([], True)
    r = T.execute("save_memory", {"content": "给张总回信要正式", "evidence": "给张总回信要正式一点"}, 0)
    prompt = agent._system_prompt([], True)
    assert "用户长期偏好" in prompt
    assert "给张总回信要正式" in prompt and "「给张总回信要正式一点」" in prompt
    T.execute("delete_memory", {"memory_id": r["saved"]}, 0)
    assert "用户长期偏好" not in agent._system_prompt([], True)


def test_agent_saves_memory_in_loop(monkeypatch):
    """用户说「记住…」→ auto 模式直接执行（organize 授权）→ 审计留痕 + 注入提示词。"""
    conn = database.get_conn()
    conn.execute("DELETE FROM agent_memory")
    conn.commit()
    _script(monkeypatch, [
        json.dumps({"tool": "save_memory",
                    "args": {"content": "广告邮件直接归档", "evidence": "记住：广告类邮件直接归档"}}),
        "已记住，之后广告类邮件我会直接归档。",
    ])
    aid = _aid()
    events = list(agent.run_stream("记住：广告类邮件直接归档", None, None, [aid], "auto", None))
    tr = _collect(events, "tool_result")[0]
    assert tr["ok"] is True and tr["tool"] == "save_memory"
    row = conn.execute(
        "SELECT id, evidence FROM agent_memory WHERE content = '广告邮件直接归档'"
    ).fetchone()
    assert row is not None and row["evidence"] == "记住：广告类邮件直接归档"
    act = conn.execute(
        "SELECT status FROM ai_actions WHERE tool = 'save_memory' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert act["status"] == "executed"
    assert "广告邮件直接归档" in agent._system_prompt([aid], True)


def test_memory_api():
    """设置页查看/删除端点。"""
    conn = database.get_conn()
    conn.execute("DELETE FROM agent_memory")
    conn.commit()
    r = T.execute("save_memory", {"content": "偏好 A", "evidence": "原话 A"}, 0)
    client = TestClient(app, base_url="http://127.0.0.1")  # 过 S1 本机 Host 校验
    resp = client.get("/api/ai/memory")
    assert resp.status_code == 200
    items = resp.json()["memories"]
    assert len(items) == 1 and items[0]["content"] == "偏好 A" and items[0]["evidence"] == "原话 A"
    resp = client.delete(f"/api/ai/memory/{r['saved']}")
    assert resp.status_code == 200 and resp.json()["ok"] is True
    resp = client.delete(f"/api/ai/memory/{r['saved']}")
    assert resp.json().get("error") == "记忆不存在"


# ── 规则提议与调度晨报（REDESIGN_PLAN §18.5/§18.6）────────────────

def test_rule_proposals_flow():
    """观察→阈值提议→采纳入黑名单 / 忽略后不再提。"""
    conn = database.get_conn()
    conn.execute("DELETE FROM rule_observations")
    conn.execute("DELETE FROM agent_proposals")
    conn.execute("DELETE FROM sender_lists WHERE pattern IN ('promo@spam.com', 'ads@x.com')")
    conn.commit()
    for i in range(3):
        conn.execute(
            "INSERT OR IGNORE INTO rule_observations (email_id, account_id, sender_email, action)"
            " VALUES (?, 1, 'promo@spam.com', 'archive')", (9000 + i,),
        )
    conn.commit()
    rule_proposals.observe(
        [{"id": 9003, "account_id": 1, "sender_email": "promo@spam.com"}], "archive")
    row = conn.execute(
        "SELECT id, evidence_count FROM agent_proposals"
        " WHERE pattern = 'promo@spam.com' AND status = 'pending'").fetchone()
    assert row is not None and row["evidence_count"] >= 3
    # 已在名单/已有 pending → 不重复提
    rule_proposals.propose()
    assert conn.execute(
        "SELECT COUNT(*) n FROM agent_proposals WHERE pattern = 'promo@spam.com'"
    ).fetchone()["n"] == 1

    resp = client.post(f"/api/ai/proposals/{row['id']}/decide", json={"decision": "approve"})
    assert resp.json()["status"] == "approved"
    assert conn.execute(
        "SELECT 1 FROM sender_lists WHERE pattern = 'promo@spam.com' AND list_type = 'blacklist'"
    ).fetchone()
    resp = client.post(f"/api/ai/proposals/{row['id']}/decide", json={"decision": "approve"})
    assert "error" in resp.json()  # 已决定不能重复操作

    # 忽略路径：reject 后同发件人不复活提议
    for i in range(4):
        conn.execute(
            "INSERT OR IGNORE INTO rule_observations (email_id, account_id, sender_email, action)"
            " VALUES (?, 1, 'ads@x.com', 'trash')", (9100 + i,),
        )
    conn.commit()
    rule_proposals.propose()
    prow = conn.execute(
        "SELECT id FROM agent_proposals WHERE pattern = 'ads@x.com' AND status = 'pending'"
    ).fetchone()
    assert prow is not None
    resp = client.post(f"/api/ai/proposals/{prow['id']}/decide", json={"decision": "reject"})
    assert resp.json()["status"] == "rejected"
    conn.execute(
        "INSERT OR IGNORE INTO rule_observations (email_id, account_id, sender_email, action)"
        " VALUES (9200, 1, 'ads@x.com', 'trash')"
    )
    conn.commit()
    rule_proposals.propose()
    assert conn.execute(
        "SELECT COUNT(*) n FROM agent_proposals WHERE pattern = 'ads@x.com' AND status = 'pending'"
    ).fetchone()["n"] == 0
    conn.execute("DELETE FROM rule_observations")
    conn.execute("DELETE FROM agent_proposals")
    conn.execute("DELETE FROM sender_lists WHERE pattern IN ('promo@spam.com', 'ads@x.com')")
    conn.commit()


def test_scheduler_allowed_tools(monkeypatch):
    """白名单硬边界：allowed 外工具（schema 已过滤仍被模型点名）执行层拒绝并回灌。"""
    aid = _aid(grants='{"read":true,"draft":true,"organize":true,"send":true}')
    _script(monkeypatch, [
        json.dumps({"tool": "send_draft", "args": {"draft_id": 1}}),
        "定时运行不做发送。",
    ])
    events = list(agent.run_stream("把草稿 1 发出去", None, None, [aid], "auto", None,
                                   origin="scheduler",
                                   allowed_tools=agent.SCHEDULER_ALLOWED))
    tr = _collect(events, "tool_result")[0]
    assert tr["ok"] is False and "不在本次定时运行" in tr["summary"]
    assert not _collect(events, "approval_required")  # 拒绝发生在审批判定之前
    assert database.get_conn().execute(
        "SELECT COUNT(*) c FROM ai_actions WHERE account_id = ?", (aid,)
    ).fetchone()["c"] == 0  # 被拒调用不落审计


def test_allowed_persisted_for_resume():
    """allowed_json 落库 → _load_run 恢复（续跑时硬边界不丢失）。"""
    aid = _aid()
    state = agent.RunState(session_id=None, account_ids=[aid], mode="auto",
                           profile_id=None, origin="scheduler")
    state.allowed = agent.SCHEDULER_ALLOWED
    state.run_id = agent._create_run(state)
    loaded = agent._load_run(state.run_id)
    assert loaded.allowed == agent.SCHEDULER_ALLOWED
    state2 = agent.RunState(session_id=None, account_ids=[aid], mode="auto",
                            profile_id=None, origin="ui")
    state2.run_id = agent._create_run(state2)
    loaded2 = agent._load_run(state2.run_id)
    assert loaded2.allowed is None  # 未设白名单 = 不限
