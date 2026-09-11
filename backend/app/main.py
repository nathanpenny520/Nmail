"""Nmail 本地服务入口。

仅绑定 127.0.0.1，托管 /api 与已构建的前端静态文件。
前端目录按运行形态解析：wheel 安装（app/static）→ PyInstaller 冻结资源 → 源码开发（frontend/dist）。
"""
from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import api_router
from app.config import APP_NAME, APP_VERSION
from app.core import pipeline  # noqa: F401 — 导入即注册 jobs runner（organize）
from app.db.database import run_migrations
from app.scheduler import MailScheduler


def _find_dist_dir() -> Path | None:
    here = Path(__file__).resolve().parent  # .../app（源码或 site-packages）
    candidates: list[Path] = []
    if getattr(sys, "frozen", False):  # PyInstaller 单文件：只用随包资源
        base = Path(getattr(sys, "_MEIPASS", None) or Path(sys.executable).parent)
        candidates.append(base / "app" / "static")
    else:
        # 源码开发：frontend/dist 优先（跟随每次构建），app/static 是打包快照，
        # 两者并存时若优先 static 会让开发者一直看到旧界面
        candidates.append(here.parents[1] / "frontend" / "dist")
        candidates.append(here / "static")
    for p in candidates:
        if p.is_dir():
            return p
    return None


DIST_DIR = _find_dist_dir()

scheduler = MailScheduler()


class SPAStaticFiles(StaticFiles):
    """SPA 历史路由回退：未命中的路径返回 index.html，由前端路由接管。

    兼容两种 Starlette 行为：返回 404 响应，或直接抛出 HTTPException(404)。
    """

    async def get_response(self, path: str, scope):
        try:
            response = await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404:
                raise
            return await super().get_response("index.html", scope)
        if response.status_code == 404:
            return await super().get_response("index.html", scope)
        return response


@asynccontextmanager
async def lifespan(_: FastAPI):
    run_migrations()
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(title=APP_NAME, version=APP_VERSION, lifespan=lifespan)

# ── 本机来源校验（IMPROVEMENT_PLAN S1）────────────────────────────────────
# 服务仅绑定 127.0.0.1，但浏览器不限：恶意网页可向 http://127.0.0.1:8720 发
# multipart 无预检 POST 触发本机 API（drive-by），公网域名也可经 DNS rebinding
# 解析到 127.0.0.1 后用自己的域名作 Host 访问。两道校验零依赖、不影响正常使用：
# - Host 必须是本机主机名（端口与实际监听一致时才严格比对）；
# - 浏览器附带的 Origin（POST/fetch 恒带；同源 GET 一般不带）必须是本机源。
_LOCAL_HOSTNAMES = {"127.0.0.1", "localhost", "::1"}


def _is_local_host(hostname: str) -> bool:
    return (hostname or "").strip("[]").lower() in _LOCAL_HOSTNAMES


@app.middleware("http")
async def _local_source_guard(request: Request, call_next):
    server = request.scope.get("server")
    server_port = server[1] if server else None

    host_header = request.headers.get("host", "")
    hostname, _, port = host_header.rpartition(":")
    if not hostname or ":" in hostname:  # Host 无端口（HTTP/1.0 少见）或 IPv6 裸地址
        hostname, port = host_header, ""
    if not _is_local_host(hostname) or (
            port and server_port is not None and port != str(server_port)):
        return JSONResponse({"detail": "拒绝非本机 Host 的请求"}, status_code=403)

    origin = request.headers.get("origin")
    if origin:
        try:
            parsed = urlsplit(origin)
        except ValueError:
            return JSONResponse({"detail": "拒绝无法解析的 Origin"}, status_code=403)
        if parsed.scheme not in ("http", "https") or not _is_local_host(parsed.hostname or "") or (
                parsed.port is not None and server_port is not None and parsed.port != server_port):
            return JSONResponse({"detail": "拒绝跨源请求"}, status_code=403)

    return await call_next(request)


app.include_router(api_router)

if DIST_DIR is not None:
    # 路由先于挂载注册，/api 不受影响；html=True 使 / 直接返回 index.html
    app.mount("/", SPAStaticFiles(directory=DIST_DIR, html=True), name="frontend")
