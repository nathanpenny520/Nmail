from fastapi import APIRouter

from app.config import APP_VERSION
from app.core import update_check
from app.db.database import get_conn

router = APIRouter(tags=["system"])


@router.get("/api/health")
def health() -> dict:
    db_ok = True
    try:
        get_conn().execute("SELECT 1")
    except Exception:
        db_ok = False
    return {"status": "ok", "version": APP_VERSION, "db": "ok" if db_ok else "error"}


@router.get("/api/update-check")
def update_check_state(force: bool = False) -> dict:
    """更新检查状态；带缓存节流（24h），force=True 跳过缓存立即检查。"""
    return update_check.get_state(force=force)
