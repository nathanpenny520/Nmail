"""Nmail 启动器：起本地服务并打开浏览器。

三个入口共用本模块：run.py（源码开发）、控制台脚本 nmail（PyPI 安装）、
PyInstaller 冻结单文件。服务仅绑定 127.0.0.1。
"""
from __future__ import annotations

import argparse
import copy
import logging
import socket
import sys
import threading
import time
import traceback
import webbrowser
from contextlib import suppress
from logging.handlers import RotatingFileHandler
from pathlib import Path

DEFAULT_PORT = 8720


def _bind_test(port: int, reuse: bool) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        if reuse:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def find_free_port(start: int) -> int:
    """从 start 起找可用端口。

    占用判定按 TCP 语义分层：有进程在监听（connect 可达）必跳过；裸 bind 失败
    但 SO_REUSEADDR 下可绑定的端口是 TIME_WAIT 残留（旧实例刚退出、连接未完全
    收敛），照常使用——否则重启后端口顺延（8720→8721→…），浏览器页面地址漂移
    （uvicorn 自带 SO_REUSEADDR，其绑定不受 TIME_WAIT 影响）。"""
    port = start
    for _ in range(50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            live = sock.connect_ex(("127.0.0.1", port)) == 0
        if not live and _bind_test(port, False):
            return port
        if not live and _bind_test(port, True):
            return port
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


# ── 窗口化平台配套：日志落盘 + 启动失败兜底（UPDATE_AND_DESKTOP.md §6）────

def _log_file() -> Path | None:
    """日志文件路径（数据目录 nmail.log）；数据目录不可得则放弃落盘。"""
    with suppress(Exception):  # noqa: BLE001 — 任何取路径异常都折成「不落盘」
        from app.config import get_data_dir

        return get_data_dir() / "nmail.log"
    return None


def setup_file_logging() -> None:
    """应用日志追加写数据目录：Windows 窗口化构建没有控制台可看，落盘是唯一
    去处。控制台渠道输出不受影响（终端照常、文件兼有）。uvicorn 自有 logger
    体系在 uvicorn.run 时经 dictConfig 整体重配，由 _log_config 注入同一文件。"""
    log_path = _log_file()
    if log_path is None:
        return
    handler = RotatingFileHandler(log_path, maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s"))
    logging.getLogger().addHandler(handler)


def _log_config() -> dict:
    """uvicorn 日志配置：默认配置基础上补文件 handler。必须改配置而非事后
    挂载——uvicorn.run 的 dictConfig 会整体覆盖 uvicorn/uvicorn.access 的
    handlers，事后挂的全被清掉。"""
    from uvicorn.config import LOGGING_CONFIG

    cfg = copy.deepcopy(LOGGING_CONFIG)
    log_path = _log_file()
    if log_path is None:
        return cfg
    cfg["formatters"]["plain"] = {"format": "%(asctime)s %(levelname)-8s %(name)s: %(message)s"}
    cfg["handlers"]["file"] = {
        "class": "logging.handlers.RotatingFileHandler",
        "formatter": "plain",
        "filename": str(log_path),
        "maxBytes": 1_000_000,
        "backupCount": 2,
        "encoding": "utf-8",
    }
    for name in ("uvicorn", "uvicorn.access"):
        cfg["loggers"][name]["handlers"].append("file")
    return cfg


def _report_crash() -> None:
    """启动失败兜底：traceback 追加进日志文件（窗口化平台终端无处可看）；
    Windows 冻结包再弹原生错误框，双击后绝不静默消失。"""
    tb = traceback.format_exc()
    log_path = _log_file()
    if log_path is not None:
        with suppress(OSError), log_path.open("a", encoding="utf-8") as fp:
            fp.write(tb)
    if sys.platform == "win32" and getattr(sys, "frozen", False):
        with suppress(Exception):  # noqa: BLE001 — 弹框失败也无能为力，放弃即可
            import ctypes

            lines = tb.strip().splitlines()
            tail = f"\n\n{lines[-1]}" if lines else ""
            where = f"\n\n日志文件：{log_path}" if log_path else ""
            ctypes.windll.user32.MessageBoxW(
                0, f"Nmail 启动失败，请把日志文件发给开发者。{where}{tail}", "Nmail", 0x10
            )


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
    """入口薄壳：未捕获异常先落日志再原样上抛（保留退出码）；
    SystemExit（--help/--version/参数错）直通不弹框。"""
    try:
        _launch(argv)
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001 — 兜底报告后照常抛出
        _report_crash()
        raise


def _launch(argv: list[str] | None = None) -> None:
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

    setup_file_logging()  # 尽早挂上：此后任何环节的异常都有处可查

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
    uvicorn.run(fastapi_app, host="127.0.0.1", port=port, log_level="info", log_config=_log_config())


if __name__ == "__main__":  # 冻结单文件的入口即本文件，缺此保护则加载完即静默退出
    main()
