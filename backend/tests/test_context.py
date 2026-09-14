"""上下文管理单测（REDESIGN_PLAN §17.8）：估算器、折叠边界、确定性纪要、
五段式摘要解析、会话记忆读写、窗口解析与溢出识别。全离线，不出网。"""
from __future__ import annotations

import json

from app.ai import context as C
from app.db import database

database.run_migrations()


def test_estimate_tokens_cjk_vs_ascii():
    assert C.estimate_tokens("") == 0
    assert C.estimate_tokens("abcdef") == 2  # 6 ASCII ≈ 6/4 + 1
    assert C.estimate_tokens("六四个汉字正好") == 8  # 7 CJK + 1 开销
    mixed = C.estimate_tokens("你好world")
    assert 3 <= mixed <= 5  # 2 CJK + 5 ASCII/4


def test_resolve_window_default_and_custom():
    from app.ai import profiles as P

    original = P.list_profiles()
    original_active = P.get_active_id()
    try:
        P.save_profiles([
            {"id": "ctxw1", "name": "小窗", "base_url": "http://x", "model": "m",
             "context_window": 32768},
            {"id": "ctxw0", "name": "未指定", "base_url": "http://y", "model": "m"},
        ])
        P.set_active_id("ctxw0")
        assert C.resolve_window("ctxw1") == 32768  # 档案指定 → 按实际窗口（防压缩失效）
        assert C.resolve_window(None) == C.DEFAULT_CONTEXT_WINDOW  # 激活档案未指定 → 默认 1M
        P.save_profiles([p for p in P.list_profiles() if p["id"] == "ctxw1"])
        P.set_active_id("ctxw1")
        assert C.resolve_window(None) == 32768  # 激活切到指定档案 → 生效
    finally:
        P.save_profiles(original)
        P.set_active_id(original_active)


def test_is_overflow_error():
    assert C.is_overflow_error("This model's maximum context length is 8192 tokens")
    assert C.is_overflow_error("请 reduce the length of the prompt")
    assert not C.is_overflow_error("connection timeout")


def _exchange(i: int) -> list[dict]:
    return [{"role": "assistant", "content": "", "tool_calls": [{"id": f"c{i}", "type": "function",
             "function": {"name": "search_emails", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": f"c{i}", "content": '{"count": 1}'}]


def test_boundary_index_pairs_and_tail():
    msgs = [{"role": "system"}, {"role": "user", "content": "q"},
            *(_exchange(1) + _exchange(2) + _exchange(3))]
    # 保留 2 条尾巴：最大安全边界 = 第 2 组 assistant 位置（折叠整组保配对）
    b = C.boundary_index(msgs, 2)
    assert msgs[b]["role"] == "assistant"
    tail = msgs[b:]
    assert tail[0].get("tool_calls") and tail[1].get("role") == "tool"  # 尾部自身配对完整
    assert len(tail) >= 2
    assert C.boundary_index([{"role": "system"}, {"role": "user"}], 1) is None  # 没什么可折


def test_deterministic_digest_content():
    msgs = [{"role": "system"},
            {"role": "user", "content": "帮我找招新的邮件"},
            *_exchange(1),
            {"role": "assistant", "content": "找到了 1 封。"}]
    digest = C.deterministic_digest(msgs, len(msgs))
    assert "帮我找招新的邮件" in digest
    assert "search_emails" in digest
    assert "找到了 1 封" in digest


def test_compact_tool_line_native_and_json_mode():
    # 原生模式：从配对 assistant.tool_calls 反查工具名 + 关键标量
    hint = "h" * 120
    msgs = [{"role": "system"},
            {"role": "assistant", "content": "", "tool_calls": [
                {"id": "c1", "type": "function",
                 "function": {"name": "search_emails", "arguments": '{"q": "招新"}'}}]},
            {"role": "tool", "tool_call_id": "c1",
             "content": json.dumps({"count": 5, "hint": hint}, ensure_ascii=False)}]
    line = C.compact_tool_line(msgs, 2)
    assert line.startswith("search_emails：")
    assert "count=5" in line and "早期明细已省略" in line
    # JSON 降级模式：直接取「工具结果：」摘要前缀
    json_msg = {"role": "user", "content": "工具结果：搜索到 5 封；数据：{...原始...}"}
    line2 = C.compact_tool_line([json_msg], 0)
    assert "搜索到 5 封" in line2 and "原始" not in line2


def test_parse_summary_and_render():
    good = '{"task_overview": "清理促销邮件", "user_constraints": "不要动工作邮件", "todo": ""}'
    summary = C.parse_summary("前言杂讯 " + good + " 后记")
    assert summary and summary["task_overview"] == "清理促销邮件"
    assert summary["todo"] == ""
    assert C.parse_summary("完全不是 JSON") is None

    block = C.render_summary(summary)
    assert "系统会话摘要" in block and "不是用户本人指令" in block  # 防注入标注必备
    assert "清理促销邮件" in block and "用户要求：不要动工作邮件" in block
    # L4 兜底：纪要块同样带防注入标注
    assert "不是用户本人指令" in C.digest_block("用户：q\n  → search_emails({})")


def test_memory_ledger_brief_and_block(tmp_path):
    from app.db import database as db

    cur = db.get_conn().execute("INSERT INTO chat_sessions (title) VALUES ('记忆测试')")
    db.get_conn().commit()
    sid = int(cur.lastrowid)
    try:
        assert C.load_memory(sid) == {"brief": "", "ledger": []}
        for i in range(C.MEMORY_LEDGER_MAX + 5):  # 超上限只留最近 N 条
            C.append_ledger(sid, f"search_emails：找到 {i} 封")
        C.set_brief(sid, "任务目标：清理促销邮件")
        memory = C.load_memory(sid)
        assert len(memory["ledger"]) == C.MEMORY_LEDGER_MAX
        assert memory["ledger"][-1].endswith("44 封")  # 旧的被挤出
        assert memory["brief"] == "任务目标：清理促销邮件"

        block = C.memory_block(memory)
        assert "会话记忆" in block and "不是用户本人指令" in block  # 防注入标注必备
        assert "任务目标：清理促销邮件" in block and "search_emails" in block
        assert len(block) <= C.MEMORY_BLOCK_MAX + 10
    finally:
        db.get_conn().execute("DELETE FROM chat_sessions WHERE id = ?", (sid,))
        db.get_conn().commit()


def test_feedback_budget_per_tool():
    from app.ai import agent

    long_body = {"body": "x" * 8000}
    assert len(agent._feedback_text(long_body, "read_email")) < 4200
    assert len(agent._feedback_text(long_body)) < 1300  # 其余工具维持 1200
    listing = {"emails": [{"id": 7, "subject": "标题", "from": "a@b.c", "date": "2026-09-14",
                           "unread": True}], "count": 1}
    text = json.loads(agent._feedback_text(listing, "search_emails"))  # 未超预算原样紧凑化
    assert text["emails"][0].startswith("id=7") and text["count"] == 1  # 列表行格式保留 id
