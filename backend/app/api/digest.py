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
    digest = json.loads(latest["content_json"]) if latest else None
    if digest:
        digest = _filter_dismissed(digest)
    return {
        "dates": [r["date"] for r in rows],
        "digest": digest,
    }


def _filter_dismissed(digest: dict) -> dict:
    """重要邮件列表过滤掉用户已清除的条目（dismissed_important 为快照内的持久记录）。"""
    dismissed = set(digest.get("dismissed_important") or [])
    if dismissed:
        digest["important"] = [i for i in digest.get("important", []) if i["email_id"] not in dismissed]
    return digest


@router.post("/important/{email_id}/dismiss")
def dismiss_important(email_id: int) -> dict:
    """从最新摘要的重要邮件列表清除一条（记录持久化，重新生成不复活；跨天随新摘要重置）。"""
    conn = get_conn()
    row = conn.execute(
        "SELECT date, content_json FROM digest_history ORDER BY date DESC LIMIT 1"
    ).fetchone()
    if not row:
        raise HTTPException(404, "暂无摘要")
    data = json.loads(row["content_json"])
    if not any(i.get("email_id") == email_id for i in data.get("important", [])):
        raise HTTPException(404, "该邮件不在重要邮件列表中")
    dismissed = set(data.get("dismissed_important") or [])
    dismissed.add(email_id)
    data["dismissed_important"] = sorted(dismissed)
    conn.execute(
        "UPDATE digest_history SET content_json = ? WHERE date = ?",
        (json.dumps(data, ensure_ascii=False), row["date"]),
    )
    conn.commit()
    return {"ok": True}


@router.post("/generate")
def generate() -> dict:
    try:
        return build_digest(force=True)
    except tasks.AINotConfigured as exc:
        raise HTTPException(400, str(exc)) from None
