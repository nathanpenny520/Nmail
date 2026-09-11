"""每日摘要 API：查看、手动生成/刷新。"""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException

from app.ai import tasks
from app.ai.digest import build_digest
from app.db.database import get_conn

router = APIRouter(prefix="/api/digest", tags=["digest"])


@router.get("")
def get_digest() -> dict:
    conn = get_conn()
    rows = conn.execute(
        "SELECT date FROM digest_history ORDER BY date DESC LIMIT 14"
    ).fetchall()
    latest = conn.execute(
        "SELECT content_json FROM digest_history ORDER BY date DESC LIMIT 1"
    ).fetchone()
    return {
        "dates": [r["date"] for r in rows],
        "digest": json.loads(latest["content_json"]) if latest else None,
    }


@router.post("/generate")
def generate() -> dict:
    try:
        return build_digest(force=True)
    except tasks.AINotConfigured as exc:
        raise HTTPException(400, str(exc)) from None
