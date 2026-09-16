# 应用内更新与桌面图标（docs/UPDATE_AND_DESKTOP.md）

> 2026-09-15 用户拍板并当轮实施。两个诉求：①检查到新版本后应用内直接更新（默认开、可关）+ 更新按钮；②每种安装方式都有桌面图标，非技术用户不必碰命令行。
> 本文档是方案与决策记录；落地后的结构现状见 docs/ARCHITECTURE.md。

## 1. 渠道识别（core/channel.py）

自更新与桌面集成都必须知道自己是怎么被装上的。启动时检测一次（模块级缓存）：

| 渠道 | 判定 | 桌面图标 | 应用内更新 |
|---|---|---|---|
| `binary` 直装二进制 | `sys.frozen` 且路径不在包管理器目录 | 打包 .app（mac）/ .lnk（Win） | **完整自更新**（下载→校验→换身→重启） |
| `brew` | frozen 且路径在 `/opt/homebrew`、`/usr/local` 下 | 打包 .app | 不自换身 → 提示 `brew upgrade nathanpenny520/nmail/nmail` |
| `winget` | frozen 且路径含 `WinGet\Packages` | .lnk | 不自换身 → 提示 `winget upgrade` |
| `pip` | 非 frozen 且不在 uv 缓存 | 命令包装器 + 独立图标 | 后台 `pip install --upgrade nmail-app` |
| `uvx` | `sys.prefix` 位于 uv 缓存（archive-v0 / Caches/uv / uv/cache） | 命令包装器 + 独立图标 | 不自更新 → 提示 `uvx --refresh --from nmail-app nmail` |

## 2. 桌面图标（core/desktop.py + api/system.py + `nmail install-shortcut`）

`nmail` 命令本身已会「起服务+开浏览器」，图标只需包装这一件事。应用内一键安装（设置页卡片 + API），CLI 子命令兜底。

产物：
- **Windows**：桌面 + 开始菜单 `.lnk`（PowerShell WScript.Shell 生成）。binary 渠道图标用 exe 内嵌；pip/uvx 先把启动命令写进 `%DATA_DIR%/bin/nmail.cmd`，`.lnk` 指向它，图标用随包分发的 `nmail.ico`。
- **macOS**：`/Applications/Nmail.app`（用户期望标准位置，2026-09-15 反馈后由 ~/Applications 改来；无写权限回退 `~/Applications`）（Info.plist + MacOS/nmail + MacOS/server 启动脚本 + Resources/nmail.icns）。binary 渠道脚本 exec 冻结二进制；pip/uvx exec 对应命令（uvx 绝对路径在安装时以 `shutil.which` 定死）。**Dock 图标常驻**依赖编译型存根 `assets/nmail-stub`（scripts/nmail_stub.m，通用二进制）：LaunchServices 不为纯脚本 bundle 注册应用——存根以 NSApplication 身份注册（图标/名称/⌘Q/Dock 右键 Quit），服务是其子进程；Quit → SIGTERM → server 脚本 trap 连带结束 Python；服务退出则应用随退。
- **Linux**：`~/.local/share/applications/nmail.desktop` + 图标装进 hicolor。

支撑改动：
- 图标资产随包分发：`backend/app/assets/`（ico/icns/512png 入库入 wheel，nmail.spec datas 同步打入冻结包）；gen_icons.py 产出时一并写入。
- cli.py：①`install-shortcut` / `uninstall-shortcut` 子命令（argparse 前预扫 argv，不影响既有参数面）；②**单实例探测**——8720 已有健康 Nmail（/api/health 校验）则直接开浏览器退出，不再 `find_free_port` 顺延多开（图标双击最常见场景）；③`--wait-port N` 启动参数：等端口释放后精确绑定 N（更新重启用，见 §3）。
- API：`GET/POST/DELETE /api/desktop-shortcut`（状态/安装/移除），设置页「关于」新增卡片。

## 3. 应用内更新（core/update_apply.py）

### 3.1 换身机制（binary 渠道核心）

三平台通用事实：**运行中的可执行文件可以重命名、不能删除/覆写**。

1. 下载：按平台映射 Release 资产（`nmail-windows-x64.exe` / `nmail-macos-arm64` / `nmail-linux-x64`）流式下载到 `<DATA_DIR>/update/nmail.new`，进度写入 KV；
2. 校验：GitHub API release 资产自带 `digest`（sha256），不匹配即丢弃；
3. 换身：当前二进制 rename 为 `nmail.old` → `nmail.new` os.replace 到原路径。旧进程照常跑（旧 inode），**文件已就位即「更新完成」**；
4. 重启（可选动作）：新进程带 `--wait-port <当前端口>` 启动（等旧进程退净再绑同一端口，防 find_free_port 顺延丢页面），旧进程随即退出；下次启动清理 `nmail.old`（留作回滚）；
5. 启动完成检查：进程启动早段若发现 `<DATA_DIR>/update/nmail.new` 存在（下载中途退出的残局）→ 校验通过则完成换身、失败则删除——保证「下次打开一定是新版」。
6. 就绪态自愈：启动收尾与 `GET /api/update-apply` 读取时校验——`phase=ready` 但 `staged_version` 已不比当前版本新（更新已应用）→ 归位 `idle` 并清理过期更新通知，否则「已就绪，重启即更新」提示在应用后永久悬挂；`staged_version` 三个写入点统一存不含 v 前缀的裸版本号。

附带好处：应用内下载的文件不带 quarantine 属性，换身后不再触发 Gatekeeper/SmartScreen 首次放行。

### 3.2 渠道更新动作

- `binary`：上述全流程；`ready` 后前端出「立即重启更新」。
- `pip`：后台 `{sys.executable} -m pip install --upgrade nmail-app`（运行中进程不受影响，模块已加载进内存）；`ready` 后重启动作 = spawn `[sys.executable, "-m", "app.cli", "--wait-port", N]`。
- `brew`/`winget`/`uvx`：`can_self_update=false`，设置页展示对应升级命令 + 复制按钮。

### 3.3 自动更新（用户拍板口径）

- 设置项 `auto_update_enabled`（默认**开**，设置页可关，紧挨「自动检查更新」）。
- 触发：启动后延迟静默检查一次（24h 缓存复用）+ 调度器每日兜底一次；发现新版本且本渠道可自更新 → **后台静默下载+换身，不打扰当前使用**。
- 就绪提示（文字尽量简洁，用户定）：通知中心 + 页面浮条——「新版本 vX.Y.Z 已就绪，重启即更新；下次打开自动生效。」+ 指向设置的关闭入口。
- 用户点浮条「立即重启更新」→ 走重启；叉掉浮条 → 无需任何补做（文件已换好，下次打开天然是新版）。
- `update_check_enabled`（检查开关）与 `auto_update_enabled`（装不装）分离：关检查=连对比都不做；开检查关自动=只提示不动手。

### 3.4 安全与边界

- 仅 https 到 github.com，SHA256 校验后才落位；数据目录内临时文件，失败即弃。
- 端口交接：`--wait-port` 精确回绑，浏览器页面轮询 /api/health 恢复后自动刷新。
- 无签名不变：自更新不制造新的系统放行负担。
- Windows 双机实测受限（本机 macOS）：Windows 分支按 rename 语义谨慎实现，真机验证留给用户下轮。

## 4. CI：macOS .app 发行资产（用户已同意）

release.yml macos 打包 job 追加一步：把冻结二进制包成标准 `Nmail.app`（复用 gen_icons 的 icns）打 zip 上传 Release 资产 `Nmail-macos-arm64.app.zip`——mac 用户下载解压拖进「应用程序」即用，不必等首次运行后再在设置里生成。

## 5. 实施顺序（会话内三步三提交）

1. 渠道识别 + 桌面图标（纯增量零风险）
2. 手动「立即更新」（binary/pip 换身与重启）
3. 自动更新开关 + 后台触发 + 就绪提示

## 6. Windows 无窗口化（2026-09-16 用户拍板并当轮实施）

用户反馈：Windows 双击 exe 弹出命令行黑窗，误点 X 即杀掉后端。macOS/Linux 的图标形态
（.app 存根 / .desktop `Terminal=false`）本就无终端窗口，唯 Windows 因 `console=True`
打包为控制台子系统。四项配套，三平台行为自此一致：**无窗口 · 常驻 · 有显式退出**。

1. **去黑窗**：nmail.spec `console=(sys.platform != "win32")`——仅 Windows 改窗口子系统；
   macOS/Linux/源码 `run.py` 控制台行为不变。重复双击仍走单实例探测直接开页面。
2. **日志落盘**：无控制台即无处看日志——cli.py 启动早期给 root logger 挂 RotatingFileHandler
   （`<DATA_DIR>/nmail.log`，1MB×3 滚动）；uvicorn/uvicorn.access 经 `log_config` 注入同一
   文件（dictConfig 会整体覆盖其 handlers，必须改配置而非事后挂载）。终端渠道输出不变，文件兼有。
3. **崩溃兜底**：main 薄壳捕获未捕获异常——traceback 追加进 nmail.log；Windows 冻结包再弹
   原生 MessageBoxW（零依赖），启动失败绝不静默消失。SystemExit（--help 等）直通。
4. **显式退出**：`POST /api/quit`（响应送达后延迟 0.8s `os._exit(0)`，与 restart_app 同款
   节奏；SQLite WAL 崩溃安全）+ 设置-关于「退出 Nmail」卡片（两段确认，成功提示重开方式）。
   关浏览器标签不退服——后台轮询/每日摘要要常驻，与 macOS Dock 常驻语义一致。

顺带清理同类「闪控制台」隐患：system.py `_git_commit` 冻结包直接短路（git 探测会闪窗）；
desktop.py 两处 PowerShell spawn、update_apply 重启 spawn 补齐 `CREATE_NO_WINDOW`；
pip/uvx 渠道 Windows 图标改指 `pythonw -m app.cli`（console script 与 .cmd 都会闪黑框），
pythonw 缺失时退回 .cmd 包装。

已知边界：双击启动若失败，用户看到的是错误弹窗而非日志尾部（详见日志文件）；Windows
真机验证（黑窗消失、退出按钮、崩溃弹窗）待用户下轮双机实测。
