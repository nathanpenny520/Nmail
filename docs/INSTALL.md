# 安装与更新指南（docs/INSTALL.md）

Nmail 是本地优先的单机应用：任何安装方式都只在本机跑一个服务 + 浏览器界面，邮件数据与密钥全部留在本机，不连任何云端服务（AI 端点除外，且用你自己的 key）。

## 安装方式（按人群四选一）

| 方式 | 适合 | 平台 | 命令 |
|---|---|---|---|
| ① 单文件可执行 | 大多数用户（推荐） | Win / macOS / Linux | 到 [Releases](https://github.com/nathanpenny520/Nmail/releases) 下载，双击运行 |
| ② winget | Windows 想要免维护升级 | Windows | `winget install nathanpenny520.Nmail` |
| ③ Homebrew | macOS (Apple Silicon) | macOS | `brew tap nathanpenny520/nmail https://github.com/nathanpenny520/homebrew-nmail && brew trust nathanpenny520/nmail && brew install nathanpenny520/nmail/nmail` |
| ④ uvx / pip | 命令行熟手，不想手动换文件 | 全平台 | `uvx --from nmail-app nmail` |
| ⑤ 源码开发 | 开发者 | 全平台 | 见 [README 开发章节](../README.md) |

> PyPI 发行名为 `nmail-app`（`nmail` 在 PyPI 已被无关项目占用）；产品名与命令名都是 Nmail / `nmail`，不受影响。

> **启动与再次使用（③ Homebrew / ④ uvx 通用）**：安装完成即得到启动命令——Homebrew 装完在终端敲 `nmail`；uvx 则运行 `uvx --from nmail-app nmail`（这条本身就是启动命令，在哪运行都一样，不在当前目录留任何文件）。启动后出现控制台窗口（程序本体，显示日志），几秒后浏览器自动打开 `http://127.0.0.1:8720`（端口被占用会自动顺延，以控制台打印为准）。退出：关闭窗口或 `Ctrl+C`。**下次使用：再运行同一条启动命令即可**（包已在本地缓存，第二次起秒级启动）；不产生系统残留，介意缓存可用 `uv cache clean` 清空。首次配置见下文「首次使用」，升级方式见下文「更新」。

### ① 单文件可执行

到 [Releases](https://github.com/nathanpenny520/Nmail/releases) 下载对应文件并**双击运行**：

| 文件 | 平台 |
|---|---|
| `nmail-windows-x64.exe` | Windows 10/11 x64 |
| `nmail-macos-arm64` | macOS (Apple Silicon) |
| `nmail-linux-x64` | Linux x64 |

**macOS 更推荐 [Nmail.app 压缩包](https://github.com/nathanpenny520/Nmail/releases/latest/download/nmail-macos-arm64.app.zip)**（v0.4.2 起）：解压，把 Nmail.app 拖进「应用程序」即装——Dock 图标、⌘Q 退出。首次打开需右键 → 打开（未公证）。

- **运行后会发生什么**：不弹任何命令行黑窗（Windows 双击即纯后台运行），几秒后浏览器自动打开 `http://127.0.0.1:8720`。端口被占用会自动顺延，以浏览器实际打开的地址为准。
- **退出**：设置-关于 →「退出 Nmail」（macOS .app 可 ⌘Q；终端直跑二进制时 Ctrl+C）。关闭浏览器标签不退出——后台同步与每日摘要在服务常驻期间照常工作。
- **日志**：程序日志写入数据目录 `nmail.log`（见下节），启动异常会弹窗提示日志位置。
- **Windows 首次运行**：SmartScreen 弹「已保护你的电脑」（未签名）→ 点「更多信息 → 仍要运行」。首次启动慢几秒是单文件自解压，属正常。若任务栏图标没换成专属图标，是 Windows 图标缓存：重命名一次 exe 或 `ie4uinit -show`。
- **macOS 首次运行**：先 `chmod +x nmail-macos-arm64`，然后**右键 → 打开**（不能直接双击，Gatekeeper 拦未公证签名）；或 `xattr -dr com.apple.quarantine nmail-macos-arm64` 后正常双击。
- **Linux 首次运行**：`chmod +x nmail-linux-x64` 后终端运行。

### ② winget（Windows）

```powershell
winget install nathanpenny520.Nmail   # 安装（manifest 审核中：microsoft/winget-pkgs#432990）
winget upgrade nathanpenny520.Nmail   # 升级
winget uninstall nathanpenny520.Nmail # 卸载
```

### ③ Homebrew（macOS Apple Silicon）

```bash
brew tap nathanpenny520/nmail https://github.com/nathanpenny520/homebrew-nmail
brew trust nathanpenny520/nmail            # Homebrew 7 起第三方 tap 须显式信任
brew install nathanpenny520/nmail/nmail    # 升级: brew upgrade nathanpenny520/nmail/nmail；卸载: brew uninstall nathanpenny520/nmail/nmail
```

> **必须用全名**：core 仓库已有同名无关软件，裸 `brew install nmail` 装到的是它。**`brew trust` 为 Homebrew 7 起必需**；未信任时 `brew tap` 报「invalid syntax」并删克隆，实为信任问题。

Linux 用户请用方式 ④（tap 不分发 Linux 二进制）。

### ④ uvx / pip（全平台，推荐命令行用户）

```bash
# 装 uv（一次即可，见 https://docs.astral.sh/uv/getting-started/installation/）
uvx --from nmail-app nmail           # 无需安装，直接运行；uv 自动管理 Python
# 或常驻安装
uv tool install nmail-app && nmail   # 升级: uv tool upgrade nmail-app
pip install nmail-app                # 升级: pip install -U nmail-app；卸载: pip uninstall nmail-app
```

> ⚠️ 常见笔误：`uvx -from nmail-app nmail`（单横线）会报 `Failed to read --find-links directory …/rom`
> ——单横线的 `-f` 是 `--find-links` 缩写。必须用**双横线 `--from`**；嫌容易错就用上面的 `uv tool install`。

### ⑤ 源码开发

见 [README「从源码运行」](../README.md)：venv + `pip install -r backend/requirements.txt` + 前端构建 + `python run.py`。

## 首次使用（约 5 分钟）

1. **添加邮箱**：设置 → 添加账号。填邮箱地址即可自动匹配服务器（内置 20 个预设 + 未收录域名自动探测），密码填**授权码/应用专用密码**（不是邮箱登录密码，各服务商获取方式见页面内中文提示）。
2. **配置 AI**：设置 → AI 配置 → 新增配置。填 Base URL + API Key + 模型名（DeepSeek / OpenAI / OpenRouter 或本地 Ollama、LM Studio 均可），点「测试连接」验证，可保存多套随时切换；对话界面可临时换模型。
3. **可选**：轮询间隔、每日摘要时间、字号，都在 设置-通用。

## 更新

- **应用内检查**（默认开启，设置-关于 可关）：每 24 小时向 GitHub 做一次匿名版本号对比（请求只带 UA，不含任何本机数据），发现新版本会在通知中心提醒；设置页可手动「检查更新」。
- **应用内更新**（v0.4.2 起，默认开启可关）：单文件版与 pip 安装在发现新版本后自动在后台下载并就位，提示「重启即更新，下次打开自动生效」，设置-关于 可一键重启或关掉自动安装；Homebrew/winget/uvx 由包管理器管理，应用内会给出对应升级命令。
- **桌面图标**（设置-关于 一键安装，或命令行 `nmail install-shortcut`）：Windows 在桌面+开始菜单创建快捷方式，macOS 在「应用程序」生成 Nmail.app，Linux 创建 .desktop 启动器——双击即用，无需再敲命令。
- **升级命令**：`winget upgrade nathanpenny520.Nmail` ｜ `brew upgrade nathanpenny520/nmail/nmail` ｜ `uv tool upgrade nmail-app` ｜ uvx：`uvx --refresh --from nmail-app nmail`（uvx 首次运行取最新版、之后沿用缓存版本，新发布不会自动跟上，`--refresh` 刷新缓存即取最新）｜ 单文件：下载新版覆盖旧文件（或直接用应用内更新）。
- **升级不丢数据**：邮件库、密钥、配置在独立数据目录（见下），新版本首次启动自动执行数据库迁移。

## 数据位置、备份与卸载

| 平台 | 数据目录 |
|---|---|
| Windows | `%LOCALAPPDATA%\Nmail` |
| macOS | `~/Library/Application Support/Nmail` |
| Linux | `~/.local/share/Nmail` |

- 内容：`nmail.db`（邮件/索引/会话等全部业务数据）、`secrets.json`（邮箱授权码与 AI key，请妥善保管）、`accounts/<id>/attachments/`（附件）、`nmail.log`（运行日志，排查问题先看这里）。
- **备份**：整个数据目录拷走即可（可用环境变量 `NMAIL_DATA_DIR` 指到自选位置，如移动硬盘）。
- **彻底卸载**：删除程序本体（winget/brew uninstall 或删 exe）+ 删除上表数据目录。
