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
| `uvx` | `sys.prefix` 位于 uv 缓存（archive-v0 / Caches/uv / uv/cache） | **uvx 命令启动器**（§2.1/§7） | 不自更新 → 图标每次启动天然最新版；提示 `uvx --refresh --from nmail-app nmail` |

## 2. 桌面图标（core/desktop.py + api/system.py + `nmail install-shortcut`）

`nmail` 命令本身已会「起服务+开浏览器」，图标只需包装这一件事。应用内一键安装（设置页卡片 + API），CLI 子命令兜底。

产物：
- **Windows**：桌面 + 开始菜单 `.lnk`（PowerShell WScript.Shell 生成），图标用随包分发的 `nmail.ico`。binary 渠道直指 exe（参数 `--idle-exit`）；**uvx 渠道走 .vbs 隐藏启动器（§2.1）**；pip 渠道 `.lnk` 直指 `pythonw -m app.cli --idle-exit`（console script 与 .cmd 都会闪黑框，pythonw 缺失退回 .cmd 包装）。
- **macOS**：`/Applications/Nmail.app`（用户期望标准位置，2026-09-15 反馈后由 ~/Applications 改来；无写权限回退 `~/Applications`）（Info.plist + MacOS/nmail + MacOS/server 启动脚本 + Resources/nmail.icns）。binary 渠道脚本 exec 冻结二进制；**uvx 渠道脚本直接跑 `uvx --from nmail-app nmail --idle-exit`（§2.1）**；pip 渠道 exec 本环境命令。**Dock 图标常驻**依赖编译型存根 `assets/nmail-stub`（scripts/nmail_stub.m，通用二进制）：LaunchServices 不为纯脚本 bundle 注册应用——存根以 NSApplication 身份注册（图标/名称/⌘Q/Dock 右键 Quit），服务是其子进程；Quit → SIGTERM → server 脚本 trap 连带结束 Python；服务退出则应用随退（空闲自动退出时 Dock 图标随之消失，符合预期）。
- **Dock 再点重开页面**（2026-09-17 补，用户反馈关标签后点图标无响应）：应用已运行时 macOS 不二次启动进程，只发 reopen 事件——此前存根未实现，点击是死点。现 `applicationShouldHandleReopen` 用默认浏览器重开页面：server 脚本经 `NMAIL_URL_FILE` 环境变量告知约定文件（bundle 内 `Contents/MacOS/url`），cli 起服后把**实际绑定地址**写入（端口顺延也正确），存根读取后 `/usr/bin/open <url>`，文件缺失兜底 8720。仅 macOS 需要——Win/Linux 图标再点即起新进程，cli 单实例探测本就重开页面（**多次点击=多个标签页**，三平台一致）。
- **Linux**：`~/.local/share/applications/nmail.desktop`（`Terminal=false` 本就无终端）+ 图标装进 hicolor，wrapper exec 启动命令。

### 2.1 uvx 渠道启动器：图标指向命令而非环境（2026-09-18 用户拍板）

此前 pip/uvx 图标把启动命令定死在**安装图标那一刻的运行环境**——uvx 的环境在 uv 缓存里，
升级换版、`uv cache prune` 后即成死链（Windows「点了没反应」的根因）。现按渠道分流
（`channel.detect_channel()`），uvx 渠道图标只依赖 uv 本体（装在 `~/.local/bin`，稳定）：

- 启动命令一律为 `uvx --from nmail-app nmail --idle-exit`（uvx 绝对路径安装时 `shutil.which` 定死，Finder/LaunchServices 无 PATH 也能跑）。
- **永远最新版**：uvx 每次启动重新解析 PyPI（实测裸命令紧跟发版，见 CHANGELOG 0.4.x）；`uv cache prune` 随便清，图标不坏。
- 三平台形态：Windows `.lnk → wscript.exe 跑 nmail.vbs`（`WshShell.Run …, 0, False` 全程无窗口，.vbs 存 UTF-16 带 BOM 防中文用户名路径乱码）；macOS 存根 .app 内 server 脚本跑 uvx 命令（reopen 机制不变）；Linux .desktop wrapper `exec` uvx 命令。
- 所有渠道图标启动一律带 `--idle-exit`（§7）——是否真退出由设置项决定，标志只是「同意空闲退出」的开关。
- pip/binary 渠道维持原方案（环境稳定，无死链问题），仅补 `--idle-exit` 参数。
- 已知取舍：uvx 启动需解析 PyPI，**离线时图标启动会失败**（联网自愈）；启动比直跑慢约 0.5–1s。

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
   ~~关浏览器标签不退服~~——2026-09-18 用户拍板推翻为**空闲自动退出**（图标启动时生效，§7）；
   终端裸跑 `nmail` 行为不变（Ctrl+C 退出、不自动退），「退出 Nmail」卡片保留作显式停服入口。

顺带清理同类「闪控制台」隐患：system.py `_git_commit` 冻结包直接短路（git 探测会闪窗）；
desktop.py 两处 PowerShell spawn、update_apply 重启 spawn 补齐 `CREATE_NO_WINDOW`；
pip/uvx 渠道 Windows 图标改指 `pythonw -m app.cli`（console script 与 .cmd 都会闪黑框），
pythonw 缺失时退回 .cmd 包装。

已知边界：双击启动若失败，用户看到的是错误弹窗而非日志尾部（详见日志文件）；Windows
真机验证（黑窗消失、退出按钮、崩溃弹窗）待用户下轮双机实测。

## 7. 空闲自动退出 + 首跑横幅（2026-09-18 用户拍板）

用户模型：**「点图标=开标签页，关标签页=后台自己退」**。后台永驻（§6 旧语义）改为
图标启动时默认空闲自动退出；终端裸跑不受影响。

### 7.1 机制（core/idle_exit.py + cli `--idle-exit` + main 中间件/看门狗）

- **活动信号 = HTTP 请求**。前端常驻轮询（通知铃 15s、目录树 60s、列表 20s）即天然心跳；
  无需新的长连接。ASGI 中间件记账：请求开始 `in_flight+1`、结束 `in_flight-1` 并刷新
  `last_activity`——长流式请求（AI 对话流）在途期间 `in_flight>0`，不会被误杀。
- **看门狗**：lifespan 内 asyncio 任务，每 `max(2, min(15, 阈值/4))` 秒查一次——
  `in_flight==0` 且空闲超阈值 → 日志 + 置 uvicorn `should_exit=True` 优雅退出
  （cli 改用 `uvicorn.Server` 对象形态注入退出钩子；跨平台，不走 os.kill）。
  触发后走正常 lifespan 收尾（scheduler.shutdown），下次启动 UID 增量同步自动续传。
- **阈值 90s**（用户确认）：比 60s 高是给浏览器后台标签定时器节流留余量（隐藏标签
  最低 1 次/分钟，恰好 60s 会误杀还开着的标签）。关掉最后一个标签后约 1.5 分钟退出。
- **开关三层**（互不打架）：
  | 层 | 语义 |
  |---|---|
  | cli `--idle-exit`（裸 flag） | 「本次启动同意空闲退出」，秒数读设置项——图标启动一律带它 |
  | 设置项 `idle_exit_enabled`（默认开） | 图标启动的实际开关；看门狗每 tick 重读，改动即时生效 |
  | cli `--idle-exit N`（带值，N=0 关） | 显式覆盖秒数/关闭，测试与高级用户用 |
  - 终端裸跑 `nmail`（无 flag）**完全不变**：永不空闲退出——总管家/CLI/脚本自动化零风险。
- 退出时通知：不打扰，日志可查（nmail.log 记「空闲 Ns 自动退出」）。

### 7.2 首跑横幅（弹一次）

- 首次打开页面且桌面图标未安装时，App 底部浮出一次性横幅：「在桌面创建 Nmail 图标，
  下次双击直达」+「立即安装」/「关闭」。**显示即记**（KV `desktop_banner_seen`，
  POST /api/desktop-shortcut/banner-seen）——只弹这一次，不纠缠；安装/移除动作也顺手置位。
- 前端挂 App 级固定定位卡片，不嵌布局；`GET /api/desktop-shortcut` 响应带 `banner`
  布尔（未安装且未看过）供前端判断。

### 7.3 验证边界

- macOS 全链路本机实测（uvx 真环境装图标、点图标开标签、重复点击、空闲退出、Dock 消失）。
- Windows 真机验证（.vbs 无窗口启动、多次点击多开标签、空闲退出）留给用户双机实测；
  .vbs 编码（UTF-16 BOM）与 wscript 路径按已知语义谨慎实现。
