from fastapi import APIRouter

from app.config import APP_VERSION
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
