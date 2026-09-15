"""安装渠道识别（UPDATE_AND_DESKTOP.md §1）：当前实例是怎么装上的。

自更新与桌面集成都按渠道分流：冻结二进制可能来自 Release 直装、Homebrew 或
winget（后两者文件归包管理器管，不能自换身）；非冻结则区分 uvx（临时缓存，
归 uv 管）与 pip（常规虚拟环境，含 uv tool install）。

判定只看运行形态与路径特征，零网络、零写盘；进程内缓存一次。
"""
from __future__ import annotations

import sys
from pathlib import Path

CHANNELS = ("binary", "brew", "winget", "pip", "uvx")

# 各渠道的升级命令（can_self_update=false 时设置页展示）；binary/pip 应用内自更新无此命令
UPGRADE_HINTS: dict[str, str] = {
    "brew": "brew upgrade nathanpenny520/nmail/nmail",
    "winget": "winget upgrade nathanpenny520.Nmail",
    "uvx": "uvx --refresh --from nmail-app nmail",
}


def _segments(p: Path) -> set[str]:
    """路径小写段集合；Windows 风格字符串在 POSIX 上手动按分隔符再切一遍
    （检测总是跑在与安装相同的系统上，这里只为测试与防御性统一）。"""
    return {s.lower() for s in str(p).replace("\\", "/").split("/") if s}


def _detect() -> str:
    if getattr(sys, "frozen", False):
        segs = _segments(Path(sys.executable))
        # Homebrew：Apple Silicon 默认 /opt/homebrew、Intel 与部分 Linux /usr/local/Homebrew、
        # Linux 默认 /home/linuxbrew。按路径段匹配，避免误伤 Linux 上手动装到
        # /usr/local/bin 的直装用户（macOS 上 /usr/local/bin 归 brew 是更常见形态）。
        if segs & {"homebrew", "linuxbrew", "cellar"}:
            return "brew"
        # winget 便携包：…\Microsoft\WinGet\Packages\…
        if "winget" in segs:
            return "winget"
        return "binary"
    # uvx 临时环境：…/uv/archive-v0/<hash>（三平台缓存目录的公共特征段）
    if "archive-v0" in _segments(Path(sys.prefix)):
        return "uvx"
    return "pip"


_cached: str | None = None


def detect_channel() -> str:
    """渠道名（进程内缓存；测试用 _detect 配 monkeypatch 覆盖各形态）。"""
    global _cached
    if _cached is None:
        _cached = _detect()
    return _cached


def can_self_update(channel: str | None = None) -> bool:
    """该渠道是否支持应用内自更新：binary 换身、pip 原地升级；包管理器/uvx 不行。"""
    return (channel or detect_channel()) in ("binary", "pip")


def upgrade_hint(channel: str | None = None) -> str | None:
    """不可自更新渠道的升级命令；可自更新渠道返回 None。"""
    return UPGRADE_HINTS.get(channel or detect_channel())
