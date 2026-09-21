"""Nmail 启动器：起本地服务并打开浏览器。

三个入口共用本模块：run.py（源码开发）、控制台脚本 nmail（PyPI 安装）、
PyInstaller 冻结单文件。服务仅绑定 127.0.0.1。
"""
from __future__ import annotations

import argparse
import copy
import logging
import os
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


def raise_nofile_limit(cap: int = 10240) -> tuple[int, int] | None:
    """抬高 fd 软上限（硬上限内）。Windows 返回 None 跳过——resource 模块
    POSIX 专属，Windows 也没有 fd 软上限概念，无此处的触顶风险。

    GUI/launchd 会话默认软上限仅 256：anyio 工作线程按负载起停，每个碰库的
    工作线程都持有 sqlite 连接（db+wal 句柄），请求爆发期连接水位堆高即可
    触顶——accept 报 Errno 24、sqlite 打不开，服务整体瘫痪（2026-09-17 实测）。
    硬上限 unlimited 时直接给到 cap。失败静默：原上限下仍可用，只是余量小。
    """
    if sys.platform == "win32":
        return None
    import resource

    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    target = cap if hard == resource.RLIM_INFINITY else min(cap, hard)
    if soft < target:
        with suppress(Exception):
            resource.setrlimit(resource.RLIMIT_NOFILE, (target, hard))
            soft = target
    return soft, hard


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
    parser.add_argument(
        "--idle-exit", dest="idle_exit", nargs="?", const=-1, default=None, type=int,
        metavar="N",
        help="空闲自动退出（桌面图标启动专用）：裸 flag 按设置项开关（默认无请求 90s 后"
             "退出）；N 显式指定秒数，0 关闭。不带本参数则永不空闲退出（终端/自动化场景）",
    )
    parser.add_argument("--version", action="version", version=f"Nmail {APP_VERSION}")
    args = parser.parse_args(args_list)

    setup_file_logging()  # 尽早挂上：此后任何环节的异常都有处可查
    if (limits := raise_nofile_limit()) is not None:
        print(f"fd soft limit: {limits[0]} (hard {limits[1]})")

    # 空闲自动退出（UPDATE_AND_DESKTOP.md §7）：模式在此定下；auto 的设置项
    # 由 lifespan 解析（此时 DB 未必就绪），退出钩子在下面 Server 对象上注入
    from app.core import idle_exit

    if args.idle_exit is None:
        idle_exit.configure("off")
    elif args.idle_exit == -1:
        idle_exit.configure("auto")
    else:
        idle_exit.configure("fixed", max(0, args.idle_exit))

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

    # macOS .app 存根握手（UPDATE_AND_DESKTOP.md §2）：bundle server 脚本经
    # NMAIL_URL_FILE 告知约定文件，把实际绑定地址写进去——端口被占顺延也正确，
    # 存根收到 Dock「再点图标」reopen 事件读它用默认浏览器重开页面
    if url_file := os.environ.get("NMAIL_URL_FILE"):
        with suppress(OSError):
            Path(url_file).write_text(url, encoding="utf-8")

    print(f"Nmail 启动中: {url}  (Ctrl+C 退出)")

    if not args.no_browser:
        threading.Thread(target=open_browser_later, args=(url,), daemon=True).start()

    # 直接传 app 对象而非导入字符串：PyInstaller 冻结环境里字符串导入不可靠。
    # Server 对象形态（等价于 uvicorn.run）：空闲退出的钩子需要摸到 should_exit
    config = uvicorn.Config(
        fastapi_app, host="127.0.0.1", port=port, log_level="info", log_config=_log_config()
    )
    server = uvicorn.Server(config)
    if idle_exit.enabled():
        idle_exit.set_exit_hook(lambda: setattr(server, "should_exit", True))
    try:
        server.run()
    except KeyboardInterrupt:
        # Ctrl+C 退出：uvicorn 已优雅关停（服务至此都正常），不把 asyncio 取消堆栈
        # 漏到顶层——默认行为会打印一大段 KeyboardInterrupt/CancelledError，像出了错
        print("\nNmail 已退出。")


if __name__ == "__main__":  # 冻结单文件的入口即本文件，缺此保护则加载完即静默退出
    main()
