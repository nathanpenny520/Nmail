"""Agent v2 循环测试（REDESIGN_PLAN §17）：原生 function calling 流式、审批暂停与
续跑、拒绝改道、步数/预算暂停与继续、JSON 文本兜底解析、segments 构建、
搜索跨文件夹、set_category 与撤销。LLM 打桩脚本化（不出网）。"""
from __future__ import annotations

import json
import uuid

from app.ai import agent
from app.ai import tools as T
from app.db import database

database.run_migrations()


def _aid(*, grants: str | None = None) -> int:
    conn = database.get_conn()
    cur = conn.execute(
        "INSERT INTO accounts (email, imap_server, imap_port, ai_permission, ai_grants)"
        " VALUES (?, 'imap.test', 993, ?, ?)",
        (f"v2{uuid.uuid4().hex[:8]}@example.com", "draft_review", grants),
    )
    conn.commit()
    return int(cur.lastrowid)


def _seed_email(aid: int, uid: int, subject: str, sender: str = "s@x.com",
                folder: str = "INBOX") -> int:
    conn = database.get_conn()
    cur = conn.execute(
        "INSERT INTO emails (account_id, folder, uid, subject, sender_email, body_text)"
        " VALUES (?, ?, ?, ?, ?, '正文')",
        (aid, folder, uid, subject, sender),
    )
    conn.commit()
    return int(cur.lastrowid)


def _native_script(monkeypatch, steps: list[tuple]):
    """原生协议打桩：steps 为 [(text_deltas, calls), ...]；返回记录器（校验 tool_choice）。"""
    monkeypatch.setattr(agent.tasks, "_ai_config", lambda pid=None: ("http://x", "test-model", None))
    monkeypatch.setattr(agent, "_native_supported", lambda *a, **k: True)
    rec = {"n": 0, "tool_choices": []}

    def fake_iter(base_url, model, api_key, messages, tools=None, tool_choice=None,
                  max_tokens=2000, temperature=0.3):
        idx = min(rec["n"], len(steps) - 1)
        rec["n"] += 1
        rec["tool_choices"].append(tool_choice)
        deltas, calls = steps[idx]
        for d in deltas:
            yield ("text_delta", d)
        return (deltas[-1] if deltas else ""), calls, {"prompt_tokens": 2, "completion_tokens": 2}, "stop"

    monkeypatch.setattr(agent.llm, "iter_chat_step", fake_iter)
    return rec


def _collect(events: list[dict], etype: str) -> list[dict]:
    return [e for e in events if e.get("type") == etype]


def _run_row(run_id: int):
    return database.get_conn().execute(
        "SELECT * FROM agent_runs WHERE id = ?", (run_id,)).fetchone()


def test_native_stream_loop_and_persistence(monkeypatch):
    """原生协议：text_delta 流式 → 工具调用回灌（role:tool）→ 最终文本；
    agent_runs 落 done 且 messages 含配对的 tool 消息。"""
    aid = _aid()
    _seed_email(aid, 1, "招新合作洽谈")
    rec = _native_script(monkeypatch, [
        (["我来搜索一下"], [{"id": "c1", "name": "search_emails",
                             "arguments": {"q": "招新", "account_id": aid}}]),
        (["收件箱里有 1 封招新相关的邮件。"], []),
    ])
    events = list(agent.run_stream("帮我找招新的邮件", None, None, [aid], "approval", None))
    assert events[0]["type"] == "run_started" and events[0]["run_id"] > 0
    deltas = _collect(events, "text_delta")
    # 过程叙述与最终回答都应流式下发
    assert [d["delta"] for d in deltas] == ["我来搜索一下", "收件箱里有 1 封招新相关的邮件。"]
    assert _collect(events, "tool_call")[0]["tool"] == "search_emails"
    assert _collect(events, "tool_result")[0]["ok"] is True
    assert _collect(events, "text")[-1]["text"].startswith("收件箱里有")
    assert events[-1]["type"] == "done"
    assert rec["tool_choices"] == [None, None]  # 预算内不强制
    row = _run_row(events[0]["run_id"])
    assert row["status"] == "done"
    messages = json.loads(row["messages_json"])
    assert any(m.get("role") == "tool" and m.get("tool_call_id") == "c1" for m in messages)


def test_native_approval_pause_then_resume(monkeypatch):
    """审批暂停 → 批准 → resume 续跑：执行结果回灌、最终文本、run 置 done。"""
    aid = _aid()
    _native_script(monkeypatch, [
        ([], [{"id": "c1", "name": "create_draft",
               "arguments": {"to": "s@x.com", "subject": "Re: 会议", "body": "收到"}}]),
        (["草稿已起草完成，请查看待审列表。"], []),
    ])
    events = list(agent.run_stream("回复会议邀请", None, None, [aid], "approval", None))
    approvals = _collect(events, "approval_required")
    assert len(approvals) == 1 and approvals[0]["run_id"] == events[0]["run_id"]
    paused = _collect(events, "paused")
    assert paused and paused[0]["reason"] == "approval"
    run_id = events[0]["run_id"]
    assert _run_row(run_id)["status"] == "waiting_approval"

    result = agent.execute_action(approvals[0]["action_id"], "approve")
    assert result.get("status") == "executed"

    events2 = list(agent.resume_stream(run_id))
    assert events2[0]["type"] == "run_started"
    tr = _collect(events2, "tool_result")
    assert tr and tr[0]["ok"] is True and tr[0]["action_id"] == approvals[0]["action_id"]
    assert _collect(events2, "text")[-1]["text"].startswith("草稿已起草完成")
    row = _run_row(run_id)
    assert row["status"] == "done"
    messages = json.loads(row["messages_json"])
    tool_msg = next(m for m in messages if m.get("role") == "tool" and m.get("tool_call_id") == "c1")
    assert "draft_id" in tool_msg["content"]


def test_reject_feeds_back_and_run_completes(monkeypatch):
    """拒绝续跑：拒绝原因回灌（模型改道），最终 run 置 done 而非卡死。"""
    aid = _aid()
    _native_script(monkeypatch, [
        ([], [{"id": "c1", "name": "create_draft",
               "arguments": {"to": "s@x.com", "subject": "Re: 会议", "body": "收到"}}]),
        (["好的，已按你的要求取消发送。"], []),
    ])
    events = list(agent.run_stream("回复会议邀请", None, None, [aid], "approval", None))
    approvals = _collect(events, "approval_required")
    run_id = events[0]["run_id"]
    agent.execute_action(approvals[0]["action_id"], "reject")

    events2 = list(agent.resume_stream(run_id))
    tr = _collect(events2, "tool_result")
    assert tr and tr[0]["ok"] is False and "拒绝" in tr[0]["summary"]
    assert _collect(events2, "text")[-1]["text"].startswith("好的，已按你的要求取消")
    assert _run_row(run_id)["status"] == "done"


def test_max_steps_pause_and_continue(monkeypatch):
    """步数兜底触顶 → paused_max_steps；续跑授予新的一段步数（可再次暂停）。"""
    aid = _aid()
    monkeypatch.setattr(agent, "MAX_STEPS", 2)
    _native_script(monkeypatch, [
        ([], [{"id": "c1", "name": "digest_stats", "arguments": {}}]),
        ([], [{"id": "c2", "name": "digest_stats", "arguments": {}}]),
    ])
    events = list(agent.run_stream("概况", None, None, [aid], "approval", None))
    paused = _collect(events, "paused")
    assert paused and paused[0]["reason"] == "max_steps"
    assert _collect(events, "tool_result")  # 前两步的工具确实执行过
    run_id = events[0]["run_id"]
    assert _run_row(run_id)["status"] == "paused_max_steps"

    events2 = list(agent.resume_stream(run_id))
    assert len(_collect(events2, "tool_result")) == 2  # 新的一段预算里又跑了两步
    assert _collect(events2, "paused")[0]["reason"] == "max_steps"


def test_budget_forces_text_then_pauses_if_ignored(monkeypatch):
    """预算耗尽：先 tool_choice=none 强制收尾；模型仍要调工具 → paused_budget；
    续跑（预算重置）后正常文本收尾。"""
    aid = _aid()
    rec = _native_script(monkeypatch, [
        ([], [{"id": "c1", "name": "digest_stats", "arguments": {}}]),
        (["预算到点了，直接说结论：一切正常。"], []),
    ])
    state = agent.RunState(session_id=None, account_ids=[aid], mode="approval",
                           profile_id=None, origin="ui")
    state.messages = [{"role": "system", "content": "s"}, {"role": "user", "content": "概况"}]
    state.native = True
    state.budget_used_s = agent.TIME_BUDGET_S + 1  # 直接置于超预算态
    state.run_id = agent._create_run(state)
    events = list(agent._loop(state))
    assert rec["tool_choices"][0] == "none"  # 预算收尾：禁用工具
    paused = _collect(events, "paused")
    assert paused and paused[0]["reason"] == "budget"  # 模型不理会 → 暂停
    run_id = state.run_id
    assert _run_row(run_id)["status"] == "paused_budget"

    events2 = list(agent.resume_stream(run_id))
    assert rec["tool_choices"][1] is None  # 续跑=新预算，不再强制
    assert _collect(events2, "text")[-1]["text"].startswith("预算到点了")
    assert _run_row(run_id)["status"] == "done"


def test_native_json_text_fallback_parse(monkeypatch):
    """原生模式下模型无视 tools 输出裸 JSON 文本 → 兜底解析为工具调用，不泄漏给用户。"""
    aid = _aid()
    _native_script(monkeypatch, [
        (['{"tool": "digest_stats", "args": {}}'], []),
        (["概况：收件箱 1 封。"], []),
    ])
    events = list(agent.run_stream("概况", None, None, [aid], "approval", None))
    assert _collect(events, "tool_call")[0]["tool"] == "digest_stats"
    assert not any('{"tool"' in (e.get("text") or "") for e in _collect(events, "text"))


def test_extract_json_balanced_with_noise():
    """止血回归（§17.1）：混入幻觉 <result> 的输出按首个平衡 JSON 提取，不再整体泄漏。"""
    text = '{"tool": "digest_stats", "args": {}}\n<result> {"account": "x"} </result>'
    action = agent._parse_model_action(text)
    assert action == {"tool": "digest_stats", "args": {}}


def test_build_segments_shape():
    """事件 → 分段：text 合并、step 状态流转、审批前置 waiting、error 内联。"""
    from app.api.ai import _build_segments

    events = [
        {"type": "run_started", "run_id": 1},
        {"type": "text_delta", "delta": "我先"},
        {"type": "text_delta", "delta": "看看概况。"},
        {"type": "text", "text": "我先看看概况。"},
        {"type": "tool_call", "tool": "digest_stats", "call_id": "c1", "args": {}},
        {"type": "tool_result", "tool": "digest_stats", "call_id": "c1", "ok": True,
         "summary": "完成"},
        {"type": "tool_call", "tool": "send_draft", "call_id": "c2", "args": {"draft_id": 1}},
        {"type": "approval_required", "action_id": 9, "tool": "send_draft", "call_id": "c2",
         "args": {"draft_id": 1}, "reason": "审批模式", "run_id": 1, "meta": {}},
        {"type": "paused", "reason": "approval", "run_id": 1},
        {"type": "done"},
    ]
    segs = _build_segments(events)
    assert [s["kind"] for s in segs] == ["text", "step", "step", "approval"]
    assert segs[0]["content"] == "我先看看概况。"
    assert segs[1]["status"] == "ok" and segs[1]["summary"] == "完成"
    assert segs[2]["status"] == "waiting" and segs[2]["action_id"] == 9
    assert segs[3]["reason"] == "审批模式"

    echo = _build_segments([
        {"type": "tool_result", "tool": "send_draft", "call_id": "c2", "ok": True,
         "summary": "已发送", "action_id": 9},
    ])
    assert echo[0]["kind"] == "step" and echo[0].get("echo") is True  # 续跑流的回放步


def test_search_covers_archived_and_filters():
    """§17.3 搜索增强：默认覆盖归档文件夹（修 INBOX 硬编码）；分类/未读过滤可用。"""
    aid = _aid()
    _seed_email(aid, 51, "促销邮件标题", sender="news@shop.com", folder="Archived")
    _seed_email(aid, 52, "同事来信", sender="boss@corp.com")
    found = T.execute("search_emails", {"sender": "news@shop.com"}, aid, [aid])
    assert found.get("count") == 1  # 归档文件夹里的邮件能搜到
    inbox_only = T.execute("search_emails", {"sender": "news@shop.com", "folder": "INBOX"}, aid, [aid])
    assert inbox_only.get("count") == 0
    by_cat = T.execute("search_emails", {"category": "promo"}, aid, [aid])
    assert "error" not in by_cat
    hint = T.execute("search_emails", {"q": "不存在的关键词xyz"}, aid, [aid])
    assert hint.get("count") == 0 and "hint" in hint  # 空结果带下一步建议


def test_set_category_tool_and_undo_roundtrip(monkeypatch):
    """set_category：设置/清除分类与需回复标记，undo 恢复原值。"""
    aid = _aid()
    eid = _seed_email(aid, 61, "待分类")
    result = T.execute("set_category", {"ids": [eid], "category": "promo", "needs_reply": True},
                       aid, [aid])
    assert result.get("updated") == 1
    row = database.get_conn().execute(
        "SELECT category, needs_reply FROM emails WHERE id = ?", (eid,)).fetchone()
    assert row["category"] == "promo" and row["needs_reply"] == 1

    # agent 层审计 + undo：auto 模式直执行落 ai_actions（含 undo_json）
    _native_script(monkeypatch, [
        ([], [{"id": "c9", "name": "set_category",
               "arguments": {"ids": [eid], "category": "work"}}]),
        (["已改好分类。"], []),  # 收尾文本，避免脚本循环复用导致二次执行
    ])
    events = list(agent.run_stream("改分类", None, None, [aid], "auto", None))
    assert _collect(events, "tool_result")[0]["ok"] is True
    action = database.get_conn().execute(
        "SELECT id, undo_json FROM ai_actions WHERE tool = 'set_category'"
        " ORDER BY id DESC LIMIT 1").fetchone()
    assert action["undo_json"] is not None
    assert agent.undo_action(action["id"]).get("undone") == 1
    row = database.get_conn().execute(
        "SELECT category, needs_reply FROM emails WHERE id = ?", (eid,)).fetchone()
    assert row["category"] == "promo" and row["needs_reply"] == 1  # 回到 undo 记录的原值


def test_resume_rejects_unknown_or_finished_run():
    """不存在的 run / 已完成的 run 不可续跑。"""
    events = list(agent.resume_stream(999999))
    assert events[0]["type"] == "error"
    aid = _aid()
    state = agent.RunState(session_id=None, account_ids=[aid], mode="approval",
                           profile_id=None, origin="ui")
    state.messages = [{"role": "system", "content": "s"}, {"role": "user", "content": "q"}]
    state.run_id = agent._create_run(state)
    agent._save_run(state, "done")
    events2 = list(agent.resume_stream(state.run_id))
    assert events2[0]["type"] == "error"
