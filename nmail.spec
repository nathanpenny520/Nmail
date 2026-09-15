# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置：三平台单文件 nmail（内含前端静态资源）。

构建前先执行 bash scripts/sync_frontend.sh 同步前端产物。
已知分发注意点（详见 README）：Windows SmartScreen 对无签名 exe 有警告；
macOS 未公证二进制需右键打开或 xattr -cr。
"""
from pathlib import Path

import sys

ROOT = Path(SPECPATH)
STATIC = ROOT / "backend" / "app" / "static"

# 应用图标：Windows→ico、macOS→icns，Linux 不支持嵌入则忽略（assets/ 由 scripts/gen_icons.py 生成）
_ICON = {"win32": "nmail.ico", "darwin": "nmail.icns"}.get(sys.platform)
_icon_path = ROOT / "assets" / _ICON if _ICON else None
ICON = str(_icon_path) if _icon_path and _icon_path.exists() else None

# pyproject.toml 是版本唯一来源：冻结环境无包元数据，config._app_version 读随包副本解析版本
datas = [(str(ROOT / "pyproject.toml"), ".")]
# 桌面图标生成资产（core/desktop.py 运行时读取；UPDATE_AND_DESKTOP.md §2）
APP_ASSETS = ROOT / "backend" / "app" / "assets"
if APP_ASSETS.is_dir():
    datas.append((str(APP_ASSETS), "app/assets"))
if STATIC.is_dir():
    datas.append((str(STATIC), "app/static"))

a = Analysis(
    [str(ROOT / "backend" / "app" / "cli.py")],
    pathex=[str(ROOT / "backend")],
    binaries=[],
    datas=datas,
    hiddenimports=[
        # uvicorn 以字符串形式延迟导入这些子模块，冻结时需显式声明
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="nmail",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=True,  # 保留控制台便于查看启动日志
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICON,
)
