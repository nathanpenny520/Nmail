"""轻量任务执行器（IMPROVEMENT_PLAN §3.4）。

长任务（AI 整理、批量 IMAP 动作）提交后立即返回 job_id，HTTP 不再被长耗时
操作阻塞；进度与结果写 jobs 表（迁移 v12），前端经 GET /api/jobs/* 轮询。
执行体经 `@runner(kind)` 注册——由拥有业务逻辑的模块（core/pipeline.py、
core/batch_ops.py）在导入时注册，本模块不反向依赖业务实现。
"""
from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from collections.abc import Callable

from app.db.database import get_conn, tx

logger = logging.getLogger(__name__)

_MAX_WORKERS = 2
_executor = ThreadPoolExecutor(max_workers=_MAX_WORKERS, thread_name_prefix="nmail-job")
_runners: dict[str, Callable[..., dict]] = {}


def runner(kind: str) -> Callable[[Callable[..., dict]], Callable[..., dict]]:
    """注册任务执行函数：fn(job_id, **payload) -> result(dict，写入 result_json)。"""
    def wrap(fn: Callable[..., dict]) -> Callable[..., dict]:
        _runners[kind] = fn
        return fn
    return wrap


def submit(kind: str, *, account_id: int | None = None, dedupe: bool = False,
           **payload: Any) -> int:
    """登记 job 并提交线程池，立即返回 job_id。

    dedupe=True 时同 kind + 同 account_scope 的 running 任务直接复用
    （防双击重复提交，如「AI 整理」）。account_id 既作去重作用域也并入
    payload，执行体可按需取用。
    """
    payload.setdefault("account_id", account_id)
    with tx() as conn:
        if dedupe:
            row = conn.execute(
                "SELECT id FROM jobs WHERE kind = ? AND status = 'running' AND account_id IS ?",
                (kind, account_id),
            ).fetchone()
            if row:
                return int(row["id"])
        cur = conn.execute(
            "INSERT INTO jobs (kind, account_id) VALUES (?, ?)", (kind, account_id)
        )
        job_id = int(cur.lastrowid)
    _executor.submit(_run, kind, job_id, payload)
    return job_id


def report(job_id: int, *, stage: str, progress: float | None = None,
           detail: str = "") -> None:
    """执行中上报进度（0..1）与面向用户的阶段明细。"""
    sets = ["stage = ?", "updated_at = datetime('now')"]
    params: list[Any] = [stage]
    if progress is not None:
        sets.append("progress = ?")
        params.append(max(0.0, min(1.0, float(progress))))
    if detail:
        sets.append("detail = ?")
        params.append(detail[:300])
    params.append(job_id)
    conn = get_conn()
    conn.execute(f"UPDATE jobs SET {', '.join(sets)} WHERE id = ?", params)
    conn.commit()


def get_job(job_id: int) -> dict | None:
    row = get_conn().execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if row is None:
        return None
    return {
        "id": int(row["id"]),
        "kind": row["kind"],
        "account_id": row["account_id"],
        "status": row["status"],
        "progress": float(row["progress"]),
        "stage": row["stage"],
        "detail": row["detail"],
        "result": json.loads(row["result_json"]) if row["result_json"] else None,
    }


def list_active() -> list[dict]:
    rows = get_conn().execute(
        "SELECT * FROM jobs WHERE status = 'running' ORDER BY id"
    ).fetchall()
    return [get_job(int(r["id"])) or {} for r in rows]


def _run(kind: str, job_id: int, payload: dict) -> None:
    fn = _runners.get(kind)
    if fn is None:
        with tx() as conn:
            conn.execute(
                "UPDATE jobs SET status = 'failed', detail = '未知任务类型',"
                " updated_at = datetime('now') WHERE id = ?",
                (job_id,),
            )
        return
    try:
        result = fn(job_id, **payload)
        with tx() as conn:
            conn.execute(
                "UPDATE jobs SET status = 'done', progress = 1, result_json = ?,"
                " updated_at = datetime('now') WHERE id = ?",
                (json.dumps(result or {}, ensure_ascii=False), job_id),
            )
    except Exception as exc:  # noqa: BLE001 — 失败进表供前端展示，不进 HTTP
        logger.exception("job %s(%s) failed", job_id, kind)
        with tx() as conn:
            conn.execute(
                "UPDATE jobs SET status = 'failed', detail = ?,"
                " updated_at = datetime('now') WHERE id = ?",
                (str(exc)[:300], job_id),
            )
