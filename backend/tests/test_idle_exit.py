"""空闲自动退出（UPDATE_AND_DESKTOP.md §7）纯逻辑：模式折算/活动记账/看门狗。

模块是进程内单例，用例各自收尾复位，避免污染其他测试导入的 app.main。
"""
from __future__ import annotations

import asyncio

import pytest

from app.core import idle_exit


def teardown_function():
    idle_exit.configure("off")
    idle_exit.set_exit_hook(lambda: None)
    while idle_exit._in_flight:  # 被取消的用例可能留下在途计数，复位防污染
        idle_exit.leave()


def test_resolve_seconds_modes():
    idle_exit.configure("off")
    assert idle_exit.resolve_seconds(lambda k, d=None: True) == 0
    idle_exit.configure("auto")
    assert idle_exit.resolve_seconds(lambda k, d=None: True) == idle_exit.DEFAULT_THRESHOLD
    assert idle_exit.resolve_seconds(lambda k, d=None: False) == 0  # 设置项关 → 不退
    idle_exit.configure("fixed", 45)
    assert idle_exit.resolve_seconds(lambda k, d=None: False) == 45  # 显式秒数优先于设置项
    idle_exit.configure("fixed", 0)
    assert idle_exit.resolve_seconds(lambda k, d=None: True) == 0  # --idle-exit 0 强制关


def test_activity_accounting():
    idle_exit.enter()
    assert not idle_exit.should_exit_now(0)  # 在途请求期间永不退出（AI 长流不误杀）
    idle_exit.enter()
    idle_exit.leave()
    idle_exit.leave()
    assert idle_exit.should_exit_now(0)  # 无在途且 idle>=0 恒真（边界探针）
    assert idle_exit.should_exit_now(10**9) is False  # 刚活动过，长阈值不触发


def test_watchdog_fires_hook(monkeypatch):
    fired: list[int] = []
    idle_exit.configure("fixed", 1)
    idle_exit.set_exit_hook(lambda: fired.append(1))
    monkeypatch.setattr(idle_exit, "idle_seconds", lambda: 10.0)  # 已空闲 10s > 阈值 1s
    asyncio.run(idle_exit.watchdog(1, tick=0.05))
    assert fired == [1]


def test_watchdog_survives_while_busy(monkeypatch):
    fired: list[int] = []
    idle_exit.configure("fixed", 1)
    idle_exit.set_exit_hook(lambda: fired.append(1))
    monkeypatch.setattr(idle_exit, "idle_seconds", lambda: 10.0)
    idle_exit.enter()  # 有在途请求 → 不退；超时被取消即证明整个时限内都没触发
    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(asyncio.wait_for(idle_exit.watchdog(1, tick=0.05), timeout=0.4))


def test_watchdog_provider_gates_live(monkeypatch):
    """provider 重读设置项（§7「设置页开关即时生效」）：关=挂起，开=恢复判定。"""
    fired: list[int] = []
    idle_exit.configure("auto")
    idle_exit.set_exit_hook(lambda: fired.append(1))
    monkeypatch.setattr(idle_exit, "idle_seconds", lambda: 10.0)
    enabled = {"v": False}  # 模拟设置项关闭
    with pytest.raises(asyncio.TimeoutError):  # 不退出 → 协程被超时取消，即「挂起等待」
        asyncio.run(asyncio.wait_for(
            idle_exit.watchdog(1, tick=0.05, seconds_provider=lambda: 1 if enabled["v"] else 0),
            timeout=0.3))
    assert fired == []  # 整个时限内设置项关 → 不退

    idle_exit.configure("fixed", 1)
    asyncio.run(asyncio.wait_for(  # 正常路径秒级返回；防呆超时让回归可见而非挂死
        idle_exit.watchdog(1, tick=0.05, seconds_provider=lambda: 1), timeout=1.0))
    assert fired == [1]  # 恢复后按阈值正常退出
