#!/usr/bin/env python3
"""Nmail 一键启动：起本地服务并打开浏览器。

用法:
    python run.py [--port 8720] [--no-browser]
"""
from __future__ import annotations

import argparse
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

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
    try:
        webbrowser.open(url)
    except OSError:
        pass  # 无图形环境时静默跳过


def main() -> None:
    parser = argparse.ArgumentParser(description="Nmail 一键启动")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    args = parser.parse_args()

    import uvicorn

    port = find_free_port(args.port)
    url = f"http://127.0.0.1:{port}"

    print(f"Nmail 启动中: {url}  (Ctrl+C 退出)")

    if not args.no_browser:
        threading.Thread(target=open_browser_later, args=(url,), daemon=True).start()

    uvicorn.run("app.main:app", host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()
