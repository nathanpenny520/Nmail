"""Nmail 本地服务入口。

仅绑定 127.0.0.1，托管 /api 与已构建的前端静态文件（frontend/dist）。
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import api_router
from app.config import APP_NAME, APP_VERSION
from app.db.database import run_migrations

ROOT = Path(__file__).resolve().parents[2]
DIST_DIR = ROOT / "frontend" / "dist"


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
    yield


app = FastAPI(title=APP_NAME, version=APP_VERSION, lifespan=lifespan)
app.include_router(api_router)

if DIST_DIR.is_dir():
    # 路由先于挂载注册，/api 不受影响；html=True 使 / 直接返回 index.html
    app.mount("/", SPAStaticFiles(directory=DIST_DIR, html=True), name="frontend")
