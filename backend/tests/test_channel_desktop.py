"""渠道识别与桌面图标/自更新的纯函数层（UPDATE_AND_DESKTOP.md §1–§3）。

渠道判定 monkeypatch 运行形态与路径；换身/产物生成用临时目录，不触真实系统位置。
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

from app.config import APP_VERSION
from app.core import channel, desktop, update_apply
from app.db.database import run_migrations

run_migrations()  # 渠道状态读写 KV 表；迁移幂等


# ── channel：渠道判定 ──────────────────────────────────────

def _detect_with(monkeypatch, frozen: bool, executable=None, prefix=None) -> str:
    monkeypatch.setattr(sys, "frozen", frozen, raising=False)
    if executable is not None:
        monkeypatch.setattr(sys, "executable", executable)
    if prefix is not None:
        monkeypatch.setattr(sys, "prefix", prefix)
    return channel._detect()


def test_channel_frozen_plain_is_binary(monkeypatch):
    assert _detect_with(monkeypatch, True, "/Users/x/Downloads/nmail-macos-arm64") == "binary"


def test_channel_frozen_homebrew_is_brew(monkeypatch):
    assert _detect_with(monkeypatch, True, "/opt/homebrew/bin/nmail") == "brew"
    assert _detect_with(monkeypatch, True, "/home/linuxbrew/.linuxbrew/bin/nmail") == "brew"


def test_channel_frozen_winget_is_winget(monkeypatch):
    path = r"C:\Users\x\AppData\Local\Microsoft\WinGet\Packages\Nmail\nmail.exe"
    assert _detect_with(monkeypatch, True, path) == "winget"


def test_channel_uvx_and_pip(monkeypatch):
    assert _detect_with(
        monkeypatch, False, prefix="/Users/x/Library/Caches/uv/archive-v0/ab12cd") == "uvx"
    assert _detect_with(monkeypatch, False, prefix="/Users/x/.venv") == "pip"


def test_channel_capabilities_and_hints():
    assert channel.can_self_update("binary") and channel.can_self_update("pip")
    assert not any(channel.can_self_update(c) for c in ("brew", "winget", "uvx"))
    assert channel.upgrade_hint("uvx") == "uvx --refresh --from nmail-app nmail"
    assert channel.upgrade_hint("binary") is None


# ── desktop：产物内容纯函数 ────────────────────────────────

def test_mac_info_plist_and_exec_line(tmp_path):
    plist = desktop._mac_info_plist()
    assert APP_VERSION in plist and "APPL" in plist and "AppIcon" in plist
    line = desktop._mac_exec_line("/path with space/nmail", ["--port", "9"], tmp_path)
    assert "'/path with space/nmail'" in line and "--port" in line
    assert str(tmp_path / "nmail-app.log") in line


def test_linux_desktop_entry_and_win_wrapper():
    entry = desktop._linux_desktop_entry("/data/bin/nmail.sh")
    assert "Exec=/data/bin/nmail.sh" in entry and "Icon=nmail" in entry and "Terminal=false" in entry
    wrapper = desktop._win_cmd_wrapper(r"C:\Program Files\x\nmail.exe", [])
    assert '"C:\\Program Files\\x\\nmail.exe" %*' in wrapper
    assert "uvx" in desktop._win_cmd_wrapper("uvx.exe", ["--from", "nmail-app", "nmail"])


def test_sh_quoting():
    assert desktop._sh("plain") == "'plain'"
    assert desktop._sh("a'b") == "'a'\\''b'"


def test_launch_target_prefers_console_script(tmp_path, monkeypatch):
    exe = tmp_path / "bin" / "python"
    exe.parent.mkdir()
    script = exe.parent / "nmail"
    script.write_text("#!/bin/sh\n")
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))
    assert desktop._launch_target() == (str(script), [])
    script.unlink()
    target, args = desktop._launch_target()
    assert target == str(exe) and args and args[0] == "-c"


# ── desktop：状态与移除 ────────────────────────────────────

def test_shortcut_status_empty_and_marker_roundtrip():
    status = desktop.get_shortcut_status()
    assert status["installed"] is False and status["paths"] == []
    desktop._write_marker(["/nonexistent/Nmail.app"])
    status = desktop.get_shortcut_status()
    assert status["installed"] is False and status["healthy"] is False  # 路径失效=不健康
    desktop._clear_marker()
    assert desktop._read_marker() is None


# ── update_apply：校验与状态 ───────────────────────────────

def test_verify_digest(tmp_path):
    f = tmp_path / "nmail.new"
    f.write_bytes(b"payload")
    good = "sha256:" + hashlib.sha256(b"payload").hexdigest()
    update_apply._verify_digest(f, good)  # 不抛即通过
    for bad in (None, "sha256:" + "0" * 64, "md5:abc"):
        try:
            update_apply._verify_digest(f, bad)
            assert False, f"应拒绝: {bad}"
        except ValueError:
            pass


def test_apply_state_shape_and_gate(monkeypatch):
    state = update_apply.get_state()
    assert {"channel", "can_self_update", "phase", "progress", "current_version"} <= set(state)
    assert state["current_version"] == APP_VERSION
    # 固定成不可自更新渠道再调 start_apply：收口并给命令提示（否则会真起下载/pip 线程）
    monkeypatch.setattr(channel, "detect_channel", lambda: "uvx")
    result = update_apply.start_apply()
    assert result["ok"] is False and "不支持" in result["error"]
    assert update_apply.get_state()["phase"] == "idle"


def test_platform_asset_mapping():
    assert update_apply._platform_key() in (
        None, ("windows", "amd64"), ("macos", "arm64"), ("linux", "amd64"))
