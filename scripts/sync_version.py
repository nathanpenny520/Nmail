#!/usr/bin/env python3
"""版本号统一同步：唯一来源 = 根 pyproject.toml，一键写入所有跟随位置。

app / nmail-cli / skill 使用同一条版本线（用户决策 2026-09-15）——此前 CLI
独立版本（0.1.0）与服务端版本（0.4.0）互不相关，导致 _notice.update 版本
比较永久误报。跟随位置共四处：

  1. pyproject.toml                    （来源，release.sh 从这里改起）
  2. nmail-cli/pyproject.toml          （nmail-cli 发包版本）
  3. nmail-cli/nmail_cli/__init__.py   （__version__，运行时自报）
  4. skills/SKILL.md                   （frontmatter version）

release.sh 在改完版本号后调用本脚本；backend/tests/test_version_sync.py
在 CI 校验四处一致，漂移即红。用法：

  python3 scripts/sync_version.py          # 按根 pyproject 当前版本同步其余三处
  python3 scripts/sync_version.py 0.5.0    # 先把根 pyproject 改成 0.5.0 再同步
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# (相对路径, 版本行正则, 替换模板)；正则必须恰好命中 1 处，多/少都算漂移故障。
# 一律用无 $ 锚定的行首匹配（替换只动值）——行尾可能带注释，锚死会把带注释的行判成漂移。
_TARGETS = [
    ("nmail-cli/pyproject.toml", r'(?m)^version = "[0-9][0-9.]*"', 'version = "{v}"'),
    ("nmail-cli/nmail_cli/__init__.py", r'(?m)^__version__ = "[0-9][0-9.]*"',
     '__version__ = "{v}"'),
    ("skills/SKILL.md", r"(?m)^version: [0-9][0-9.]*", "version: {v}"),
]


def main() -> None:
    pyproject_path = ROOT / "pyproject.toml"
    pyproject = pyproject_path.read_text(encoding="utf-8")

    if len(sys.argv) > 1:  # 带参数：先把根 pyproject 改成目标版本（等价 release.sh 内的 sed）
        version = sys.argv[1]
        if not re.fullmatch(r"\d+\.\d+\.\d+", version):
            raise SystemExit(f"❌ 版本号格式应为 X.Y.Z：{version}")
        new, n = re.subn(r'(?m)^version = "[0-9][0-9.]*"', f'version = "{version}"', pyproject)
        if n != 1:
            raise SystemExit(f"❌ pyproject.toml 版本行命中 {n} 处（应为 1）")
        pyproject_path.write_text(new, encoding="utf-8")
        pyproject = new
        print(f"✅ pyproject.toml → {version}")

    m = re.search(r'(?m)^version = "([0-9][0-9.]*)"', pyproject)
    if not m:
        raise SystemExit("❌ pyproject.toml 里找不到 version 行")
    version = m.group(1)

    for rel, pattern, template in _TARGETS:
        path = ROOT / rel
        text = path.read_text(encoding="utf-8")
        new, n = re.subn(pattern, template.format(v=version), text)
        if n != 1:
            raise SystemExit(f"❌ {rel} 版本行命中 {n} 处（应为 1），文件已漂移，请手动检查")
        path.write_text(new, encoding="utf-8")
        print(f"✅ {rel} → {version}")

    print(f"版本已统一：{version}（pyproject / nmail-cli / __init__ / SKILL.md）")


if __name__ == "__main__":
    main()
