"""渠道识别与桌面图标/自更新的纯函数层（UPDATE_AND_DESKTOP.md §1–§3）。

渠道判定 monkeypatch 运行形态与路径；换身/产物生成用临时目录，不触真实系统位置。
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

from app.config import APP_VERSION
from app.core import channel, desktop, update_apply
from app.db.database import run_migrations, set_setting

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

def test_mac_info_plist_and_script(tmp_path):
    plist = desktop._mac_info_plist()
    assert APP_VERSION in plist and "APPL" in plist and "AppIcon" in plist
    script = desktop._mac_script("/path with space/nmail", ["--port", "9"], tmp_path)
    # exec 会替换进程使 LaunchServices 跟丢 bundle（Dock 图标消失）；必须是保活等待式
    assert "exec " not in script
    assert "'/path with space/nmail'" in script and "--port" in script
    assert str(tmp_path / "nmail-app.log") in script
    assert "trap 'kill \"$CHILD\" 2>/dev/null' TERM INT" in script and "wait \"$CHILD\"" in script


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
    assert desktop._launch_target() == (str(script), ["--idle-exit"], "console")
    script.unlink()
    target, args, kind = desktop._launch_target()
    assert target == str(exe) and args[0] == "-c" and args[-1] == "--idle-exit" and kind == "python"


def test_launch_target_uvx_channel(monkeypatch):
    """uvx 渠道图标指向 uvx 命令而非安装时的缓存环境（§2.1）：永远最新、清缓存不死链。"""
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(desktop.channel, "detect_channel", lambda: "uvx")
    monkeypatch.setattr(desktop, "_find_uvx", lambda: "/opt/homebrew/bin/uvx")
    assert desktop._launch_target() == (
        "/opt/homebrew/bin/uvx", ["--from", "nmail-app", "nmail", "--idle-exit"], "uvx")


def test_launch_target_uvx_missing_binary_falls_back(monkeypatch, tmp_path):
    """uvx 找不到（异常 PATH）：退回环境内命令，图标可重装修复，不死锁。"""
    exe = tmp_path / "bin" / "python"
    exe.parent.mkdir()
    (exe.parent / "nmail").write_text("#!/bin/sh\n")
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))
    monkeypatch.setattr(desktop.channel, "detect_channel", lambda: "uvx")
    monkeypatch.setattr(desktop, "_find_uvx", lambda: None)
    target, args, kind = desktop._launch_target()
    assert kind == "console" and target == str(exe.parent / "nmail")
    assert args == ["--idle-exit"]


def test_find_uvx_known_locations(tmp_path, monkeypatch):
    assert desktop._find_uvx() is None or isinstance(desktop._find_uvx(), str)  # 本机 PATH 任一态
    home_uvx = tmp_path / "home" / ".local" / "bin" / "uvx"
    home_uvx.parent.mkdir(parents=True)
    home_uvx.write_text("#!/bin/sh\n")
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.setattr(desktop.shutil, "which", lambda _: None)
    assert desktop._find_uvx() == str(home_uvx)


def test_win_vbs_hidden_launcher():
    vbs = desktop._win_vbs(
        r"C:\Program Files\UV\uvx.exe", ["--from", "nmail-app", "nmail", "--idle-exit"])
    # 引号翻倍防空格路径（内层 "" + 外层 " = 三连引号）；Run 参数 0=隐藏窗口、False=不等待（§2.1）
    assert 'Run """C:\\Program Files\\UV\\uvx.exe"" --from nmail-app nmail --idle-exit", 0, False' in vbs
    assert vbs.endswith("\r\n")


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


# ── update_apply：换身舞步（临时目录模拟冻结二进制）─────────────────────

def _fake_binary(tmp_path: Path, content: str = "OLD") -> Path:
    current = tmp_path / "nmail"
    current.write_text(content)
    current.chmod(0o755)
    return current


def test_swap_in_new_replaces_and_keeps_old(tmp_path, monkeypatch):
    current = _fake_binary(tmp_path)
    new_file = tmp_path / "download.bin"
    new_file.write_text("NEW")
    monkeypatch.setattr(update_apply, "_current_binary", lambda: current)
    update_apply._swap_in_new(new_file)
    assert current.read_text() == "NEW"
    assert (tmp_path / "nmail.old").read_text() == "OLD"
    assert not new_file.exists() and not (tmp_path / "nmail.tmp").exists()
    assert current.stat().st_mode & 0o111  # 可执行位保留


def test_swap_rollback_on_failure(tmp_path, monkeypatch):
    current = _fake_binary(tmp_path)
    monkeypatch.setattr(update_apply, "_current_binary", lambda: current)
    try:
        update_apply._swap_in_new(tmp_path / "missing.bin")  # copyfile 必失败
        assert False, "应抛 OSError"
    except OSError:
        pass
    # 原文件必须完好在原位，否则下次启动无程序可跑
    assert current.exists() and current.read_text() == "OLD"
    assert not (tmp_path / "nmail.old").exists()


def test_finish_pending_swap_applies_newer(tmp_path, monkeypatch):
    current = _fake_binary(tmp_path)
    new_file = update_apply._update_dir() / "nmail.new"
    new_file.write_text("NEW")
    update_apply._set_state(
        phase="downloading", pending_version="999.0.0",
        digest="sha256:" + hashlib.sha256(b"NEW").hexdigest())
    monkeypatch.setattr(update_apply, "_current_binary", lambda: current)
    update_apply.finish_pending_swap()
    assert current.read_text() == "NEW"
    state = update_apply.get_state()
    assert state["phase"] == "ready" and state["staged_version"] == "999.0.0"


def test_finish_pending_swap_discards_stale(tmp_path, monkeypatch):
    new_file = update_apply._update_dir() / "nmail.new"
    new_file.write_text("X")
    update_apply._set_state(phase="downloading", pending_version="0.0.1", digest=None)
    monkeypatch.setattr(update_apply, "_current_binary", lambda: None)
    update_apply.finish_pending_swap()
    assert not new_file.exists() and update_apply.get_state()["phase"] == "idle"


def test_heal_applied_ready(tmp_path, monkeypatch):
    # 已在跑新版（staged 不比当前新）：就绪态自愈归位 idle——读状态与启动收尾两条路径
    update_apply._set_state(phase="ready", progress=100, staged_version=APP_VERSION)
    assert update_apply.get_state()["phase"] == "idle"
    assert update_apply.get_state()["staged_version"] is None
    update_apply._set_state(phase="ready", progress=100, staged_version="v0.0.9")
    update_apply.finish_pending_swap()
    assert update_apply.get_state()["phase"] == "idle"
    # staged 仍比当前新（真的在等重启）：不得误清
    update_apply._set_state(phase="ready", progress=100, staged_version="999.0.0")
    assert update_apply.get_state()["phase"] == "ready"


# ── 自动更新心跳：开关/渠道/新版本三重门控（UPDATE_AND_DESKTOP.md §3.3）────

def test_auto_update_tick_gates(monkeypatch):
    from app.core import update_check as uc

    calls: list[int] = []
    monkeypatch.setattr(update_apply, "start_apply", lambda: calls.append(1))
    monkeypatch.setattr(uc, "get_state", lambda **kw: {"is_newer": True})

    set_setting("update_check_enabled", False)
    set_setting("auto_update_enabled", True)
    update_apply.auto_update_tick()
    assert calls == []  # 检查关闭 → 不动

    set_setting("update_check_enabled", True)
    set_setting("auto_update_enabled", False)
    update_apply.auto_update_tick()
    assert calls == []  # 只检查不自动安装

    set_setting("auto_update_enabled", True)
    monkeypatch.setattr(update_apply.channel, "detect_channel", lambda: "uvx")
    update_apply.auto_update_tick()
    assert calls == []  # 渠道不可自更新 → 不动

    monkeypatch.setattr(update_apply.channel, "detect_channel", lambda: "pip")
    update_apply.auto_update_tick()
    assert calls == [1]  # 全部满足 → 触发

    monkeypatch.setattr(uc, "get_state", lambda **kw: {"is_newer": False})
    update_apply.auto_update_tick()
    assert calls == [1]  # 已是最新 → 不触发
