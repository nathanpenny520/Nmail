#!/usr/bin/env python3
"""Nmail 一键启动（源码开发入口）。

用法:
    python run.py [--port 8720] [--no-browser]

启动逻辑在 app.cli（与 PyPI 安装脚本、冻结包共用），此处仅注入源码路径。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.cli import main  # noqa: E402  — 需在路径注入后导入

if __name__ == "__main__":
    main()
