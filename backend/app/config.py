"""应用配置与路径。

数据目录遵循 platformdirs 各平台标准位置（Windows: %LOCALAPPDATA%/Nmail），
可用环境变量 NMAIL_DATA_DIR 覆盖。
"""
from __future__ import annotations

import os
import sys
import tomllib
from importlib.metadata import PackageNotFoundError, version as _metadata_version
from pathlib import Path

from platformdirs import user_data_dir

APP_NAME = "Nmail"


def _version_from_pyproject(base: Path) -> str | None:
    """读 pyproject.toml 的 [project].version；文件缺失或解析失败返回 None。"""
    try:
        with (base / "pyproject.toml").open("rb") as fp:
            return tomllib.load(fp)["project"]["version"]
    except (OSError, KeyError, tomllib.TOMLDecodeError):
        return None


def _app_version() -> str:
    """版本号唯一来源是 pyproject.toml（T5）。解析顺序：

    ① 源码直跑/可编辑安装：读仓库根 pyproject.toml，随改动即时生效；
    ② PyInstaller 冻结包：nmail.spec 已把 pyproject.toml 打入随包资源，读解包目录；
    ③ wheel/uvx 安装（site-packages 旁无 pyproject）：读包元数据；
    ④ 兜底 "0.0.0"——以上全失败（异常环境）时的故意异常值，便于暴露问题，不随发版维护。
    """
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", None) or Path(sys.executable).parent)
    else:
        base = Path(__file__).resolve().parents[2]
    if v := _version_from_pyproject(base):
        return v
    try:
        return _metadata_version("nmail-app")
    except PackageNotFoundError:
        return "0.0.0"


APP_VERSION = _app_version()


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
