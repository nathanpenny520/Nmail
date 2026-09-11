# Nmail

AI 驱动的本地聚合邮箱客户端 · 本地优先 · 隐私自持 · MIT 开源。

你只管看信、写信、拍板；AI 负责分类、过滤噪音、预先写好草稿、每天给你汇报。数据全部留在本机，AI 用你自己的 OpenAI 兼容 API key（也可指向 Ollama / LM Studio 实现 100% 本地推理），纯 IMAP/SMTP 客户端，不自建任何邮件服务。

> 产品方案与路线图见 [docs/PRODUCT_PLAN.md](docs/PRODUCT_PLAN.md)。当前进度：**P4 打磨**。

## 快速开始

三种方式任选：

**① 单文件可执行（零依赖，双击即用）**

到 [Releases](../../releases) 下载对应平台文件（Windows: `nmail-windows-x64.exe`）双击运行，自动打开浏览器。

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

浏览器访问 http://127.0.0.1:8720 —— 首次使用请到「设置 → AI 配置」新增配置档案（Base URL + API Key + 模型名，可保存多套随时切换），点「测试连接」验证。

## 自行打包

```bash
bash scripts/sync_frontend.sh                       # 构建前端并同步进 Python 包
.venv/Scripts/pip install pyinstaller               # 依赖已在 requirements 内
.venv/Scripts/pyinstaller nmail.spec                # 产出 dist/nmail 单文件（Windows 为 nmail.exe）
```

或只构建 wheel：`pip wheel . -w dist`。发布 PyPI 后用户即可 `uvx nmail`。打 `v*` tag 时 CI（`.github/workflows/release.yml`）自动完成 wheel 发布与三平台二进制。

## 开发模式

```bash
# 后端热重载
cd backend && ../.venv/Scripts/python -m uvicorn app.main:app --reload --port 8720

# 前端 dev server（/api 已代理到 8720）
cd frontend && npm run dev   # http://localhost:5173
```

## 数据与隐私

- 数据目录遵循各平台标准位置（Windows: `%LOCALAPPDATA%\Nmail`），可用环境变量 `NMAIL_DATA_DIR` 覆盖。
- `nmail.db`：邮件与索引（SQLite，后续版本）；`secrets.json`：AI API key 等密钥。
- 服务仅绑定 `127.0.0.1`；API key 不回传前端；使用云端 AI 端点时邮件正文会发送到该端点，指向本地端点（Ollama 等）则 0 外发。

## 技术栈

Python 3.11+ · FastAPI · SQLite (WAL + FTS5) · APScheduler ｜ React 18 · Vite · TypeScript · Tailwind CSS · ECharts（摘要可视化）

## 许可证

[MIT](LICENSE)
