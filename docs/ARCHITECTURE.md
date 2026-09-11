# Nmail 架构（docs/ARCHITECTURE.md）

> 本文档随代码同步维护：接口/模块/数据表有变化时，同一提交内更新此处。

## 总体形态

单机单进程：`python run.py` 启动 FastAPI（仅绑定 127.0.0.1），托管 `/api/*` 与 `frontend/dist` 静态产物（含 SPA 历史路由回退）。浏览器是唯一 UI，无原生 GUI、无系统托盘、无 OS 独有 API。

```
浏览器 (React SPA)
   │  REST /api/* + SSE (text/event-stream)
   ▼
FastAPI (uvicorn, 127.0.0.1:8720)
   ├─ api/          路由层（pydantic 校验，错误转中文 HTTPException）
   ├─ core/         邮件核心（IMAP/SMTP/同步/流水线/HTML 消毒）
   ├─ ai/           LLM 任务（OpenAI 兼容，base_url 可指向本地模型）
   ├─ scheduler/    APScheduler 后台线程（60s tick：轮询收信 + 每日摘要）
   └─ db/           SQLite(WAL) + FTS5(trigram) + 版本化迁移
   ▼
本地数据目录（platformdirs；Windows: %LOCALAPPDATA%/Nmail）
   ├─ nmail.db      全部业务数据
   ├─ secrets.json  AI key、各账号授权码（永不回传前端）
   └─ accounts/<id>/attachments/  附件落盘
```

## 后端模块（backend/app/）

| 模块 | 职责 | 要点 |
|------|------|------|
| `main.py` | 入口、lifespan（迁移+调度器启停）、SPAStaticFiles 回退 | 路由先于静态挂载注册 |
| `api/system.py` | `/api/health` | — |
| `api/settings.py` | 设置 KV 读写 + AI 端点测试 | 含 `ui_font/body_font` 档位校验；key 只回传 `*_set` 布尔 |
| `api/accounts.py` | 账号 CRUD/测试/同步/文件夹/服务商预设/语气学习 | 授权码存 `secrets.json`（key=`account_pwd:{id}`）；PATCH 支持改密码与 AI 权限 |
| `api/emails.py` | 列表/搜索/详情/操作/发送/附件下载 | 搜索：≥3 字走 FTS5 trigram，<3 字回退 LIKE；详情返回消毒后 HTML（`?images=1` 放行远程图+内联 cid） |
| `api/drafts.py` | 待审草稿：列表/修改/发送(approve)/丢弃/恢复/彻底删除/重新生成 | approve 走 SMTP 并带 `In-Reply-To`；原文自动标已读 |
| `api/ai.py` | 单邮件问答、总管家问答（会话持久化）、写作辅助、用量、AI 整理 | 问答/总管家均有 `/stream` SSE 版本，中途错误以 `{"error":...}` 事件下发 |
| `api/notifications.py` | 通知中心 | — |
| `api/sender_lists.py` | 白/黑名单（邮箱或 @域名） | 管线中零成本先过滤 |
| `api/chats.py` | 总管家会话持久化（chat_sessions/messages） | P4 新增 |
| `api/digest.py` | 每日摘要查看/手动生成 | — |
| `core/providers.py` | 19 个服务商预设（含中文授权码提示） | 按域名自动匹配 |
| `core/imap_client.py` | IMAP/SMTP 封装 | 网易系需 IMAP ID 命令；SMTP 端口 465=SSL/587=STARTTLS；`append_sent` 发送后归档 |
| `core/sync.py` | UID 增量同步 | 首同步限 30 天；UIDVALIDITY 变化自愈；登录失败→`auth_error`+一次性通知；同步完成后触发 AI 流水线 |
| `core/pipeline.py` | 白/黑名单 → AI 批量分类 → 营销自动归档 → 生成草稿 → 通知 | AI 未配置诚实降级；批量 20 封/请求 |
| `core/mail_html.py` | nh3 白名单消毒 + 远程图片拦截 + cid 内联 + Markdown→HTML | 两层防护：消毒在前、图片控制在后 |
| `ai/llm.py` | OpenAI 兼容客户端（流式 `iter_deltas` / 非流式） | connect 5s / 读写 15s 快速失败 |
| `ai/tasks.py` | 分类/草稿/问答/写作/摘要综述/Tone DNA + 用量日志 | 所有调用写 `ai_logs` |
| `ai/digest.py` | 每日摘要：统计（零成本 SQL）+ AI 综述（一次调用） | 当天已生成则复用 |
| `ai/prompts.py` | 全部提示词模板 | 结构化输出要求纯 JSON，`_extract_json` 容错解析 |
| `db/database.py` | 连接（WAL）+ `MIGRATIONS` 版本化迁移 + KV 设置 | 迁移只追加不改历史 |
| `scheduler.py` | 每 60s tick：到期账号增量同步 + 摘要到点生成 | 「检查到期」而非每账号注册任务，改设置无需重建调度 |

## 前端（frontend/src/）

| 部分 | 内容 |
|------|------|
| `pages/` | InboxPage/ArchivedPage（共用 MailBrowser，分屏+可拖拽）、DraftsPage（草稿分屏）、DigestPage（ECharts 摘要）、ManagerPage（AI 总管家，SSE 流式）、SettingsPage |
| `components/` | MailBrowser（三态：列表/分屏/全屏）、EmailReader（消毒 iframe+操作栏+AI 面板）、HtmlMail（sandbox=allow-same-origin，高度自适应+zoom 注入）、ComposeModal（Markdown+AI 辅助）、AddAccountModal、AiPanel、NotificationBell（浏览器通知）、Markdown（react-markdown+gfm） |
| `api/` | `client.ts`（REST 封装，FormData 不设 JSON 头）、`stream.ts`（SSE 解析，错误可见） |
| 字号系统 | `index.css` 三档 CSS 变量（`--fs-xs/sm/md/lg`），`<html data-font>` 切换（FontApplier 读设置应用）；`t-xs/sm/md/lg` 工具类；正文字号独立经 iframe zoom 注入 |

## 数据表（nmail.db）

`settings`(KV) · `notifications` · `accounts`(含 ai_permission/tone_dna) · `emails`(含分类/needs_reply/archived_local) · `attachments` · `sync_state`(uid/uidvalidity) · `emails_fts`(trigram) · `drafts`(pending/sent/discarded) · `ai_logs`(全量 AI 用量) · `sender_lists` · `digest_history` · `chat_sessions`/`chat_messages`（P4 会话持久化）

迁移版本：v1 基础表 → v2 邮件核心+FTS → v3 AI 层 → v4 摘要+ToneDNA → v5 会话持久化

## 关键流程

### 同步管线（每次轮询/手动收信）
```
UID 增量拉取 → 落库+附件落盘 → 白名单(留收件箱)/黑名单(直接归档)
→ AI 批量分类(category/importance/needs_reply/reason)
→ 营销(promo)自动本地归档 → 需回复且账号权限≥draft_review → 生成草稿+通知
```

### 安全模型
- HTML 邮件：nh3 白名单 → 远程图默认拦截（计数）→ 前端 sandbox iframe（仅 allow-same-origin，无脚本）
- 发信：multipart/alternative（Markdown→HTML + 纯文本兜底）；草稿 approve 带 In-Reply-To 并归档 Sent
- 密钥：本地 `secrets.json`（POSIX chmod 600）；AI key 不回传；服务仅 127.0.0.1
