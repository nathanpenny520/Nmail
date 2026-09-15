"""Nmail 启动器：起本地服务并打开浏览器。

三个入口共用本模块：run.py（源码开发）、控制台脚本 nmail（PyPI 安装）、
PyInstaller 冻结单文件。服务仅绑定 127.0.0.1。
"""
from __future__ import annotations

import argparse
import socket
import sys
import threading
import time
import webbrowser
from contextlib import suppress

DEFAULT_PORT = 8720


def find_free_port(start: int) -> int:
    port = start
    for _ in range(50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                port += 1
    raise RuntimeError(f"端口 {start} 起连续 50 个端口均被占用")


def wait_for_port(port: int, timeout: float = 30.0) -> int:
    """等 port 可绑定后精确回绑（更新重启专用：旧进程退出、新进程接同一端口，
    浏览器页面地址不变）。

    两段式：先探活——健康检查有人应答就说明旧进程还在，继续等；无人应答后
    再带 SO_REUSEADDR 试绑——旧进程退出后的 TIME_WAIT 连接残留会让裸 bind
    在 macOS 上报 EADDRINUSE 等满超时，进而错误地顺延换端口。超时才退回顺延。"""
    import httpx

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            httpx.get(f"http://127.0.0.1:{port}/api/health", timeout=0.4)
        except Exception:  # noqa: BLE001 — 无人应答即旧进程已退（或非 Nmail 服务）
            break
        time.sleep(0.2)
    while time.monotonic() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                time.sleep(0.2)
    print(f"等待端口 {port} 释放超时（{timeout:.0f}s），改用顺延端口", flush=True)
    return find_free_port(port)


def probe_existing(port: int) -> str | None:
    """端口上已有健康 Nmail 时返回其 URL。

    单实例语义：图标双击/重复命令启动不再顺延端口多开一套服务，直接打开
    已运行实例的页面（UPDATE_AND_DESKTOP.md §2）。探测失败一律当「没在运行」。
    """
    try:
        import httpx

        resp = httpx.get(f"http://127.0.0.1:{port}/api/health", timeout=1.0)
        if resp.status_code == 200 and resp.json().get("status") == "ok":
            return f"http://127.0.0.1:{port}"
    except Exception:  # noqa: BLE001 — 非 Nmail 服务/网络栈异常都视为端口可用
        pass
    return None


def open_browser_later(url: str) -> None:
    time.sleep(1.5)
    with suppress(OSError):
        webbrowser.open(url)  # 无图形环境时静默跳过


def _shortcut_command(install: bool) -> None:
    """install-shortcut / uninstall-shortcut：桌面图标一键安装（设置页同名功能）。"""
    from app.core import desktop  # 延迟导入保持 --help 轻量

    result = desktop.install_shortcut() if install else desktop.remove_shortcut()
    if result.get("ok"):
        paths = "、".join(result.get("paths", [])) or "（默认位置）"
        print(("已创建桌面图标: " if install else "已移除桌面图标: ") + paths)
    else:
        print(f"操作失败: {result.get('error')}")
        raise SystemExit(1)


def main(argv: list[str] | None = None) -> None:
    args_list = list(sys.argv[1:] if argv is None else argv)
    # 轻量子命令：argparse 前预扫，不影响既有参数面
    if args_list and args_list[0] in ("install-shortcut", "uninstall-shortcut"):
        _shortcut_command(args_list[0] == "install-shortcut")
        return

    from app.config import APP_VERSION  # 延迟导入保持 --help/--version 轻量

    parser = argparse.ArgumentParser(description="Nmail 一键启动")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    parser.add_argument(
        "--wait-port", type=int, default=None, metavar="N",
        help="等端口 N 释放后精确绑定它（更新重启专用；不做单实例探测）",
    )
    parser.add_argument("--version", action="version", version=f"Nmail {APP_VERSION}")
    args = parser.parse_args(args_list)

    # 更新换身收尾：上次下载中途退出留下的半程更新在此完成或清理（binary 渠道，
    # UPDATE_AND_DESKTOP.md §3.1 第 5 步）——保证「下次打开一定是新版」
    from app.core import update_apply  # noqa: E402 — 同样延迟导入

    update_apply.finish_pending_swap()

    from app.main import app as fastapi_app  # 延迟导入：--help 无需加载重型依赖
    import uvicorn

    if args.wait_port is not None:
        port = wait_for_port(args.wait_port)
    else:
        existing = probe_existing(args.port)
        if existing is not None:
            print(f"Nmail 已在运行: {existing}  (直接打开)")
            if not args.no_browser:
                webbrowser.open(existing)
            return
        port = find_free_port(args.port)
    url = f"http://127.0.0.1:{port}"

    print(f"Nmail 启动中: {url}  (Ctrl+C 退出)")

    if not args.no_browser:
        threading.Thread(target=open_browser_later, args=(url,), daemon=True).start()

    # 直接传 app 对象而非导入字符串：PyInstaller 冻结环境里字符串导入不可靠
    uvicorn.run(fastapi_app, host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":  # 冻结单文件的入口即本文件，缺此保护则加载完即静默退出
    main()
