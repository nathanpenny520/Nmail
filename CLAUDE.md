# CLAUDE.md — Nmail 工作规范

AI 驱动的本地聚合邮箱客户端。Python FastAPI + SQLite(FTS5) 后端 · React+Vite+TS 前端 · 仅绑定 127.0.0.1 · MIT。
产品定位与路线：[docs/PRODUCT_PLAN.md](docs/PRODUCT_PLAN.md)；**v0.4 改版主线（2026-09-12 定稿，落地工作以此为准）**：[docs/REDESIGN_PLAN.md](docs/REDESIGN_PLAN.md)；架构细节：[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)；变更记录：[docs/CHANGELOG.md](docs/CHANGELOG.md)；多会话看板：[docs/SESSIONS.md](docs/SESSIONS.md)。

## 常用命令

```bash
python run.py                                   # 一键启动（127.0.0.1:8720，自动开浏览器）
cd backend && ../.venv/Scripts/python -m uvicorn app.main:app --reload --port 8720   # 后端热重载
cd frontend && npm run dev                      # 前端 dev server（/api 代理到 8720）
cd frontend && npm run build                    # 前端构建（含 tsc 类型检查）——前端改动后必须执行
curl http://127.0.0.1:8720/openapi.json > frontend/openapi.json && cd frontend && npm run gen:api   # 后端 API 改动后：更新接口类型（openapi.json 快照 + schema.d.ts 同提交）
cd backend && ../.venv/Scripts/python -m ruff check app --select F,E9,B,SIM,UP,TID251   # 后端静态检查（含 T4 分层规则：禁 core/scheduler/ai → app.api）
bash scripts/release.sh 0.2.0                   # 一条命令发版（PyPI/Release/Homebrew/winget PR，详见 docs/RELEASE.md）
cd ../nmail-site && npm run build               # 官网仓库（独立 git 仓，Astro；部署见其 README）——发版后补一篇动态即两站同步
```

## 工作流规范（必须遵守）

1. **文档优先**：改代码之前先更新对应文档（本文件 / docs/），写清楚要改什么、影响哪些模块；方案类改动先给方案再动手。
2. **文档同步**：功能变更与文档更新放在**同一个提交**里——`docs/CHANGELOG.md` 必记；涉及架构/接口变化必更 `docs/ARCHITECTURE.md`；阶段推进必更 `docs/PRODUCT_PLAN.md` 状态。
3. **提交信息**：`<阶段/模块>: <一句话>`（例 `P2: AI 层…`、`fix: 发信两处问题…`、`UI v2: …`）。
4. **验证后提交**：前端必须 `npm run build` 通过；后端必须 ruff 通过 + 启动冒烟（`/api/health`）；API 改动用 curl/脚本实测往返。
5. **真实数据验证**：收发/同步/AI 相关功能，必须用用户真实账号数据验证后才能宣称完成。
6. **后端改动必须重启进程**：前端 dist 由后端按请求读盘（强刷即见），但 Python 进程不会热加载——"改了没生效"先查是否重启。
7. **数据库迁移只追加**：在 `backend/app/db/database.py` 的 `MIGRATIONS` 列表末尾追加新版本号 SQL，禁止修改历史迁移。
8. **多会话透明——开工三件事**：多个会话并行共享同一工作树是常态。开工前必做：① 读 `docs/SESSIONS.md`，目标范围与任一「进行中」会话重叠时先协调或换范围；② 在看板登记本会话（ID / 目标 / 预计触碰文件）；③ `git log --oneline -5` 看最新动态。收工时更新看板——完成或中断都要留状态、产出与遗留事项，不留僵尸条目。
9. **即时重读，禁凭记忆覆盖**：共享树里文件随时可能被其他会话修改——编辑前的 Read 必须新鲜；发现文件与预期不符时，以磁盘现状为准，对照 `git log` 弄清发生了什么再调整方案，绝不盲改回去。
10. **提交纪律**：按路径 `git add` 只暂存本会话改动，不带其他会话的 WIP；提交前看 `git log` 确认并行新提交，推送前先 `git pull --rebase`；CHANGELOG 条目先用「待提交」占位、提交后由产生它的会话回填哈希。**谁改动谁提交**：会话完成并验证通过后立即自行 commit（含文档），不得把已完成的改动留在工作树等他人代提交。

## 架构速览（详见 docs/ARCHITECTURE.md）

- `backend/app/`：`main.py` 入口（SPA 托管+SSE）· `api/` 路由 · `core/`（IMAP/SMTP/同步/流水线/HTML消毒）· `ai/`（LLM 任务/提示词/摘要）· `db/`（迁移+KV）· `scheduler.py`（轮询+每日摘要）
- `frontend/src/`：`pages/` 页面 · `components/` 组件 · `api/client.ts` REST + `api/stream.ts` SSE
- 数据与密钥：`%LOCALAPPDATA%/Nmail`（`nmail.db` + `secrets.json`），`NMAIL_DATA_DIR` 可覆盖
- 无 OS 独有 API；服务仅绑定 127.0.0.1；API key 存本机 secrets.json 并明文回显设置界面（默认遮蔽、小眼睛显隐；用户要求所见即所存）

## 关键决策（勿违背）

1. 只做邮件核心：收发读搜分类归档；**不做**日历/CRM/任务/聊天（docs/PRODUCT_PLAN.md §3.6）；轻量通讯录（自动采集+写信补全）属邮件核心，非 CRM（v0.4 修订）
2. 跨端优先：不用 OS keyring/DPAPI/托盘；通知走浏览器 Notification API
3. AI 分类先行，无规则引擎；仅发件人白/黑名单两个零成本集合
4. 人在回路默认：AI 发送默认必须人工审批；自动模式仅「AI 专属邮箱」默认开启，普通账号手动开且需二次确认（v0.4 修订，边界见 REDESIGN_PLAN §6.6）
5. 成本控制：规则/集合先行，AI 批量分类（约 20 封/请求），正文截断，全量 ai_logs
6. 参考项目只借思想：**inbox-zero 是 AGPL，严禁复制代码**；mail-skill 无 LICENSE，不复制代码
7. UI 导航：无应用侧栏，「邮件」为唯一常驻基座，其余页面经标签条右侧小按钮点击开页签（v0.4，REDESIGN_PLAN §3.2）
8. 归档 = 每账号服务器端 `Archived` 文件夹的真实 IMAP 移动（账号列 `archive_folder`）；不再使用本地聚合归档视图（v0.4，REDESIGN_PLAN §4.6）
9. 对外 API 仅由本机进程提供且只绑定 127.0.0.1，不提供监听 0.0.0.0 选项；不提供云端托管服务（v0.4，REDESIGN_PLAN §7）
