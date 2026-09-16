# 收尾计划（docs/WIND_DOWN_PLAN.md）

> **v0.4.2 后的收官阶段主线（2026-09-16 定稿）**：不加新功能，补齐分发产物、安装文档与键盘收尾后封版。
> 决策经用户 2026-09-16 拍板；本文件是落地工作的唯一依据。

## 决策记录（勿再议）

| # | 决策 | 说明 |
|---|---|---|
| 1 | **Homebrew 只做自家 tap cask** | `brew install --cask nathanpenny520/nmail/nmail`；**不提交官方 homebrew-cask**（人工审核有知名度门槛，等有用户量再议）。brew 下载不打 quarantine 属性，装完直接开、无 Gatekeeper 警告 |
| 2 | **macOS：dmg 首选，.app.zip 保留** | dmg 两栏拖装（Nmail.app + /Applications 软链）；官网/Release 默认下载看到的是 App（dmg） |
| 3 | **Intel macOS 放弃** | 仅 Apple Silicon（macos-latest=arm64），文档明示 |
| 4 | **不迁 Tauri** | 项目无 Electron 前提：Python FastAPI 后端 + 浏览器 GUI。迁移 = Rust 重写或壳+sidecar，违背收官原则 |
| 5 | **Linux 维持单文件** | 不做 AppImage/deb（难维护） |
| 6 | Windows 不上代码签名 | portable zip 仅打包体验升级；SmartScreen 警告依旧（MOTW），EV 证书收官期不上 |

## 任务清单

### P1 发版产物（release.yml + homebrew-nmail tap）

1. **dmg**：binaries job macOS 分支加 `hdiutil create -format UDZO` 两栏拖装布局，产出 `nmail-macos-arm64.dmg` 资产；`.app.zip` 照旧保留
2. **Windows portable zip**：exe 打成 `nmail-windows-x64.zip`（附运行说明）；winget 仍指裸 exe 不动
3. **Release Notes 自动化**：softprops 三处加 `generate_release_notes: true`（提交列表 + Full Changelog 链接）；发版收尾清单加 `gh release edit` 粘贴 CHANGELOG 本版条目
4. **tap cask**：homebrew-nmail 仓加 `Casks/nmail.rb`（url 指 dmg、`app "Nmail.app"`、livecheck）；release.yml homebrew-tap job 同步 bump cask
5. **验证点**：`.app`/dmg 形态下 channel 语义——binary 自更新是否兼容 bundle 内 `nmail-bin` 替换；不兼容则 dmg/cask 渠道按 brew 语义标不自更新（`brew upgrade` 升级），改 channel.py 即可

### P2 文档四处同步（CLAUDE.md 规范 #11）

dmg 首选 + cask 命令 + Windows zip 渠道 + 仅 Apple Silicon 声明，同步四处：
`docs/INSTALL.md` ｜ README 双语 ｜ 官网 `download.astro`（**硬编码资产名 `APP_ZIP` 旁加 `DMG` 常量**，逐处核对）｜ 代码内文案（channel.py 升级提示）

### P3 键盘收尾

1. **`?` 快捷键帮助面板**：MailBrowser 挂 `?`（Shift+/），浮层列全部快捷键；输入框聚焦时不触发（与现有 onKey 同一守卫）
2. **使用指南表补全**：现有 8 键表缺 `↑`/`↓` 方向键；补写信快捷键 `Ctrl/Cmd+S` 存草稿、`Ctrl/Cmd+Enter` 发送
3. 现有快捷键基线（MailBrowser.tsx，输入框聚焦时自动失效）：`j`/`↓`、`k`/`↑` 移动光标 · `Enter`/`o` 打开 · `e` 归档 · `#` 删除 · `x` 勾选 · `c` 写信 · `/` 搜索 · `Esc` 关闭

### P4 决策落档

本文件 + CLAUDE.md 指针 + CHANGELOG；完成后 PRODUCT_PLAN 标注收官状态。

## 验证口径

- release 改动：`bash scripts/release.sh <下一版本> --dry-run` 演练 + 实发一版核对资产齐、Release Notes 非空、cask 可 `brew install --cask` 全链路
- 文档：四处 grep 核对命令一致（规范 #11）
- 前端：`npm run build`（含字号门禁/vitest）；后端 ruff + pytest
