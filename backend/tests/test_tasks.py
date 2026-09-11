"""ai/tasks 纯函数测试：模型输出的 JSON 稳健解析（IMPROVEMENT_PLAN T1）。"""
from __future__ import annotations

import pytest

from app.ai.tasks import _extract_json


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
    with pytest.raises(Exception):
        _extract_json("完全不是 JSON 的输出")
