"""Nmail 启动器：起本地服务并打开浏览器。

三个入口共用本模块：run.py（源码开发）、控制台脚本 nmail（PyPI 安装）、
PyInstaller 冻结单文件。服务仅绑定 127.0.0.1。
"""
from __future__ import annotations

import argparse
import socket
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


def open_browser_later(url: str) -> None:
    time.sleep(1.5)
    with suppress(OSError):
        webbrowser.open(url)  # 无图形环境时静默跳过


def main(argv: list[str] | None = None) -> None:
    from app.config import APP_VERSION  # 延迟导入保持 --help/--version 轻量

    parser = argparse.ArgumentParser(description="Nmail 一键启动")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    parser.add_argument("--version", action="version", version=f"Nmail {APP_VERSION}")
    args = parser.parse_args(argv)

    from app.main import app as fastapi_app  # 延迟导入：--help 无需加载重型依赖
    import uvicorn

    port = find_free_port(args.port)
    url = f"http://127.0.0.1:{port}"

    print(f"Nmail 启动中: {url}  (Ctrl+C 退出)")

    if not args.no_browser:
        threading.Thread(target=open_browser_later, args=(url,), daemon=True).start()

    # 直接传 app 对象而非导入字符串：PyInstaller 冻结环境里字符串导入不可靠
    uvicorn.run(fastapi_app, host="127.0.0.1", port=port, log_level="info")
