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


def test_parallel_calls_approval_resume_fills_siblings(monkeypatch):
    """压测回归（2026-09-15）：审批暂停落在并行调用批中间——同批未执行的 call 续跑时
    必须补 tool 回应，否则 OpenAI 兼容端点 400（tool_calls 须逐 id 回应，deepseek 实测）。"""
    aid = _aid()
    eid = _seed_email(aid, 71, "待整理")
    _native_script(monkeypatch, [
        ([], [{"id": "c_del", "name": "star_emails", "arguments": {"ids": [eid], "star": True}},
              {"id": "c_skip", "name": "digest_stats", "arguments": {}}]),
        (["好的，已按批准结果收尾。"], []),
    ])
    events = list(agent.run_stream("并行批", None, None, [aid], "approval", None))
    approvals = _collect(events, "approval_required")
    assert approvals and approvals[0]["call_id"] == "c_del"  # 批里第一个写类出卡即暂停
    run_id = events[0]["run_id"]
    agent.execute_action(approvals[0]["action_id"], "approve")

    events2 = list(agent.resume_stream(run_id))
    assert events2[-1]["type"] == "done" and _collect(events2, "error") == []
    messages = json.loads(_run_row(run_id)["messages_json"])
    tool_ids = [m.get("tool_call_id") for m in messages if m.get("role") == "tool"]
    assert "c_del" in tool_ids and "c_skip" in tool_ids  # 同批 sibling 也被回应
    skip = next(m for m in messages if m.get("tool_call_id") == "c_skip")
    assert "跳过" in skip["content"]
    call_ids = {tc["id"] for m in messages for tc in (m.get("tool_calls") or [])}
    assert call_ids == set(tool_ids)  # 配对完整：每个 call 恰有回应


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
    """步数兜底触顶 → paused_max_steps；续跑授予新的一段步数（可再次暂停）。
    打桩脚本最后一格是「仍要调工具」形态 → 无小结，行为与 A1 前一致（回归）。"""
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


def test_max_steps_wrapup_summary_before_pause(monkeypatch):
    """A1 触顶收尾：步数耗尽先强制小结（assistant 落 messages、text 事件下发）
    再 paused_max_steps；小结前注入的收尾指令是临时消息（不留在历史）。"""
    aid = _aid()
    monkeypatch.setattr(agent, "MAX_STEPS", 2)
    rec = _native_script(monkeypatch, [
        ([], [{"id": "c1", "name": "digest_stats", "arguments": {}}]),
        ([], [{"id": "c2", "name": "digest_stats", "arguments": {}}]),
        (["小结：已查两轮概况，收件箱无异常。"], []),  # 第 3 次调用=触顶收尾小结
        ([], [{"id": "c4", "name": "digest_stats", "arguments": {}}]),
        ([], [{"id": "c5", "name": "digest_stats", "arguments": {}}]),
    ])
    events = list(agent.run_stream("概况", None, None, [aid], "approval", None))
    paused = _collect(events, "paused")
    assert paused and paused[0]["reason"] == "max_steps"
    assert _collect(events, "text")[-1]["text"].startswith("小结：已查两轮概况")
    run_id = events[0]["run_id"]
    assert _run_row(run_id)["status"] == "paused_max_steps"
    messages = json.loads(_run_row(run_id)["messages_json"])
    assert messages[-1]["role"] == "assistant" and "小结" in messages[-1]["content"]
    assert not any("预算已到" in str(m.get("content")) for m in messages)  # 收尾指令已弹出

    # 续跑：新的一段步数 + 继续锚点注入 → 再跑两步后再次触顶（无小结形态，脚本钳位）
    events2 = list(agent.resume_stream(run_id))
    assert len(_collect(events2, "tool_result")) == 2
    assert _collect(events2, "paused")[0]["reason"] == "max_steps"
    messages2 = json.loads(_run_row(run_id)["messages_json"])
    assert any("用户选择继续" in str(m.get("content")) for m in messages2)


def test_budget_forces_text_then_pauses_if_ignored(monkeypatch):
    """预算耗尽：先 tool_choice=none 强制收尾；模型仍要调工具 → A1 小结后 paused_budget；
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
    assert rec["tool_choices"][1] is None    # A1 收尾小结：禁工具的普通调用
    assert _collect(events, "text")[-1]["text"].startswith("预算到点了")  # 小结已下发
    paused = _collect(events, "paused")
    assert paused and paused[0]["reason"] == "budget"  # 小结后仍暂停可续
    run_id = state.run_id
    assert _run_row(run_id)["status"] == "paused_budget"

    events2 = list(agent.resume_stream(run_id))
    assert rec["tool_choices"][2] is None  # 续跑=新预算，不再强制
    assert _collect(events2, "text")[-1]["text"].startswith("预算到点了")
    assert _run_row(run_id)["status"] == "done"


def test_final_answer_mismatch_gets_corrected(monkeypatch):
    """A2 完成断言校验：本 run 零工具调用却声称「已发送」→ 回灌纠正一次，
    模型改口后正常收尾（无警示行、无虚构）。"""
    aid = _aid()
    _native_script(monkeypatch, [
        (["已发送给 boss@x.com 了。"], []),
        (["刚才那封还没有发送，需要我现在起草吗？"], []),
    ])
    events = list(agent.run_stream("帮我发给老板", None, None, [aid], "approval", None))
    texts = [e["text"] for e in _collect(events, "text")]
    assert texts[-1].startswith("刚才那封还没有发送")  # 改口后的回答
    assert "系统注记" not in texts[-1]  # 一次纠正即改正 → 不加警示
    row = _run_row(events[0]["run_id"])
    assert row["status"] == "done"
    messages = json.loads(row["messages_json"])
    assert any("没有对应的工具执行记录" in str(m.get("content")) for m in messages)  # 纠正已回灌
    assert events[-1]["type"] == "done"


def test_final_answer_mismatch_twice_warns_not_blocks(monkeypatch):
    """A2 二次仍不一致：原文放行 + 末尾警示行（不静默、不阻断，拍板项 4 推荐值）。"""
    aid = _aid()
    _native_script(monkeypatch, [
        (["已发送给 boss@x.com 了。"], []),
    ])
    events = list(agent.run_stream("帮我发给老板", None, None, [aid], "approval", None))
    final = _collect(events, "text")[-1]["text"]
    assert final.startswith("已发送给")  # 原文保留
    assert "没有对应的执行记录" in final  # 警示行附加
    assert _run_row(events[0]["run_id"])["status"] == "done"


def test_completion_mismatch_matrix():
    """A2 判定矩阵：有本 run 工具调用记录的断言放行；无关断言/否定句不拦。"""
    aid = _aid()
    state = agent.RunState(session_id=None, account_ids=[aid], mode="auto",
                           profile_id=None, origin="ui")
    # 空历史：发送断言 → 不一致
    assert agent._completion_mismatch(state, "已发送给 a@b.com") != ""
    # 有 send_draft 调用记录（native 形态）→ 放行
    state.messages = [{"role": "assistant", "content": "",
                       "tool_calls": [{"id": "c1", "type": "function",
                                       "function": {"name": "send_draft", "arguments": "{}"}}]}]
    assert agent._completion_mismatch(state, "已发送给 a@b.com") == ""
    # JSON 降级协议回显形态同样被识别
    state.messages = [{"role": "assistant", "content": '{"tool": "send_draft", "args": {}}'}]
    assert agent._completion_mismatch(state, "已回复对方了") == ""
    # 无关断言（只读类动词）不拦
    assert agent._completion_mismatch(state, "搜到了 3 封邮件") == ""
    # 归档断言只有搜索记录 → 不一致
    state.messages = [{"role": "assistant", "content": "",
                       "tool_calls": [{"id": "c2", "type": "function",
                                       "function": {"name": "search_emails", "arguments": "{}"}}]}]
    assert agent._completion_mismatch(state, "已归档 5 封") != ""


def test_feedback_truncation_keeps_head_and_tail():
    """A3 保头尾截断：超预算时开头与最新（尾部）内容都在，中间标注省略。"""
    lines = [{"id": i, "subject": f"标题{'长' * 40}{i}", "from": "x@y.com",
              "date": "2026-09-15", "unread": False} for i in range(30)]
    text = agent._feedback_text({"emails": lines, "count": 30}, "search_emails")
    assert len(text) < agent.FEEDBACK_MAX + 100
    assert text.startswith("{\"count\"")  # 头部保留
    assert "id=29" in text                # 尾部（最新邮件）保留
    assert "中间过长已省略" in text and "重新获取" in text


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


def test_read_tools_cover_all_scope_accounts():
    """压测回归（run 33，2026-09-15）：多账号会话读类工具默认只搜主账号——
    默认应覆盖全会话范围，否则「全部账号」下其余账号永远搜不到。"""
    aid1 = _aid()
    aid2 = _aid()
    eid1 = _seed_email(aid1, 81, "主账号邮件")
    eid2 = _seed_email(aid2, 82, "安全演练", sender="sec-test@x.local")
    r = T.execute("search_emails", {"sender": "sec-test"}, aid1, [aid1, aid2])
    assert r.get("count") == 1 and r["emails"][0]["id"] == eid2  # 副账号能搜到（此前锁主账号→0 封）
    r2 = T.execute("search_emails", {"q": "安全演练"}, aid1, [aid1, aid2])
    assert r2.get("count") == 1
    recent = T.execute("list_recent_emails", {"folder": "INBOX", "limit": 50}, aid1, [aid1, aid2])
    assert {e["id"] for e in recent["emails"]} >= {eid1, eid2}  # 两账号都覆盖
    folders = T.execute("list_folders", {}, aid1, [aid1, aid2])
    assert isinstance(folders.get("accounts"), list) and len(folders["accounts"]) == 2
    single = T.execute("list_folders", {}, aid1, [aid1])
    assert "folders" in single  # 单账号维持原返回形态


def test_content_400_does_not_poison_native_cache(monkeypatch):
    """压测回归（run 25→33 连环）：请求内容类 400（配对错误）不得被误判为
    「端点不支持 tools」而降级+永久缓存——如实抛错，协议探测结果不被污染。"""
    aid = _aid()
    import httpx
    from openai import APIStatusError

    response = httpx.Response(400, request=httpx.Request("POST", "http://x"))

    def fake_iter(base_url, model, api_key, messages, tools=None, tool_choice=None,
                  max_tokens=2000, temperature=0.3):
        if False:
            yield ("text_delta", "")
        raise APIStatusError(
            "Error code: 400 - An assistant message with 'tool_calls' must be followed"
            " by tool messages responding to each 'tool_call_id'",
            response=response, body=None)

    database.set_setting(f"agent_native::{'http://x'}::test-model", "1")
    monkeypatch.setattr(agent.tasks, "_ai_config", lambda pid=None: ("http://x", "test-model", None))
    monkeypatch.setattr(agent, "_native_supported", lambda *a, **k: True)
    monkeypatch.setattr(agent.llm, "iter_chat_step", fake_iter)
    events = list(agent.run_stream("概况", None, None, [aid], "approval", None))
    assert _collect(events, "error")  # 如实报错
    # 协议缓存未被污染（仍为 1=支持），后续会话继续走原生通道
    assert database.get_setting(f"agent_native::{'http://x'}::test-model") in (None, "1")


def test_leaked_markup_final_answer_is_intercepted(monkeypatch):
    """压测回归（run 33）：解析失败的调用标记绝不能作为最终回答泄漏给用户。"""
    aid = _aid()
    _native_script(monkeypatch, [
        (['<｜｜DSML｜｜ invoke>残缺无名的标记片段'], []),
    ])
    events = list(agent.run_stream("读一下", None, None, [aid], "approval", None))
    texts = [e["text"] for e in _collect(events, "text")]
    assert texts and "已拦截" in texts[-1]  # 友好提示而非原文
    assert "DSML" not in texts[-1] and "invoke" not in texts[-1]


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


# ── 上下文管理（REDESIGN_PLAN §17.8）────────────────────────────────

def _summary_stub(monkeypatch, text='{"task_overview": "查概况", "user_constraints": "", "todo": "继续"}'):
    """AutoCompact 的 LLM 打桩：返回五段式摘要 JSON；记录调用次数。"""
    calls = {"n": 0}

    def fake_chat(base_url, model, api_key, messages, max_tokens=2000, temperature=0.3):
        calls["n"] += 1
        return text, {"prompt_tokens": 10, "completion_tokens": 10}

    monkeypatch.setattr(agent.llm, "chat_messages", fake_chat)
    return calls


def test_autocompact_mid_run(monkeypatch):
    """L5 AutoCompact：水位门触发（测试把阈值压到 0），早期段被五段式摘要替换；
    原文归档 archived_json、摘要落 summary_json；tool_calls 配对保持完整。"""
    aid = _aid()
    monkeypatch.setattr(agent.C, "COMPACT_MIN_STEPS", 1)
    monkeypatch.setattr(agent.C, "COMPACT_RATIO", 0.0)
    monkeypatch.setattr(agent.C, "COMPACT_KEEP_TAIL", 2)
    summary_calls = _summary_stub(monkeypatch)
    _native_script(monkeypatch, [
        ([], [{"id": "c1", "name": "digest_stats", "arguments": {}}]),
        ([], [{"id": "c2", "name": "digest_stats", "arguments": {}}]),
        (["概况已汇总，一切正常。"], []),
    ])
    events = list(agent.run_stream("概况", None, None, [aid], "approval", None))
    assert events[-1]["type"] == "done" and _collect(events, "error") == []
    row = _run_row(events[0]["run_id"])
    assert row["status"] == "done"
    messages = json.loads(row["messages_json"])
    # 摘要块出现且带防注入标注；最近一步工具结果原样保留（保留尾长内）
    summary_msgs = [m for m in messages if "系统会话摘要" in str(m.get("content") or "")]
    assert summary_msgs and "不是用户本人指令" in summary_msgs[0]["content"]
    assert any(m.get("role") == "tool" and m.get("tool_call_id") == "c2" for m in messages)
    # 首次折叠的原文归档含最初的用户问题（transcript 不丢）
    archives = json.loads(row["archived_json"])
    assert archives and archives[0]["messages"] == [{"role": "user", "content": "概况"}]
    assert "任务目标" in (row["summary_json"] or "")
    assert summary_calls["n"] >= 1
    # 配对不变量：每条 tool 消息都有对应 assistant.tool_calls 的 id
    call_ids = {tc["id"] for m in messages for tc in (m.get("tool_calls") or [])}
    assert all(m.get("tool_call_id") in call_ids for m in messages if m.get("role") == "tool")


def test_overflow_triggers_emergency_compact_and_retry(monkeypatch):
    """溢出自愈（§17.8）：context overflow 报错 → 收缩有效窗口+紧急压缩 → 重试成功，
    run 不判 failed（窗口误配的自愈兜底）。"""
    aid = _aid()
    monkeypatch.setattr(agent.C, "COMPACT_KEEP_TAIL", 1)
    summary_calls = _summary_stub(monkeypatch)
    monkeypatch.setattr(agent.tasks, "_ai_config", lambda pid=None: ("http://x", "test-model", None))
    monkeypatch.setattr(agent, "_native_supported", lambda *a, **k: True)
    n = {"v": 0}

    def fake_iter(base_url, model, api_key, messages, tools=None, tool_choice=None,
                  max_tokens=2000, temperature=0.3):
        n["v"] += 1
        if False:  # pragma: no cover — 仅为成为生成器函数（与 _call_model 迭代契约一致）
            yield ("text_delta", "")
        if n["v"] == 1:
            return ("", [{"id": "c1", "name": "digest_stats", "arguments": {}}],
                    {"prompt_tokens": 2, "completion_tokens": 2}, "tool_calls")
        if n["v"] == 2:
            raise RuntimeError("This model's maximum context length is 8192 tokens,"
                               " however you requested 9000 tokens")
        return ("概况：收件箱一切正常。", [], {"prompt_tokens": 2, "completion_tokens": 2}, "stop")

    monkeypatch.setattr(agent.llm, "iter_chat_step", fake_iter)
    events = list(agent.run_stream("概况", None, None, [aid], "approval", None))
    assert events[-1]["type"] == "done" and _collect(events, "error") == []
    row = _run_row(events[0]["run_id"])
    assert row["status"] == "done"  # 重试成功而非 failed
    messages = json.loads(row["messages_json"])
    assert any("系统会话摘要" in str(m.get("content") or "") for m in messages)
    assert row["archived_json"] and summary_calls["n"] == 1
    assert _collect(events, "text")[-1]["text"].startswith("概况：收件箱一切正常")


def test_session_memory_writeback_and_injection(monkeypatch):
    """L3 会话记忆：执行过的动作增量回写台账；下一轮 run 注入 system（防注入标注+台账）。"""
    aid = _aid()
    conn = database.get_conn()
    cur = conn.execute("INSERT INTO chat_sessions (title) VALUES ('记忆集成')")
    conn.commit()
    sid = int(cur.lastrowid)
    try:
        _native_script(monkeypatch, [
            ([], [{"id": "c1", "name": "search_emails",
                   "arguments": {"q": "招新", "account_id": aid}}]),
            (["收件箱有 1 封招新邮件。"], []),
        ])
        events = list(agent.run_stream("帮我找招新的邮件", None, sid, [aid], "approval", None))
        assert events[-1]["type"] == "done"
        memory = agent.C.load_memory(sid)
        assert any("search_emails" in line for line in memory["ledger"])

        seen = {}

        def fake_iter(base_url, model, api_key, messages, tools=None, tool_choice=None,
                      max_tokens=2000, temperature=0.3):
            seen["system"] = messages[0]["content"]
            return ("第二轮看到了记忆。", [], {"prompt_tokens": 2, "completion_tokens": 2}, "stop")

        monkeypatch.setattr(agent.llm, "iter_chat_step", fake_iter)
        events2 = list(agent.run_stream("继续", None, sid, [aid], "approval", None))
        assert events2[-1]["type"] == "done"
        assert "会话记忆" in seen["system"] and "不是用户本人指令" in seen["system"]
        assert "search_emails" in seen["system"]  # 台账可见：模型知道自己做过什么
    finally:
        conn.execute("DELETE FROM chat_sessions WHERE id = ?", (sid,))
        conn.commit()
