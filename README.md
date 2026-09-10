# Nmail

AI 驱动的本地聚合邮箱客户端 · 本地优先 · 隐私自持 · MIT 开源。

你只管看信、写信、拍板；AI 负责分类、过滤噪音、预先写好草稿、每天给你汇报。数据全部留在本机，AI 用你自己的 OpenAI 兼容 API key（也可指向 Ollama / LM Studio 实现 100% 本地推理），纯 IMAP/SMTP 客户端，不自建任何邮件服务。

> 产品方案与路线图见 [docs/PRODUCT_PLAN.md](docs/PRODUCT_PLAN.md)。当前进度：**P0 骨架**。

## 快速开始

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

浏览器访问 http://127.0.0.1:8720 —— 首次使用请到「设置」配置 AI 端点（Base URL + API Key + 模型名），点「测试连接」验证。

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
