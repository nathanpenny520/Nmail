"""桌面图标一键安装（UPDATE_AND_DESKTOP.md §2）。

nmail 命令本身已会「起服务+开浏览器」，图标只需包装这一件事。三平台产物
全部只写用户目录：Windows 桌面+开始菜单 .lnk、macOS ~/Applications/Nmail.app、
Linux .desktop + hicolor 图标。安装状态记在数据目录 desktop-shortcut.json，
路径失效时状态卡给出「重新安装」。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from app.config import APP_VERSION, get_data_dir
from app.core import channel

_MARKER = "desktop-shortcut.json"


# ── 图标资产与启动命令 ──────────────────────────────────────────────────

def _assets_dir() -> Path:
    """随包图标（backend/app/assets，冻结包由 nmail.spec datas 打入 _MEIPASS）。"""
    return Path(__file__).resolve().parents[1] / "assets"


def _launch_target() -> tuple[str, list[str]]:
    """图标最终运行的 (可执行文件, 参数)。优先用同环境的 console script
    （pip venv 与 uvx 临时环境都有），源码直跑退回解释器内联调用。"""
    if not getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).parent
        script = exe_dir / ("nmail.exe" if os.name == "nt" else "nmail")
        if script.is_file():
            return str(script), []
        # 源码直跑：启动器 cwd 不可控，把 backend 目录（app 包父目录）显式注入 sys.path
        backend_root = Path(__file__).resolve().parents[2]
        code = f"import sys; sys.path.insert(0, {str(backend_root)!r}); from app.cli import main; main()"
        return sys.executable, ["-c", code]
    return sys.executable, []


def _sh(s: str) -> str:
    """POSIX shell 单引号转义。"""
    return "'" + s.replace("'", "'\\''") + "'"


def _ps(s: str) -> str:
    """PowerShell 单引号字符串转义（内部单引号翻倍）。"""
    return s.replace("'", "''")


# ── 各平台产物内容（纯函数，便于测试）───────────────────────────────────

def _mac_script(target: str, args: list[str], data_dir: Path) -> str:
    """bundle 启动脚本：服务以子进程运行、本脚本存活等待——若用 exec 把自身
    替换成服务进程，LaunchServices 会跟丢 bundle，Dock 图标立刻消失（2026-09-15
    用户实测反馈）。退出信号转发给服务子进程，Dock 右键 Quit 即完整停服。"""
    log = data_dir / "nmail-app.log"
    quoted = " ".join([_sh(target), *(_sh(a) for a in args)])
    return (
        "#!/bin/bash\n"
        f"{quoted} \"$@\" >> {_sh(str(log))} 2>&1 &\n"
        "CHILD=$!\n"
        "trap 'kill \"$CHILD\" 2>/dev/null' TERM INT\n"
        "wait \"$CHILD\"\n"
    )


def _mac_info_plist() -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key><string>Nmail</string>
    <key>CFBundleDisplayName</key><string>Nmail</string>
    <key>CFBundleIdentifier</key><string>com.whizzzest.nmail</string>
    <key>CFBundleVersion</key><string>{APP_VERSION}</string>
    <key>CFBundleShortVersionString</key><string>{APP_VERSION}</string>
    <key>CFBundleExecutable</key><string>nmail</string>
    <key>CFBundleIconFile</key><string>AppIcon</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>CFBundleInfoDictionaryVersion</key><string>6.0</string>
    <key>LSMinimumSystemVersion</key><string>11.0</string>
    <key>NSHighResolutionCapable</key><true/>
    <key>LSApplicationCategoryType</key><string>public.app-category.productivity</string>
</dict>
</plist>
"""


def _linux_desktop_entry(exec_path: str) -> str:
    return f"""[Desktop Entry]
Type=Application
Name=Nmail
Comment=AI 驱动的本地聚合邮箱客户端
Exec={exec_path}
Icon=nmail
Terminal=false
Categories=Network;Email;
StartupWMClass=nmail
"""


def _win_cmd_wrapper(target: str, args: list[str]) -> str:
    cmd = '"' + target + '"'
    if args:
        cmd += " " + " ".join(args)
    return f"@echo off\r\n{cmd} %*\r\n"


# ── 状态记录 ────────────────────────────────────────────────────────────

def _marker_path() -> Path:
    return get_data_dir() / _MARKER


def _read_marker() -> dict | None:
    try:
        data = json.loads(_marker_path().read_text("utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def _write_marker(paths: list[str]) -> None:
    _marker_path().write_text(
        json.dumps(
            {"installed_at": datetime.now(UTC).isoformat(timespec="seconds"),
             "channel": channel.detect_channel(), "paths": paths},
            ensure_ascii=False),
        "utf-8",
    )


def _clear_marker() -> None:
    _marker_path().unlink(missing_ok=True)


# ── 对外三动作 ──────────────────────────────────────────────────────────

def get_shortcut_status() -> dict:
    m = _read_marker()
    paths = [p for p in (m or {}).get("paths", []) if p]
    healthy = bool(paths) and all(Path(p).exists() for p in paths)
    return {
        "installed": bool(m) and healthy,
        "healthy": healthy,
        "paths": paths,
        "channel": channel.detect_channel(),
        "platform": sys.platform,
        "installed_at": (m or {}).get("installed_at"),
    }


def install_shortcut() -> dict:
    try:
        if sys.platform == "win32":
            paths = _install_windows()
        elif sys.platform == "darwin":
            paths = _install_macos()
        else:
            paths = _install_linux()
    except Exception as exc:  # noqa: BLE001 — 任何平台差异都折成错误信息返回给设置页
        return {"ok": False, "paths": [], "error": f"{type(exc).__name__}: {exc}"}
    _write_marker(paths)
    return {"ok": True, "paths": paths, "error": None}


def remove_shortcut() -> dict:
    removed: list[str] = []
    for p in (_read_marker() or {}).get("paths", []):
        path = Path(p)
        try:
            if path.is_dir() and path.name.endswith(".app"):
                shutil.rmtree(path, ignore_errors=True)
            else:
                path.unlink(missing_ok=True)
            removed.append(p)
        except OSError:
            pass
    _remove_defaults()  # 状态文件丢失时的兜底清扫
    _clear_marker()
    return {"ok": True, "paths": removed, "error": None}


# ── 平台实现 ────────────────────────────────────────────────────────────

def _install_windows() -> list[str]:
    data = get_data_dir()
    bin_dir = data / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    target, args = _launch_target()
    if getattr(sys, "frozen", False):
        icon, wrapper = sys.executable, None  # exe 已内嵌图标，直接指它
    else:
        icon = bin_dir / "nmail.ico"
        shutil.copyfile(_assets_dir() / "nmail.ico", icon)
        # .lnk 直指 pythonw：控制台脚本/.cmd 都会闪黑框（§6）。args==[] 即
        # console-script 模式，包必已装进本解释器环境，pythonw -m app.cli 等价；
        # pythonw 缺失（老发行版/极端环境）退回 .cmd 包装
        pythonw = Path(sys.executable).with_name("pythonw.exe")
        if args == [] and pythonw.is_file():
            target, args, wrapper = str(pythonw), ["-m", "app.cli"], None
        else:
            wrapper = bin_dir / "nmail.cmd"
            wrapper.write_text(_win_cmd_wrapper(target, args), "utf-8")
            target = str(wrapper)
    script = "\n".join([
        "$ErrorActionPreference = 'Stop'",
        "$ws = New-Object -ComObject WScript.Shell",
        "$desktop = [Environment]::GetFolderPath('Desktop')",
        "$programs = [Environment]::GetFolderPath('Programs')",
        "$created = @()",
        "foreach ($dir in @($desktop, $programs)) {",
        "  $lnkPath = Join-Path $dir 'Nmail.lnk'",
        "  $lnk = $ws.CreateShortcut($lnkPath)",
        f"  $lnk.TargetPath = '{_ps(target)}'",
        "  $lnk.Arguments = ''",
        f"  $lnk.WorkingDirectory = '{_ps(str(data))}'",
        f"  $lnk.IconLocation = '{_ps(str(icon))},0'",
        "  $lnk.WindowStyle = 7",  # 最小化：控制台仍在任务栏可看日志，不糊脸
        "  $lnk.Save()",
        "  $created += $lnkPath",
        "}",
        "$created -join [Environment]::NewLine",
    ])
    return _run_powershell(script)


def _run_powershell(script: str) -> list[str]:
    with tempfile.NamedTemporaryFile("w", suffix=".ps1", delete=False, encoding="utf-8-sig") as fp:
        fp.write(script)
        ps1 = fp.name
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ps1],
            capture_output=True, text=True, timeout=30,
            # 窗口化平台（§6）从设置页安装图标时 spawn powershell 不得闪控制台
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
    finally:
        Path(ps1).unlink(missing_ok=True)
    if out.returncode != 0:
        raise RuntimeError((out.stderr or out.stdout).strip()[:300] or "PowerShell 执行失败")
    paths = [line.strip() for line in out.stdout.splitlines() if line.strip().endswith(".lnk")]
    if not paths:
        raise RuntimeError(f"快捷方式创建结果异常：{out.stdout.strip()[:200]}")
    return paths


def _install_macos() -> list[str]:
    data = get_data_dir()
    # 用户期望标准位置 /Applications（2026-09-15 反馈）；无写权限（非 admin）回退用户目录
    bundle = Path("/Applications/Nmail.app")
    try:
        bundle.parent.mkdir(parents=True, exist_ok=True)  # 探测写权限
    except OSError:
        bundle = Path.home() / "Applications" / "Nmail.app"
    contents = bundle / "Contents"
    (contents / "MacOS").mkdir(parents=True, exist_ok=True)
    (contents / "Resources").mkdir(parents=True, exist_ok=True)
    target, args = _launch_target()
    # 优先用编译好的 ObjC 存根做「应用面」（LaunchServices 只为 GUI 进程注册应用，
    # 纯脚本 bundle 无 Dock 图标，2026-09-15 用户实测）；无存根资产则退回脚本形态
    stub = _assets_dir() / "nmail-stub"
    if stub.is_file():
        shutil.copyfile(stub, contents / "MacOS" / "nmail")
        (contents / "MacOS" / "nmail").chmod(0o755)
        server = contents / "MacOS" / "server"
        server.write_text(_mac_script(target, args, data))
        server.chmod(0o755)
    else:
        (contents / "MacOS" / "nmail").write_text(_mac_script(target, args, data))
        (contents / "MacOS" / "nmail").chmod(0o755)
    (contents / "PkgInfo").write_text("APPL????")
    (contents / "Info.plist").write_text(_mac_info_plist())
    shutil.copyfile(_assets_dir() / "nmail.icns", contents / "Resources" / "AppIcon.icns")
    # 尽力让 LaunchServices 立刻索引到（失败不阻塞——Finder 一般也能自己发现）
    lsregister = ("/System/Library/Frameworks/CoreServices.framework/Frameworks/"
                  "LaunchServices.framework/Support/lsregister")
    subprocess.run([lsregister, "-f", str(bundle)], capture_output=True, timeout=15, check=False)
    return [str(bundle)]


def _install_linux() -> list[str]:
    data = get_data_dir()
    bin_dir = data / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    target, args = _launch_target()
    wrapper = bin_dir / "nmail.sh"
    quoted = " ".join([_sh(target), *(_sh(a) for a in args)])
    # Linux 无 Dock 常驻诉求：exec 原地替换最省一档进程
    wrapper.write_text(f"#!/bin/bash\nexec {quoted} \"$@\" >> {_sh(str(data / 'nmail-app.log'))} 2>&1\n")
    wrapper.chmod(0o755)
    icon = Path.home() / ".local/share/icons/hicolor/512x512/apps/nmail.png"
    icon.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(_assets_dir() / "nmail-512.png", icon)
    entry = Path.home() / ".local/share/applications/nmail.desktop"
    entry.parent.mkdir(parents=True, exist_ok=True)
    entry.write_text(_linux_desktop_entry(str(wrapper)))
    return [str(entry), str(icon), str(wrapper)]


def _remove_defaults() -> None:
    """无状态记录时按平台默认位置兜底清扫（尽力而为，逐个忽略失败）。"""
    try:
        if sys.platform == "win32":
            targets = ["[Environment]::GetFolderPath('Desktop') + '\\Nmail.lnk'",
                       "[Environment]::GetFolderPath('Programs') + '\\Nmail.lnk'"]
            script = "\n".join(
                [f"if (Test-Path {t}) {{ Remove-Item {t} -Force }}"] for t in targets)
            subprocess.run(["powershell", "-NoProfile", "-Command", script],
                           capture_output=True, timeout=30, check=False,
                           creationflags=subprocess.CREATE_NO_WINDOW
                           if sys.platform == "win32" else 0)
        else:
            if sys.platform == "darwin":
                shutil.rmtree(Path.home() / "Applications" / "Nmail.app", ignore_errors=True)
            else:
                entry = Path.home() / ".local/share/applications/nmail.desktop"
                entry.unlink(missing_ok=True)
                (Path.home() / ".local/share/icons/hicolor/512x512/apps/nmail.png").unlink(
                    missing_ok=True)
    except (OSError, subprocess.SubprocessError):
        pass
