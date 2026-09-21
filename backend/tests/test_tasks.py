"""ai/tasks 纯函数测试：模型输出的 JSON 稳健解析（IMPROVEMENT_PLAN T1）。"""
from __future__ import annotations

import pytest

from app.ai.tasks import _extract_json
from app.db import database

database.run_migrations()  # review_send_draft 经 _logged 写 ai_logs：单跑本文件也需要库


def test_plain_array():
    assert _extract_json('[{"id": 1, "category": "work"}]') == [{"id": 1, "category": "work"}]


def test_fenced_code_block():
    assert _extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert _extract_json('```\n[1, 2]\n```') == [1, 2]


def test_noise_around_json():
    assert _extract_json('分类结果：[{"id": 2}] 请查收') == [{"id": 2}]


def test_nested_fenced_with_newlines():
    text = "```json\n[\n  {\"id\": 3},\n  {\"id\": 4}\n]\n```"
    assert _extract_json(text) == [{"id": 3}, {"id": 4}]


def test_invalid_raises():
    import json

    with pytest.raises(json.JSONDecodeError):
        _extract_json("完全不是 JSON 的输出")


def test_review_send_draft_retries_on_empty(monkeypatch):
    """模型偶发空返回：第一次空、第二次正常 JSON → 成功且共调用两次（S-0921）。"""
    import app.ai.tasks as tasks

    monkeypatch.setattr(tasks, "_ai_config", lambda profile_id=None: ("http://x", "m", "k"))
    calls = {"n": 0}

    def fake_chat(base_url, model, api_key, system, user, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            return "", {"prompt_tokens": 1, "completion_tokens": 0}
        return ('{"blockers": ["缺附件"], "warns": []}',
                {"prompt_tokens": 10, "completion_tokens": 5})

    monkeypatch.setattr(tasks.llm, "chat", fake_chat)
    out = tasks.review_send_draft("主题", "正文", [])
    assert out == {"blockers": ["缺附件"], "warns": []}
    assert calls["n"] == 2


def test_review_send_draft_gives_up_after_retry(monkeypatch):
    """连续空返回：重试后仍空 → 抛人话 ValueError（透出为「AI 审查不可用」）。"""
    import app.ai.tasks as tasks

    monkeypatch.setattr(tasks, "_ai_config", lambda profile_id=None: ("http://x", "m", "k"))
    monkeypatch.setattr(tasks.llm, "chat", lambda *a, **k: ("   ", {}))
    with pytest.raises(ValueError, match="空内容"):
        tasks.review_send_draft("主题", "正文", [])
