import subprocess

from fastapi import APIRouter

from app.config import APP_VERSION
from app.core import update_check
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


@router.get("/api/update-check")
def update_check_state(force: bool = False) -> dict:
    """更新检查状态；带缓存节流（24h），force=True 跳过缓存立即检查。"""
    return update_check.get_state(force=force)
