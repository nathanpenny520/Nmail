"""应用配置与路径。

数据目录遵循 platformdirs 各平台标准位置（Windows: %LOCALAPPDATA%/Nmail），
可用环境变量 NMAIL_DATA_DIR 覆盖。
"""
from __future__ import annotations

import os
from pathlib import Path

from platformdirs import user_data_dir

APP_NAME = "Nmail"
APP_VERSION = "0.1.0"


def get_data_dir() -> Path:
    override = os.environ.get("NMAIL_DATA_DIR")
    base = Path(override) if override else Path(user_data_dir(APP_NAME, appauthor=False))
    base.mkdir(parents=True, exist_ok=True)
    return base


def get_db_path() -> Path:
    return get_data_dir() / "nmail.db"


def get_secrets_path() -> Path:
    return get_data_dir() / "secrets.json"
