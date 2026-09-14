"""nmail-cli 测试夹具：复用后端一次性临时数据目录，Client 走 ASGI TestClient 传输。"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))
sys.path.insert(0, str(REPO_ROOT / "nmail-cli"))

os.environ.setdefault("NMAIL_DATA_DIR", tempfile.mkdtemp(prefix="nmail-cli-pytest-"))
