"""应用配置与路径。

数据目录遵循 platformdirs 各平台标准位置（Windows: %LOCALAPPDATA%/Nmail），
可用环境变量 NMAIL_DATA_DIR 覆盖。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from platformdirs import user_data_dir

APP_NAME = "Nmail"

# 版本号单一来源是 pyproject.toml（T5）：已安装（wheel/uvx/editable）时读包元数据；
# 源码直跑或冻结环境无元数据时回退常量——改版本时只需改 pyproject，此处随动。
try:
    from importlib.metadata import PackageNotFoundError, version

    APP_VERSION = version("nmail-app")
except PackageNotFoundError:
    APP_VERSION = "0.2.0"


def get_data_dir() -> Path:
    override = os.environ.get("NMAIL_DATA_DIR")
    base = Path(override) if override else Path(user_data_dir(APP_NAME, appauthor=False))
    base.mkdir(parents=True, exist_ok=True)
    return base


def get_db_path() -> Path:
    return get_data_dir() / "nmail.db"


def get_secrets_path() -> Path:
    return get_data_dir() / "secrets.json"


def _find_dist_dir() -> Path | None:
    """前端静态目录按运行形态解析：wheel 安装（app/static）→ PyInstaller 冻结资源 → 源码开发（frontend/dist）。"""
    here = Path(__file__).resolve().parent  # .../app（源码或 site-packages）
    candidates: list[Path] = []
    if getattr(sys, "frozen", False):  # PyInstaller 单文件：只用随包资源
        base = Path(getattr(sys, "_MEIPASS", None) or Path(sys.executable).parent)
        candidates.append(base / "app" / "static")
    else:
        # 源码开发：frontend/dist 优先（跟随每次构建），app/static 是打包快照，
        # 两者并存时若优先 static 会让开发者一直看到旧界面
        candidates.append(here.parents[1] / "frontend" / "dist")
        candidates.append(here / "static")
    for p in candidates:
        if p.is_dir():
            return p
    return None


# 前端构建产物目录；None = 未构建（API 照常服务，SPA 不可用）。
# 放 config 而非 main：api 层根路径 OAuth 回调需读取它，从 main 导入会循环。
DIST_DIR = _find_dist_dir()
