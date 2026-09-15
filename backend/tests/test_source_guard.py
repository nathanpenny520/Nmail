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


# ── 公网隧道管理面拦截（2026-09-15 安全审计 A1）─────────────────────────────
# cloudflared 默认把 Host 重写为 origin 地址 + curl 类客户端不带 Origin →
# 经公网 CF 隧道时两道本机校验失效；管理面必须拒绝携带 CF-* 头的请求。

def test_cf_edge_headers_rejected_on_admin_api():
    for hdr in ("CF-Connecting-IP", "CF-Ray", "CF-Worker"):
        resp = local.get("/api/accounts", headers={hdr: "1.2.3.4"})
        assert resp.status_code == 403


def test_cf_headers_allowed_on_ext_api():
    # /api/ext/* 在来源守卫之前放行：经公网 CF 隧道持 Key 调用不受影响
    resp = foreign.get("/api/ext/v1/health", headers={"CF-Ray": "1"})
    assert resp.status_code == 200


def test_forwarded_headers_not_blocked():
    # Tailscale serve 仅加 X-Forwarded-*：SSH/Tailscale 远程访问 UI 不受影响
    assert local.get("/api/health", headers={"X-Forwarded-For": "100.64.0.1"}).status_code == 200


def test_ext_api_exempt_from_host_check():
    # ext 豁免两道来源校验（外部脚本经隧道到达时 Host 本非本机）：health 免认证可作探测
    assert foreign.get("/api/ext/v1/health").status_code == 200
