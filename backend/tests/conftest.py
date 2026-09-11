"""pytest 共享夹具：把数据目录指到一次性临时目录，绝不触碰真实用户数据。

必须在任何 app 模块导入前设置环境变量（get_data_dir/get_db_path 按调用时读）。
"""
from __future__ import annotations

import os
import tempfile

os.environ.setdefault("NMAIL_DATA_DIR", tempfile.mkdtemp(prefix="nmail-pytest-"))
