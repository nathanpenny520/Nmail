"""版本唯一来源校验：app / nmail-cli / skill 必须同一条版本线。

scripts/sync_version.py 负责维护（release.sh 发版时自动调用）；本测试兜底——
任何一处被手改漂移，CI 直接红。背景：v0.4.0 及之前 nmail-cli 独立版本
（0.1.0），与服务端版本（0.4.0）互不相关，导致 CLI 版本协商 _notice.update
永久误报；2026-09-15 起统一为同一条版本线。
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _version_of(rel: str, pattern: str) -> str:
    text = (ROOT / rel).read_text(encoding="utf-8")
    m = re.search(pattern, text, re.M)
    assert m, f"{rel} 里找不到版本行（pattern={pattern}）"
    return m.group(1)


def test_四处版本一致():
    app_v = _version_of("pyproject.toml", r'^version = "([0-9][0-9.]*)"')
    assert _version_of("nmail-cli/pyproject.toml", r'^version = "([0-9][0-9.]*)"') == app_v
    assert _version_of("nmail-cli/nmail_cli/__init__.py",
                       r'^__version__ = "([0-9][0-9.]*)"') == app_v
    assert _version_of("skills/SKILL.md", r"^version: ([0-9][0-9.]*)") == app_v
