# Nmail

AI 驱动的本地聚合邮箱客户端 · 本地优先 · 隐私自持 · MIT 开源。

你只管看信、写信、拍板；AI 负责分类、过滤噪音、预先写好草稿、每天给你汇报。数据全部留在本机，AI 用你自己的 OpenAI 兼容 API key（也可指向 Ollama / LM Studio 实现 100% 本地推理）。收发走标准 IMAP/SMTP，不自建任何邮件服务；Gmail / Outlook 已停用密码直连，Nmail 内置公开凭证支持 OAuth2 一键授权（也可自建 OAuth 应用，详见 [docs/OAuth2 使用指南.md](docs/OAuth2%20使用指南.md)）。

> 产品方案与路线图见 [docs/PRODUCT_PLAN.md](docs/PRODUCT_PLAN.md)；v0.4 改版主线见 [docs/REDESIGN_PLAN.md](docs/REDESIGN_PLAN.md)；**安装、首次使用与更新详见 [docs/INSTALL.md](docs/INSTALL.md)**；使用手册、常见问题、对外 API、隐私与安全等更多文档见 [docs/](docs/) 目录（官网 <https://nmail.whizzzest.com/docs/> 同步镜像）。当前进度：v0.3.0 已发布，v0.4 改版推进中。

## 快速开始

三种方式任选：

**① 单文件可执行（零依赖，双击即用）**

到 [Releases](../../releases) 下载对应平台文件双击运行，自动打开浏览器：Windows `nmail-windows-x64.exe` ｜ macOS (Apple Silicon) `nmail-macos-arm64` ｜ Linux `nmail-linux-x64`。
Windows 也可用 winget 安装（manifest 审核通过后可用）：`winget install nathanpenny520.Nmail`；
macOS (Apple Silicon) 用 Homebrew：`brew tap nathanpenny520/nmail https://github.com/nathanpenny520/homebrew-nmail && brew install nmail`。

- Windows 可能弹 SmartScreen 提示（未签名）：点「更多信息 → 仍要运行」
- macOS 首次运行需右键 → 打开（未公证）；Linux：`chmod +x nmail-linux-x64` 后直接运行

**② 一条命令（PyPI + uv，推荐日常使用）**

安装 [uv](https://docs.astral.sh/uv/getting-started/installation/) 后执行：

```bash
uvx --from nmail-app nmail
```

uv 自动准备 Python 运行时，无需手动安装 Python / Node。也可 `pip install nmail-app` 后直接运行 `nmail`（PyPI 发行名为 `nmail-app`——`nmail` 已被第三方占用；命令名与产品名不变）。

**③ 源码开发**

要求：Python 3.11+、Node.js 18+。

```bash
# 1. 后端依赖
python -m venv .venv
# Windows:
.venv\Scripts\pip install -r backend/requirements.txt
# macOS / Linux:
# source .venv/bin/activate && pip install -r backend/requirements.txt

# 2. 前端构建
cd frontend && npm install && npm run build && cd ..

# 3. 启动（自动打开浏览器）
python run.py
```

浏览器访问 http://127.0.0.1:8720（端口被占用会自动顺延，以控制台打印为准）。首次使用约 5 分钟：**① 添加邮箱**——设置 → 添加账号，填邮箱地址自动匹配服务器（密码型账号填授权码/应用专用密码；Gmail/Outlook 点「授权登录」一键 OAuth）；**② 配置 AI**——设置 → AI 配置 新增配置档案（Base URL + API Key + 模型名，可保存多套随时切换），点「测试连接」验证。详见 [docs/INSTALL.md](docs/INSTALL.md)。

## 自行打包

```bash
bash scripts/sync_frontend.sh                       # 构建前端并同步进 Python 包
.venv/Scripts/pip install pyinstaller               # 仅打包需要（macOS/Linux 用 .venv/bin/）
.venv/Scripts/pyinstaller nmail.spec                # 产出 dist/nmail 单文件（Windows 为 nmail.exe）
```

或只构建 wheel：`pip wheel . -w dist`。发布 PyPI 后用户即可 `uvx --from nmail-app nmail`。打 `v*` tag 时 CI（`.github/workflows/release.yml`）自动完成 wheel 发布、三平台二进制，并（配置 `HOMEBREW_TAP_TOKEN` secret 后）自动同步 Homebrew tap。

**日常发版用一条命令**：`bash scripts/release.sh 0.2.0`（自动改版本号、打 tag、盯 CI、提 winget 版本 PR，并触发官网 nmail-site 自动重建），完整说明见 [docs/RELEASE.md](docs/RELEASE.md)。

## 更新

- **应用内检查**（默认开启，可在 设置-通用 关闭）：每 24 小时向 GitHub 做一次匿名版本对比，发现新版本会在通知中心提醒；设置页可手动「检查更新」。只发送版本号，不携带任何本机数据。
- **各渠道升级**：Windows `winget upgrade nathanpenny520.Nmail` ｜ macOS `brew upgrade nmail` ｜ PyPI `uv tool upgrade nmail-app` 或 `pip install -U nmail-app` ｜ 单文件：下载新版覆盖旧 exe。
- 升级不影响数据：邮件库/密钥/配置在独立数据目录，新版本首次启动自动跑数据库迁移。

## 开发模式

```bash
# 后端热重载（Windows；macOS/Linux 用 .venv/bin/python 或激活 venv 后直接 python）
cd backend && ../.venv/Scripts/python -m uvicorn app.main:app --reload --port 8720

# 前端 dev server（/api 已代理到 8720）
cd frontend && npm run dev   # http://localhost:5173
```

## 数据与隐私

- 数据目录遵循各平台标准位置（Windows: `%LOCALAPPDATA%\Nmail` ｜ macOS: `~/Library/Application Support/Nmail` ｜ Linux: `~/.local/share/Nmail`），可用环境变量 `NMAIL_DATA_DIR` 覆盖。
- `nmail.db`：邮件库与全文索引（SQLite，WAL + FTS5）；`secrets.json`：AI API key、邮箱密码/OAuth 令牌等密钥。
- 服务仅绑定 `127.0.0.1`，不提供对外监听；AI API key 与邮箱凭据仅存本机 `secrets.json`，设置界面所见即所存（默认遮蔽）；使用云端 AI 端点时邮件正文会发送到该端点，指向本地端点（Ollama 等）则 0 外发。更多细节见 [docs/隐私与安全.md](docs/隐私与安全.md)。

## 技术栈

Python 3.11+ · FastAPI · SQLite (WAL + FTS5) · APScheduler ｜ React 18 · Vite · TypeScript · Tailwind CSS · Tiptap（写信富文本） · ECharts（摘要可视化）

## 许可证

[MIT](LICENSE)
