# Nmail

[English](README.md) ｜ 中文

AI 驱动的本地聚合邮箱客户端 · 本地优先 · 隐私自持 · MIT 开源。

<p align="center">
  <img src="assets/Nmail-demo.gif" alt="Nmail 界面演示" width="760">
</p>

你只管看信、写信、拍板；AI 负责分类、过滤噪音、预先写好草稿、每天给你汇报。数据全部留在本机，AI 用你自己的 OpenAI 兼容 API key（也可指向 Ollama / LM Studio 实现 100% 本地推理）。收发走标准 IMAP/SMTP，不自建任何邮件服务；Gmail / Outlook 已停用密码直连，Nmail 内置公开凭证支持 OAuth2 一键授权（也可自建 OAuth 应用，详见 [docs/OAuth2 使用指南.md](docs/OAuth2%20使用指南.md)）。

> 安装、首次使用与更新详见 **[docs/INSTALL.md](docs/INSTALL.md)**；使用手册、FAQ、对外 API、隐私与安全等更多文档见 [docs/](docs/)（官网 <https://nmail.whizzzest.com/docs/> 同步镜像）。当前版本 **v0.4.x**（变更见 [docs/CHANGELOG.md](docs/CHANGELOG.md)）。

## 快速开始

**① 单文件可执行（零依赖，双击即用）**

到 [Releases](../../releases) 下载对应平台文件双击运行，自动打开浏览器：Windows `nmail-windows-x64.exe` ｜ macOS (Apple Silicon) `nmail-macos-arm64` ｜ Linux `nmail-linux-x64`。Windows 也可 `winget install nathanpenny520.Nmail`（manifest 审核通过后可用）；macOS (Apple Silicon) 用 Homebrew（注意须用带 tap 前缀的全名，core 仓库有同名无关软件）：`brew tap nathanpenny520/nmail https://github.com/nathanpenny520/homebrew-nmail && brew trust nathanpenny520/nmail && brew install nathanpenny520/nmail/nmail`。

- Windows 可能弹 SmartScreen 提示（未签名）：点「更多信息 → 仍要运行」
- macOS 首次运行需右键 → 打开（未公证）；Linux：`chmod +x nmail-linux-x64` 后直接运行

**② 一条命令（PyPI + uv，推荐日常使用）**

安装 [uv](https://docs.astral.sh/uv/getting-started/installation/) 后执行：

```bash
uvx --from nmail-app nmail
```

这条命令就是启动命令，每次打开 Nmail 都运行它：重跑同一条即再次使用（包已缓存，第二次起秒级启动），升级跑 `uvx --refresh --from nmail-app nmail`。也可常驻安装 `uv tool install nmail-app`（之后任意目录敲 `nmail`，升级 `uv tool upgrade nmail-app`）或 `pip install nmail-app`（PyPI 发行名为 `nmail-app`——`nmail` 已被第三方占用；命令名与产品名不变）。

## 首次使用（约 5 分钟）

1. **添加邮箱**：设置 → 添加账号，填邮箱地址自动匹配服务器（密码型账号填授权码/应用专用密码；Gmail/Outlook 点「授权登录」一键 OAuth）。
2. **配置 AI**：设置 → AI 配置 新增配置档案（Base URL + API Key + 模型名，可保存多套随时切换），点「测试连接」验证。

浏览器访问 http://127.0.0.1:8720（端口被占用自动顺延，以控制台打印为准）。更多细节见 [docs/INSTALL.md](docs/INSTALL.md)。

## 更新

- **应用内检查**（默认开启，可在 设置-通用 关闭）：每 24 小时匿名对比 GitHub 版本号（不带任何本机数据），新版本在通知中心提醒；设置页可手动检查。
- **各渠道升级**：uvx `uvx --refresh --from nmail-app nmail` ｜ 常驻 `uv tool upgrade nmail-app` ｜ pip `pip install -U nmail-app` ｜ Windows `winget upgrade nathanpenny520.Nmail` ｜ macOS `brew upgrade nathanpenny520/nmail/nmail` ｜ 单文件：下载新版覆盖。
- **升级不丢数据**：邮件库/密钥/配置在独立数据目录，新版本首次启动自动跑数据库迁移。

## 开发

要求 Python 3.11+、Node.js 18+。

```bash
# 源码运行
python -m venv .venv
# Windows:
.venv\Scripts\pip install -r backend/requirements.txt
# macOS / Linux:
# source .venv/bin/activate && pip install -r backend/requirements.txt
cd frontend && npm install && npm run build && cd ..
python run.py                    # 启动（自动打开浏览器）

# 后端热重载（Windows；macOS/Linux 用 .venv/bin/python 或激活 venv 后直接 python）
cd backend && ../.venv/Scripts/python -m uvicorn app.main:app --reload --port 8720

# 前端 dev server（/api 已代理到 8720）
cd frontend && npm run dev       # http://localhost:5173
```

打包与发版一条命令：`bash scripts/release.sh <版本>`（详见 [docs/RELEASE.md](docs/RELEASE.md)）。

## 数据与隐私

- 数据目录在各平台标准位置（Windows: `%LOCALAPPDATA%\Nmail` ｜ macOS: `~/Library/Application Support/Nmail` ｜ Linux: `~/.local/share/Nmail`），可用环境变量 `NMAIL_DATA_DIR` 覆盖；`nmail.db` 为邮件库与全文索引（SQLite，WAL + FTS5），`secrets.json` 存 AI key 与邮箱密码/OAuth 令牌。
- 服务仅绑定 `127.0.0.1`，不提供对外监听；密钥仅存本机 `secrets.json`，设置界面所见即所存（默认遮蔽）。使用云端 AI 端点时邮件正文会发送到该端点，指向本地端点（Ollama 等）则 0 外发。更多见 [docs/隐私与安全.md](docs/隐私与安全.md)。

## 技术栈

Python 3.11+ · FastAPI · SQLite (WAL + FTS5) · APScheduler ｜ React 18 · Vite · TypeScript · Tailwind CSS · Tiptap（写信富文本） · ECharts（摘要可视化）

## 许可证

[MIT](LICENSE)
