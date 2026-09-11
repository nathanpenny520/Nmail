"""S1 本机来源校验中间件：坏 Host / 外站 Origin 必须被拒（IMPROVEMENT_PLAN T1）。"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

local = TestClient(app, base_url="http://127.0.0.1")
foreign = TestClient(app, base_url="http://evil.example")


def test_local_host_allowed():
    assert local.get("/api/health").status_code == 200


def test_foreign_host_rejected():
    assert foreign.get("/api/health").status_code == 403


def test_foreign_origin_rejected():
    resp = local.post(
        "/api/ai/organize",
        json={},
        headers={"Origin": "http://evil.example"},
    )
    assert resp.status_code == 403


def test_null_origin_rejected():
    resp = local.get("/api/health", headers={"Origin": "null"})
    assert resp.status_code == 403


def test_local_origin_allowed():
    resp = local.post(
        "/api/ai/organize",
        json={},
        headers={"Origin": "http://127.0.0.1"},
    )
    assert resp.status_code == 200  # 通过守卫，正常进入业务逻辑
