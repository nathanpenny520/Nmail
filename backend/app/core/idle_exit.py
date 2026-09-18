"""空闲自动退出（UPDATE_AND_DESKTOP.md §7，2026-09-18 用户拍板）。

用户模型：点图标=开标签页，关标签页=后台自己退。活动信号就是 HTTP 请求——
前端常驻轮询（通知铃 15s 等）即天然心跳；main.py 挂 ActivityMiddleware 记账
（在途请求数 + 最后活动时刻），lifespan 启动 watchdog 协程，空闲超阈值且无在途
请求时置 uvicorn should_exit 优雅退出（退出钩子由 cli 注入 Server 对象）。

开关三层（cli 裸 `--idle-exit` = 同意但读设置项；设置项 idle_exit_enabled 决定
图标启动是否真退；`--idle-exit N` 显式覆盖秒数，0=强制关）。终端裸跑无 flag
则完全不启用——总管家/脚本自动化零影响。

本模块只存运行态与纯逻辑，不碰 DB/网络；asyncio 之外可单测。
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable

logger = logging.getLogger(__name__)

DEFAULT_THRESHOLD = 90  # 秒（用户确认；60 会被浏览器后台标签节流误杀）

# 运行态（进程内单例；uvicorn 单事件循环，无锁）
_mode = "off"          # off | auto | fixed
_fixed_seconds = 0
_last_activity = time.monotonic()
_in_flight = 0
_exit_hook: Callable[[], None] | None = None


def configure(mode: str, seconds: int = 0) -> None:
    """cli 启动早期调用：--idle-exit 裸 flag → ("auto")；--idle-exit N → ("fixed", N)；
    未带 flag → ("off")。不读 DB（此时库未必就绪），auto 的设置项在 lifespan 再解析。"""
    global _mode, _fixed_seconds, _last_activity
    if mode not in ("off", "auto", "fixed"):
        raise ValueError(f"未知 idle-exit 模式: {mode}")
    _mode = mode
    _fixed_seconds = max(0, seconds)
    _last_activity = time.monotonic()


def set_exit_hook(hook: Callable[[], None]) -> None:
    """cli 注入退出钩子（一般是 lambda: setattr(server, "should_exit", True)）。"""
    global _exit_hook
    _exit_hook = hook


def enabled() -> bool:
    """看门狗是否已启用（lifespan 里 resolve 后判断；off 恒 False）。"""
    return _mode != "off"


def resolve_seconds(get_setting) -> int:
    """把启动模式折算成生效秒数。auto 读设置项（get_setting 由调用方注入，
    避免 core → db 的反向依赖在测试里打桩）；fixed 用显式值；off 恒 0。"""
    if _mode == "fixed":
        return _fixed_seconds
    if _mode == "auto":
        return DEFAULT_THRESHOLD if get_setting("idle_exit_enabled", True) else 0
    return 0


def touch() -> None:
    """活动刷新：任何 HTTP 请求开始/结束都算「在用」。"""
    global _last_activity
    _last_activity = time.monotonic()


def enter() -> None:
    global _in_flight
    _in_flight += 1
    touch()


def leave() -> None:
    global _in_flight
    _in_flight = max(0, _in_flight - 1)
    touch()


def idle_seconds() -> float:
    return time.monotonic() - _last_activity


def should_exit_now(threshold: int) -> bool:
    """看门狗判定（纯函数便于测试）：无在途请求且空闲超阈值。"""
    return _in_flight == 0 and idle_seconds() >= threshold


async def watchdog(
    threshold: int,
    tick: float | None = None,
    seconds_provider: Callable[[], int] | None = None,
) -> None:
    """lifespan 里的看门狗协程：周期检查，触发即调退出钩子并返回。

    seconds_provider 每 tick 重取生效秒数（main 传 resolve_seconds(get_setting) 的
    包装）——设置页开关即时生效，无需重启；返回 0 = 设置项已关，挂起等待不退出。
    缺省恒用构造阈值。tick 默认随阈值缩放（阈值/4，夹在 2–15s），短阈值测试
    也能秒级观察到退出。"""
    if seconds_provider is None:
        seconds_provider = lambda: threshold  # noqa: E731 — 单行直取，无需命名函数
    if tick is None:
        tick = max(2.0, min(15.0, threshold / 4))
    print(f"空闲自动退出：无请求 {threshold}s 后退出（每 {tick:g}s 检查）", flush=True)
    logger.info("空闲自动退出已启用：无请求 %ss 后退出（每 %gs 检查）", threshold, tick)
    while True:
        await asyncio.sleep(tick)
        current = seconds_provider()
        if current <= 0:
            continue  # 设置项已关：不退出；重新打开后按新阈值继续判定
        if should_exit_now(current):
            msg = f"空闲 {idle_seconds():.0f}s 无活动，自动退出（关掉所有 Nmail 标签页后属预期）"
            print(msg, flush=True)
            logger.info(msg)
            if _exit_hook is not None:
                _exit_hook()
            return


class ActivityMiddleware:
    """纯 ASGI 中间件：HTTP 请求全程计数。挂法见 main.py（add_middleware）。"""

    def __init__(self, app) -> None:  # noqa: ANN001 — ASGI app 无公共类型别名
        self.app = app

    async def __call__(self, scope, receive, send) -> None:  # noqa: ANN001
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        enter()
        try:
            await self.app(scope, receive, send)
        finally:
            leave()
