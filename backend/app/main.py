"""Nmail 本地服务入口。

仅绑定 127.0.0.1，托管 /api 与已构建的前端静态文件。
前端目录解析（DIST_DIR）在 config.py——api 层根路径 OAuth 回调也要读它。
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import api_router
from app.api.ext import log_ext_call as _log_ext_call
from app.config import APP_NAME, APP_VERSION, DIST_DIR
from app.core import batch_ops, pipeline  # noqa: F401 — 导入即注册 jobs runner（organize/imap_batch）
from app.db.database import cleanup_retention, run_migrations
from app.scheduler import MailScheduler

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
    # v0.4 P3（REDESIGN_PLAN §5.1）：旧 drafts 表（AI 待审）一次性并入 user_drafts
    # （Markdown→HTML 需 Python，KV 门控幂等；schema 变更在迁移 v19）
    from app.core.outbox import migrate_legacy_ai_drafts

    migrate_legacy_ai_drafts()
    cleanup_retention()  # R7：通知/用量日志保留策略，防本地库无界增长
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(title=APP_NAME, version=APP_VERSION, lifespan=lifespan)


# ── 对外 API 错误 envelope（AGENT_SKILL_PLAN P1）─────────────────────────
# /api/ext/* 失败统一 {"ok":false,"error":{code,message}}（code 供 agent/CLI 按表
# 决策重试或改参数），429 的 Retry-After 经 exc.headers 透传；成功体与内部 API
# （/api/extkeys 管理面含内）保持 {"detail"} 原样，互不影响。
_EXT_ERROR_CODES = {
    400: "bad_request", 401: "invalid_key", 403: "forbidden", 404: "not_found",
    422: "invalid_params", 429: "rate_limited", 502: "upstream", 503: "upstream", 504: "upstream",
}


def _ext_error_body(status_code: int, message: str) -> dict:
    code = _EXT_ERROR_CODES.get(status_code, "server_error" if status_code >= 500 else "bad_request")
    return {"ok": False, "error": {"code": code, "message": message}}


@app.exception_handler(StarletteHTTPException)
async def _api_http_exception_handler(request: Request, exc: StarletteHTTPException):
    if not request.url.path.startswith("/api/ext/"):
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers)
    return JSONResponse(
        _ext_error_body(exc.status_code, str(exc.detail)),
        status_code=exc.status_code, headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def _api_validation_exception_handler(request: Request, exc: RequestValidationError):
    if not request.url.path.startswith("/api/ext/"):
        return JSONResponse({"detail": exc.errors()}, status_code=422)
    message = "；".join(
        f"{'.'.join(str(loc) for loc in e['loc'][1:]) or 'body'}: {e['msg']}"
        for e in exc.errors()[:5]
    )
    return JSONResponse(_ext_error_body(422, message), status_code=422)


@app.exception_handler(Exception)
async def _api_unhandled_exception_handler(request: Request, exc: Exception):
    if not request.url.path.startswith("/api/ext/"):
        # 与 Starlette 默认 500 同形（ServerErrorMiddleware 仍记录堆栈）
        return PlainTextResponse("Internal Server Error", status_code=500)
    return JSONResponse(_ext_error_body(500, f"服务器内部错误：{exc}"), status_code=500)

# ── 本机来源校验（IMPROVEMENT_PLAN S1）────────────────────────────────────
# 服务仅绑定 127.0.0.1，但浏览器不限：恶意网页可向 http://127.0.0.1:8720 发
# multipart 无预检 POST 触发本机 API（drive-by），公网域名也可经 DNS rebinding
# 解析到 127.0.0.1 后用自己的域名作 Host 访问。两道校验零依赖、不影响正常使用：
# - Host 必须是本机主机名（端口与实际监听一致时才严格比对）；
# - 浏览器附带的 Origin（POST/fetch 恒带；同源 GET 一般不带）必须是本机源。
# 例外（v0.4 P7，REDESIGN_PLAN §7.4）：/api/ext/* 持 X-Api-Key 认证，豁免两道
# 来源校验——外部脚本经自建隧道到达时 Host/Origin 本来就不是本机；浏览器跨站
# 请求带不上自定义头（触发预检而本服务不应答），drive-by 风险由 Key 兜住。
_LOCAL_HOSTNAMES = {"127.0.0.1", "localhost", "::1"}


def _is_local_host(hostname: str) -> bool:
    return (hostname or "").strip("[]").lower() in _LOCAL_HOSTNAMES


@app.middleware("http")
async def _local_source_guard(request: Request, call_next):
    if request.url.path.startswith("/api/ext/"):
        response = await call_next(request)
        if request.url.path != "/api/ext/v1/health":  # 存活探测高频轮询，不记日志
            from starlette.concurrency import run_in_threadpool

            await run_in_threadpool(_log_ext_call, request, response.status_code)
        return response

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
