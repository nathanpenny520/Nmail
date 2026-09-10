"""本地密钥文件读写。

密钥保存在数据目录的 secrets.json。跨平台决策见 docs/PRODUCT_PLAN.md §3.5：
不使用 OS keyring / DPAPI 等系统独有接口；远期可选主密码加密（纯跨平台算法）。
"""
from __future__ import annotations

import json
import os
import stat

from app.config import get_secrets_path


def _read_all() -> dict[str, str]:
    path = get_secrets_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _write_all(data: dict[str, str]) -> None:
    path = get_secrets_path()
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)  # POSIX 下收紧权限，Windows 忽略
    except OSError:
        pass


def get_secret(key: str) -> str | None:
    return _read_all().get(key)


def set_secret(key: str, value: str | None) -> None:
    """value 为空或 None 时删除该项。"""
    data = _read_all()
    if value:
        data[key] = value
    else:
        data.pop(key, None)
    _write_all(data)


def has_secret(key: str) -> bool:
    return bool(_read_all().get(key))
