"""应用内更新执行（UPDATE_AND_DESKTOP.md §3）：下载→校验→换身→重启。

渠道语义（core/channel.py）：binary 完整自更新；pip 原地 ``pip install --upgrade``；
brew/winget/uvx 不自更新（升级命令见 channel.upgrade_hint）。

换身依赖三平台通用事实：运行中的可执行文件可以 rename、不能删除/覆写——
当前二进制 rename 为 *.old 后原路径腾空，新文件原子落位；旧进程跑旧 inode
照常服务，下次启动自然运行新版。下载中途退出留下的半程更新由 cli 启动早段
finish_pending_swap 收尾，保证「下次打开一定是新版」。
"""
from __future__ import annotations

import hashlib
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path

import httpx

from app.config import APP_VERSION, get_data_dir
from app.core import channel
from app.core.update_check import RELEASES_API, _is_newer, _parse_version, notify_ready
from app.db.database import get_setting, set_setting

_STATE_KEY = "update_apply_state"
_OLD_SUFFIX = ".old"

_HTTP_TIMEOUT = httpx.Timeout(15.0, connect=8.0)
_STREAM_TIMEOUT = httpx.Timeout(30.0, connect=8.0)

# Release 资产名按平台映射（与 release.yml matrix、winget/tap 口径一致）
_ASSET_BY_PLATFORM = {
    ("windows", "amd64"): "nmail-windows-x64.exe",
    ("macos", "arm64"): "nmail-macos-arm64",
    ("linux", "amd64"): "nmail-linux-x64",
}


def _platform_key() -> tuple[str, str] | None:
    system = {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")
    machine = platform.machine().lower()
    arch = "arm64" if machine in ("arm64", "aarch64") else "amd64"
    return (system, arch) if (system, arch) in _ASSET_BY_PLATFORM else None


def _update_dir():
    d = get_data_dir() / "update"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _read_state() -> dict:
    state = get_setting(_STATE_KEY, {}) or {}
    return state if isinstance(state, dict) else {}


def _write_state(state: dict) -> None:
    state["updated_at"] = datetime.now(UTC).isoformat(timespec="seconds")
    set_setting(_STATE_KEY, state)


def _set_state(**fields) -> None:
    state = _read_state()
    state.update(fields)
    _write_state(state)


def get_state() -> dict:
    ch = channel.detect_channel()
    state = _read_state()
    return {
        "channel": ch,
        "can_self_update": channel.can_self_update(ch),
        "upgrade_hint": channel.upgrade_hint(ch),
        "phase": state.get("phase", "idle"),
        "progress": state.get("progress", 0),
        "error": state.get("error"),
        "staged_version": state.get("staged_version"),
        "current_version": APP_VERSION,
        "updated_at": state.get("updated_at"),
    }


# ── 换身与收尾 ──────────────────────────────────────────────────────────

def _current_binary() -> Path | None:
    """冻结二进制自身路径；非冻结（pip）无换身对象返回 None。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve()
    return None


def _swap_in_new(new_file: Path) -> None:
    """把下载好的新二进制换到当前运行路径（rename 舞步，见模块 docstring）。"""
    current = _current_binary()
    if current is None:
        raise RuntimeError("非冻结环境不应走二进制换身")
    old = current.with_name(current.name + _OLD_SUFFIX)
    with suppress(OSError):
        old.unlink()  # 上上次的残留（进程已换，此时可删；被锁则下次再清）
    os.rename(current, old)  # 运行中允许 rename；原路径腾空
    try:
        tmp = current.with_name(current.name + ".tmp")
        shutil.copyfile(new_file, tmp)
        shutil.copymode(old, tmp)  # 保住可执行位
        os.replace(tmp, current)  # 同目录原子落位
    except OSError:
        # copy 失败必须把旧文件换回去，否则下次启动无程序可跑
        with suppress(OSError):
            tmp.unlink()
        with suppress(OSError):
            os.rename(old, current)
        raise
    with suppress(OSError):
        new_file.unlink()


def finish_pending_swap() -> None:
    """启动早段收尾（cli.main 调用，必须零阻塞零抛错）：
    ① 清理上次重启遗留的 *.old；② 上次下载中途退出的 nmail.new 校验后完成换身
    ——对应版本仍比当前新才换，否则删除归位。

    全函数整体兜底：首次启动时 KV 表尚未建（迁移在 FastAPI lifespan 才跑），
    读状态会 OperationalError——收尾失败绝不阻塞服务启动。"""
    try:
        current = _current_binary()
        if current is not None:
            old = current.with_name(current.name + _OLD_SUFFIX)
            if old.exists():
                with suppress(OSError):
                    old.unlink()
        state = _read_state()
        if state.get("phase") not in ("downloading", "verifying", "staging"):
            return
        new_file = _update_dir() / "nmail.new"
        pending_version = state.get("pending_version") or ""
        if (new_file.is_file() and _parse_version(pending_version)
                and _is_newer(pending_version, APP_VERSION)):
            try:
                _verify_digest(new_file, state.get("digest"))
                _swap_in_new(new_file)
                _set_state(phase="ready", progress=100, staged_version=pending_version, error=None)
                notify_ready(pending_version)
            except Exception:  # noqa: BLE001 — 收尾失败不阻塞启动，清理残局即可
                with suppress(OSError):
                    new_file.unlink()
                _set_state(phase="failed", error="启动时完成换身失败，已还原")
        else:
            with suppress(OSError):
                new_file.unlink()
            _set_state(phase="idle")
    except Exception:  # noqa: BLE001 — 首启无表/任何异常都不影响正常启动
        pass


def _verify_digest(path: Path, digest: str | None) -> None:
    if not digest or not digest.startswith("sha256:"):
        raise ValueError("缺少校验和，拒绝落位")
    h = hashlib.sha256()
    with path.open("rb") as fp:
        for chunk in iter(lambda: fp.read(1 << 20), b""):
            h.update(chunk)
    if h.hexdigest() != digest.split(":", 1)[1].strip().lower():
        raise ValueError("SHA256 校验不匹配")


# ── 后台执行：下载换身 / pip 升级 ────────────────────────────────────────

def start_apply() -> dict:
    """启动后台更新任务（API POST 入口）。进行中则幂等返回。"""
    ch = channel.detect_channel()
    if not channel.can_self_update(ch):
        hint = channel.upgrade_hint(ch)
        return {"ok": False, "error": f"渠道 {ch} 不支持应用内更新" + (f"，请执行: {hint}" if hint else "")}
    if _read_state().get("phase") in ("downloading", "verifying", "staging", "pip_upgrading"):
        return {"ok": True, "already_running": True}
    worker = _pip_upgrade if ch == "pip" else _download_and_swap
    _set_state(phase="downloading" if ch == "binary" else "pip_upgrading",
               progress=0, error=None, staged_version=None)
    threading.Thread(target=worker, daemon=True).start()
    return {"ok": True}


def _latest_release() -> dict | None:
    try:
        resp = httpx.get(
            RELEASES_API, timeout=_HTTP_TIMEOUT,
            headers={"User-Agent": f"Nmail/{APP_VERSION}", "Accept": "application/vnd.github+json"},
        )
        return resp.json() if resp.status_code == 200 else None
    except httpx.HTTPError:
        return None


def _download_and_swap() -> None:
    release = _latest_release()
    if not release:
        _set_state(phase="failed", error="无法获取 Release 信息（网络）")
        return
    tag = (release.get("tag_name") or "").strip()
    if not _is_newer(tag, APP_VERSION):
        _set_state(phase="idle")  # 已是最新（或版本号不可解析）
        return
    assets = {a.get("name"): a for a in release.get("assets", []) if isinstance(a, dict)}
    key = _platform_key()
    asset = assets.get(_ASSET_BY_PLATFORM.get(key, "")) if key else None
    if not asset or not asset.get("browser_download_url"):
        _set_state(phase="failed", error=f"Release 资产缺失（{_ASSET_BY_PLATFORM.get(key)}）")
        return
    digest = asset.get("digest")
    # pending_version/digest 先落状态再下载：中途退出后 finish_pending_swap 才能凭它收尾
    _set_state(pending_version=tag, digest=digest)
    new_file = _update_dir() / "nmail.new"
    try:
        with httpx.stream("GET", asset["browser_download_url"], timeout=_STREAM_TIMEOUT,
                          headers={"User-Agent": f"Nmail/{APP_VERSION}"}, follow_redirects=True) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("content-length") or 0)
            done, last_write = 0, 0.0
            with new_file.open("wb") as fp:
                for chunk in resp.iter_bytes(1 << 20):
                    fp.write(chunk)
                    done += len(chunk)
                    now = time.monotonic()
                    if total and now - last_write > 0.8:  # 节流写 KV，避免高频落盘
                        _set_state(phase="downloading", progress=min(99, done * 100 // total))
                        last_write = now
        _set_state(phase="verifying", progress=99)
        _verify_digest(new_file, digest)
    except (httpx.HTTPError, OSError, ValueError) as exc:
        with suppress(OSError):
            new_file.unlink()
        _set_state(phase="failed", error=f"下载或校验失败: {exc}")
        return
    try:
        _swap_in_new(new_file)
    except OSError as exc:
        _set_state(phase="failed", error=f"换身失败: {exc}")
        return
    _set_state(phase="ready", progress=100, staged_version=tag,
               pending_version=tag, digest=digest, error=None)
    notify_ready(tag)


def _pip_upgrade() -> None:
    """pip 渠道：原地升级本环境内的 nmail-app（运行中进程不受影响，模块已入内存）。"""
    proc = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--upgrade", "nmail-app",
         "--disable-pip-version-check", "-q"],
        capture_output=True, text=True, timeout=600,
    )
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()
        _set_state(phase="failed", error="pip 升级失败: " + (tail[-1][:200] if tail else "未知错误"))
        return
    # 版本号取更新检查缓存的 latest_version（刚检查过才有更新任务可言）
    latest = (_read_state().get("pending_version")
              or (get_setting("update_check_state", {}) or {}).get("latest_version") or "")
    staged = _parse_version_str(latest)
    _set_state(phase="ready", progress=100, staged_version=staged, error=None)
    notify_ready(staged)


def _parse_version_str(tag: str) -> str:
    v = _parse_version(tag)
    return ".".join(str(p) for p in v) if v else (tag or APP_VERSION)


# ── 重启 ────────────────────────────────────────────────────────────────

def restart_app(port: int) -> dict:
    """以已就位的新代码重启服务：spawn --wait-port 接同一端口，本进程随即退出。

    frozen：文件已换身，spawn 即新版；pip：site-packages 已升级，spawn 加载新码。
    浏览器页面轮询 /api/health 恢复后自动刷新，地址不变。"""
    if getattr(sys, "frozen", False):
        cmd = [sys.executable, "--wait-port", str(port), "--no-browser"]
    else:
        # 非冻结：新解释器 cwd 不可控，显式注入 backend 目录（app 包父目录）再导入；
        # pip venv 场景该路径本就在 sys.path，注入无害
        backend_root = str(Path(__file__).resolve().parents[2])
        cmd = [sys.executable, "-c",
               f"import sys; sys.path.insert(0, {backend_root!r}); from app.cli import main; main()",
               "--wait-port", str(port), "--no-browser"]
    kwargs: dict = {"close_fds": True}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(cmd, **kwargs)  # noqa: S603 — 命令完全由本进程自身形态构成
    threading.Timer(0.5, os._exit, args=(0,)).start()
    return {"ok": True, "restarting": True}


# ── 自动更新心跳（UPDATE_AND_DESKTOP.md §3.3，用户拍板口径）──────────────

def auto_update_tick() -> None:
    """启动延迟触发 + 调度器每日兜底共用：检查开启、自动安装开启、渠道可自更新、
    且确有新版本时，后台静默下载换身——不打扰当前使用，就绪后通知提示重启。
    全程零抛错（后台线程，失败静默留待下次）。"""
    try:
        if not get_setting("update_check_enabled", True):
            return
        if not get_setting("auto_update_enabled", True):
            return
        if not channel.can_self_update():
            return
        from app.core import update_check  # 延迟导入避免模块加载期耦合

        state = update_check.get_state()  # 24h 缓存节流，无网络也能用缓存
        if state.get("is_newer"):
            start_apply()
    except Exception:  # noqa: BLE001 — 心跳失败不影响主服务
        pass
