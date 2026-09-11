"""后台任务查询 API（IMPROVEMENT_PLAN §3.4）。

前端 useJob 以 GET /jobs/{id} 轮询（1s，终态即停）；/jobs/active 供全局
任务可见性（当前无人消费，留作观测口）。
"""
from fastapi import APIRouter, HTTPException

from app.core import jobs

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("/active")
def active_jobs() -> dict:
    return {"jobs": jobs.list_active()}


@router.get("/{job_id}")
def get_job(job_id: int) -> dict:
    job = jobs.get_job(job_id)
    if job is None:
        raise HTTPException(404, "任务不存在")
    return job
