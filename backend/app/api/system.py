import os
import subprocess

from fastapi import APIRouter

from app.config import APP_VERSION, get_data_dir, get_install_dir
from app.core import desktop, update_apply, update_check
from app.db.database import get_conn

router = APIRouter(tags=["system"])


def _git_commit() -> str:
    """启动时的 git 短哈希；打包/非 git 环境为空串。用于「改了没生效」的快速甄别。"""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5, check=True,
        )
        return out.stdout.strip()
    except Exception:  # noqa: BLE001 — 非 git 环境（打包版）拿不到就算了
        return ""


COMMIT = _git_commit()


@router.get("/api/health")
def health() -> dict:
    db_ok = True
    try:
        get_conn().execute("SELECT 1")
    except Exception:
        db_ok = False
    info = {"status": "ok", "version": APP_VERSION, "db": "ok" if db_ok else "error"}
    if COMMIT:
        info["commit"] = COMMIT
    return info


@router.get("/api/system/paths")
def system_paths() -> dict:
    """本机路径（设置页「关于」展示软件本地性）：数据目录实时取（含 NMAIL_DATA_DIR 重定向），
    安装目录按运行形态解析——均为当前进程的真实值，不硬编码。"""
    return {
        "data_dir": str(get_data_dir()),
        "install_dir": str(get_install_dir()),
        "data_dir_overridden": bool(os.environ.get("NMAIL_DATA_DIR")),
    }


@router.get("/api/update-check")
def update_check_state(force: bool = False) -> dict:
    """更新检查状态；带缓存节流（24h），force=True 跳过缓存立即检查。"""
    return update_check.get_state(force=force)


# ── 桌面图标（UPDATE_AND_DESKTOP.md §2）─────────────────────────────────

@router.get("/api/desktop-shortcut")
def desktop_shortcut_status() -> dict:
    return desktop.get_shortcut_status()


@router.post("/api/desktop-shortcut")
def desktop_shortcut_install() -> dict:
    """一键安装桌面图标（Windows .lnk / macOS Nmail.app / Linux .desktop）。"""
    return desktop.install_shortcut()


@router.delete("/api/desktop-shortcut")
def desktop_shortcut_remove() -> dict:
    return desktop.remove_shortcut()


# ── 应用内更新执行（UPDATE_AND_DESKTOP.md §3）───────────────────────────

@router.get("/api/update-apply")
def update_apply_state() -> dict:
    """自更新任务状态：渠道能力 + 当前 phase/progress/staged_version。"""
    return update_apply.get_state()


@router.post("/api/update-apply")
def update_apply_start() -> dict:
    """启动后台更新（binary 下载换身 / pip 原地升级）；不可自更新渠道返回命令提示。"""
    return update_apply.start_apply()


@router.post("/api/update-apply/restart")
def update_apply_restart(port: int = 0) -> dict:
    """以已就位的新代码重启服务：新进程 --wait-port 接管当前端口后本进程退出。

    port 由前端按 window.location 传入（服务端不反推监听端口）；缺省 0 时
    退化为仅退出请求（新进程找不到端口会顺延），正常流程前端必传。"""
    return update_apply.restart_app(port or 8720)
