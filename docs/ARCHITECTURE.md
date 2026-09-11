# Nmail 架构（docs/ARCHITECTURE.md）

> 本文档随代码同步维护：接口/模块/数据表有变化时，同一提交内更新此处。

## 总体形态

单机单进程：`python run.py`（源码开发）/ 控制台脚本 `nmail`（PyPI 安装）/ 单文件可执行（PyInstaller 冻结）三种入口启动 FastAPI（仅绑定 127.0.0.1），托管 `/api/*` 与前端静态产物（含 SPA 历史路由回退）。前端目录按运行形态解析：wheel 内 `app/static` → 冻结资源 `_MEIPASS/app/static` → 源码 `frontend/dist`。浏览器是唯一 UI，无原生 GUI、无系统托盘、无 OS 独有 API。

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
| `api/system.py` | `/api/health`、`/api/update-check`（24h 节流，force 可立即检查） | — |
| `api/settings.py` | 通用设置 KV 读写 + AI 端点测试 | 含 `ui_font/body_font` 档位校验；AI 配置已移至 profiles；`/api/ai/test` 字段省略时回退激活档案 |
| `api/accounts.py` | 账号 CRUD/测试/探测/同步/文件夹/服务商预设/语气学习 | 授权码存 `secrets.json`（key=`account_pwd:{id}`）；`POST /accounts/probe` 未收录域名自动探测 |
| `api/emails.py` | 列表/搜索/详情/操作/发送/附件下载 | 搜索：≥3 字走 FTS5 trigram，<3 字回退 LIKE；详情返回消毒后 HTML（`?images=1` 放行远程图+内联 cid） |
| `api/drafts.py` | 待审草稿：列表/修改/发送(approve)/丢弃/恢复/彻底删除/重新生成 | approve 走 SMTP 并带 `In-Reply-To`；原文自动标已读 |
| `api/user_drafts.py` | 写信工作台草稿：创建/列表/读取/修改/删除/发送 | 前端防抖 PATCH 自动保存；发送前 `sanitize_outgoing_html` 消毒 + 派生纯文本 + 套基础样式外层；回复草稿带 `In-Reply-To`（软引用邮件 id） |
| `api/ai.py` | 单邮件问答、总管家问答（会话持久化）、写作辅助、用量、AI 整理 | 问答/总管家均有 `/stream` SSE 版本，中途错误以 `{"error":...}` 事件下发；对话/写作接受 `profile_id` 临时切换档案 |
| `api/notifications.py` | 通知中心 | — |
| `api/sender_lists.py` | 白/黑名单（邮箱或 @域名） | 管线中零成本先过滤 |
| `api/chats.py` | 总管家会话持久化（chat_sessions/messages）：列表/消息/置顶/重命名/删除 | 列表 置顶>updated_at 倒序；删除级联；`append_message` 供 ai.py 落库复用 |
| `api/profiles.py` | AI 配置档案 CRUD/激活/模型列表代理 | 密钥语义：省略=不变、空串=清除；响应只含 `api_key_set` 布尔 |
| `api/digest.py` | 每日摘要查看/手动生成 | — |
| `core/providers.py` | 20 个服务商预设（含中文授权码提示）+ 未收录域名自动探测 | 按域名自动匹配；`probe_server()`：autoconfig 标准接口 → 常见主机名 993/465 并发试连（只收加密端口） |
| `core/imap_client.py` | IMAP/SMTP 封装 | 网易系需 IMAP ID 命令；SMTP 端口 465=SSL/587=STARTTLS；`append_sent` 发送后归档 |
| `core/sync.py` | UID 增量同步 | 首同步限 30 天；UIDVALIDITY 变化自愈；登录失败→`auth_error`+一次性通知；同步完成后触发 AI 流水线 |
| `core/pipeline.py` | 白/黑名单 → AI 批量分类 → 营销自动归档 → 生成草稿 → 通知 | AI 未配置诚实降级；批量 20 封/请求 |
| `core/mail_html.py` | nh3 白名单消毒 + 远程图片拦截 + cid 内联 + Markdown→HTML | 两层防护：消毒在前、图片控制在后；另供发件方向 `sanitize_outgoing_html`（放行 data: 内嵌图）与 `html_to_plain_text`/`wrap_email_body_html` |
| `core/update_check.py` | 应用内更新检查：GitHub Releases 对比 + 通知中心提醒 | 仅匿名 GET api.github.com（UA=Nmail/版本），24h 缓存；开关 `update_check_enabled`；按 ref_id=版本去重，升级后自动清理旧提醒 |
| `ai/llm.py` | OpenAI 兼容客户端（流式 `iter_deltas` / 非流式） | connect 5s / 读写 15s 快速失败 |
| `ai/profiles.py` | AI 配置档案存储/解析（settings JSON + secrets 分离） | 解析顺序：显式 profile_id > 激活档案 > 第一个；旧单配置首读自动迁移为「默认」档案 |
| `ai/tasks.py` | 分类/草稿/问答/写作/摘要综述/Tone DNA + 用量日志 | 所有任务接受 `profile_id` 并经 `_ai_config()` 按档案解析；所有调用写 `ai_logs` |
| `ai/digest.py` | 每日摘要：统计（零成本 SQL）+ AI 综述（一次调用） | 当天已生成则复用 |
| `ai/prompts.py` | 全部提示词模板 | 结构化输出要求纯 JSON，`_extract_json` 容错解析 |
| `db/database.py` | 连接（WAL）+ `MIGRATIONS` 版本化迁移 + KV 设置 | 迁移只追加不改历史 |
| `scheduler.py` | 每 60s tick：到期账号增量同步 + 摘要到点生成 | 「检查到期」而非每账号注册任务，改设置无需重建调度 |

## 前端（frontend/src/）

| 部分 | 内容 |
|------|------|
| `pages/` | InboxPage/ArchivedPage（共用 MailBrowser，分屏+可拖拽）、ComposePage（写信工作台，多标签）、DraftsPage（草稿分屏）、DigestPage（ECharts 摘要）、ManagerPage（AI 总管家，SSE 流式）、SettingsPage |
| `components/` | MailBrowser（三态：列表/分屏/全屏）、EmailReader（消毒 iframe+操作栏+AI 面板）、HtmlMail（sandbox=allow-same-origin+allow-popups，外链新标签打开，ResizeObserver 高度自适应+zoom 注入）、compose/（写信工作台：ComposeContext 多标签状态中枢挂 App 级、ComposeForm 字段+附件+AI 辅助+自动保存、RichEditor=TipTap v3 富文本、quote.ts 回复/转发引用）、AddAccountModal、AiPanel、NotificationBell（浏览器通知）、Markdown（react-markdown+gfm） |
| `api/` | `client.ts`（REST 封装，FormData 不设 JSON 头）、`stream.ts`（SSE 解析，错误可见） |
| 字号系统 | `index.css` 三档 CSS 变量（`--fs-xs/sm/md/lg`），`<html data-font>` 切换（FontApplier 读设置应用）；`t-xs/sm/md/lg` 工具类；正文字号独立经 iframe zoom 注入 |

## 数据表（nmail.db）

`settings`(KV) · `notifications` · `accounts`(含 ai_permission/tone_dna) · `emails`(含分类/needs_reply/archived_local) · `attachments` · `sync_state`(uid/uidvalidity) · `emails_fts`(trigram) · `drafts`(pending/sent/discarded) · `user_drafts`(写信工作台草稿，editing/sent) · `ai_logs`(全量 AI 用量) · `sender_lists` · `digest_history` · `chat_sessions`/`chat_messages`（P4 会话持久化）

迁移版本：v1 基础表 → v2 邮件核心+FTS → v3 AI 层 → v4 摘要+ToneDNA → v5 会话持久化 → v7 date_sort 排序修复 → v8 user_drafts

## 关键流程

### 同步管线（每次轮询/手动收信）
```
UID 增量拉取 → 落库+附件落盘 → 白名单(留收件箱)/黑名单(直接归档)
→ AI 批量分类(category/importance/needs_reply/reason)
→ 营销(promo)自动本地归档 → 需回复且账号权限≥draft_review → 生成草稿+通知
```

### 安全模型
- HTML 邮件：nh3 白名单（http(s) 链接强制 target=_blank + rel=noopener）→ 远程图默认拦截（计数）→ 前端 sandbox iframe（allow-same-origin+allow-popups-to-escape-sandbox，无脚本；外链点击在新标签由浏览器正常打开，不在 iframe 内导航）
- 发信：multipart/alternative（写信工作台：TipTap HTML 经 `sanitize_outgoing_html` 白名单消毒后直发 + 派生纯文本；旧 `/emails/send` 保留 Markdown→HTML）；草稿 approve 带 In-Reply-To 并归档 Sent
- 密钥：本地 `secrets.json`（POSIX chmod 600）；AI key 按档案存放（`ai_profile_key:{id}`）且不回传；服务仅 127.0.0.1

## 分发与打包

| 产物 | 路径 | 说明 |
|------|------|------|
| 源码开发 | `python run.py` | 注入 `backend/` 路径后调 `app.cli:main` |
| PyPI 包 | `pyproject.toml` | 发行名 `nmail-app`（"nmail" 在 PyPI 已被占用），console script `nmail = app.cli:main`；版本需与 `app/config.py` 的 APP_VERSION 同步；前端产物经 `scripts/sync_frontend.sh` 同步进 `backend/app/static` 打入 wheel |
| 三平台单文件 | `nmail.spec` | PyInstaller onefile；hiddenimports 显式声明 uvicorn 延迟导入子模块；前端资源随包 |
| 发布流水线 | `.github/workflows/release.yml` | 打 tag `v*` → wheel 发 PyPI（`uvx --from nmail-app nmail`）+ Windows/macOS/Linux 二进制挂 GitHub Release +（可选 secret `HOMEBREW_TAP_TOKEN`）自动同步 Homebrew tap |
| winget | winget-pkgs PR | `winget install nathanpenny520.Nmail` / `winget upgrade`；portable 型，SHA256 对齐 Release 资产 |
| 发版脚本 | `scripts/release.sh` | 一条命令：同步两处版本号 → 提交打 tag → 盯 CI → 自动提 winget 版本 PR；手册与踩坑见 `docs/RELEASE.md` |

已知分发注意点：Windows SmartScreen 对无签名 exe 会警告（缓解：onedir/误报申诉/买签名证书）；macOS 未公证二进制需右键打开或 `xattr -cr`（公证需 Apple Developer 账号）。
