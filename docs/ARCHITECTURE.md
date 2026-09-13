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
   ├─ secrets.json  AI key、各账号授权码、OAuth 客户端配置与令牌（AI key 明文回显设置界面供所见即所存；账号授权码不回传）
   ├─ accounts/<id>/attachments/  附件落盘
   └─ drafts/<id>/               写信台草稿附件落盘（发送/删稿即清）
```

## 后端模块（backend/app/）

| 模块 | 职责 | 要点 |
|------|------|------|
| `main.py` | 入口、lifespan（迁移+调度器启停）、SPAStaticFiles 回退、本机来源校验中间件（`/api/ext/*` 豁免改持 API Key + ext 调用日志） | 路由先于静态挂载注册 |
| `api/deps.py` | API 层公共错误翻译 | `mail_error_to_http`（MailError→4xx/502 翻译表）、`ai_config_or_400`（AI 未配置/停用→400）、`ai_result_or_http`（AI 调用统一 400/502）——端点零样板 |
| `api/system.py` | `/api/health`、`/api/update-check`（24h 节流，force 可立即检查）、`/api/system/paths`（数据/安装目录实时解析：`get_data_dir()` 含 NMAIL_DATA_DIR 重定向；安装目录按运行形态——冻结=可执行目录、源码=仓库根（与版本号同一判定）、wheel=`app` 包所在目录） | 只读展示，体现软件本地性，零硬编码 |
| `api/settings.py` | 通用设置 KV 读写 + AI 端点测试（2026-09-13 增：`desktop_notifications_enabled` 桌面通知总开关、`notify_types` 按类型细分（new_mail/ai_draft/digest/account_error，读侧与默认合并缺省视为开）、`auto_insert_signature` 自动签名——前端 NotificationBell 弹系统通知前按两键过滤，ComposeContext 开写信标签时注入签名一次） | 含 `ui_font/body_font` 档位校验；GET 附带只读 `detected_proxy`（系统代理探测）与 `effective_proxy`（实际生效通道，前端 3s 轮询实时展示）；AI 配置已移至 profiles；`/api/ai/test` 字段省略时回退激活档案 |
| `api/accounts.py` | 账号 CRUD/测试/探测/后台同步触发/服务商预设/文风提示词 | 授权码存 `secrets.json`（key=`account_pwd:{id}`）；`POST /accounts/probe` 未收录域名自动探测；代理跟随系统自动生效（`core/netproxy`，无账号级字段无开关）；OAuth 账号拒绝改密（400 指引重新授权）、删除账号时一并清 OAuth 令牌与 folders 缓存 ；列表/详情回传 `password` 明文（授权码所见即所存，同 AI key；仅本机 API——对外 ext 有独立窄 DTO 不含密码） |
| `api/folders.py` | 文件夹：缓存列表/强制刷新/创建/重命名/删除（v0.4 P2，自 accounts.py 迁入并扩展） | 树数据源走 folders 表缓存（空/refresh=1 才连服务器 LIST）；重命名/删除的文件夹名走查询参数（名内含分隔符）；系统文件夹（INBOX+SPECIAL-USE 识别）不可改删（`folder_guard`）；RENAME 本地缓存/邮件/断点跟随（UID 不变），DELETE 清邮件行/断点/附件目录 |
| `api/oauth.py` | Gmail/Outlook OAuth2：`GET /api/oauth/status`（**三态**：configured 自建 / builtin_available / can_authorize + 生效客户端掩码与回调地址）、`PUT /api/oauth/config`（自建 client_id/secret/回调路径登记，configured 语义=自建已配置）、`POST /api/oauth/authorize`（发起授权返 auth_url，内置凭证免预检）、`GET /api/oauth/flow/{state}`（前端轮询结果）、`GET /oauth/callback` + `GET /`（回环回调，直出自关闭 HTML；失败页附高级区自建降级引导） | 回调地址=`http://localhost:{进程端口}{生效客户端登记路径}`（端口随 run.py 动态，端口被占会顺延——桌面型 OAuth 客户端对 localhost 回环不校验端口，**路径不豁免**）；`GET /` 按 state 参数与 SPA 首页分流（授权重定向必带 state；不带则回退前端 index.html），仅在精确 `/` 拦截、其余路径仍归 SPA；回调里完成换令牌→建/转账号→触发首同步（存令牌带签发 client_id）；流程状态进程内 10 分钟 TTL，state 防伪、verifier 用后即弃；回调页不携带任何令牌内容 |
| `api/emails.py` | 列表/搜索/详情/操作/附件下载/归档迁移 | 搜索：≥3 字走 FTS5 trigram，<3 字回退 LIKE；详情返回消毒后 HTML（`?images=1` 放行远程图+内联 cid）。**v0.4 归档语义（§4.6）**：archive=移到账号服务器端归档文件夹（`accounts.archive_folder` 缺省 Archived，惰性创建），unarchive=移回收件箱，批量归档走 imap_batch job；`GET /emails/archived_pending`+`POST archived_migrate/dismiss`=存量本地归档一次性迁移流（迁移前管线清扫挂起，KV `archive_migrate_done`） |
| `api/contacts.py` | 通讯录（2026-09-12 改版，REDESIGN_PLAN §5.3/§5.4）：聚合列表/搜索（source/group_id/ungrouped 过滤 + 四视图计数）、联系组 CRUD 与成员增删、`/{id}` 详情（聚合行+各账号明细）、手动新增、按 email 作用域的改/删、`/suggest` 写信联想 | 同邮箱多账号**聚合为一行**（编辑/删除作用于该邮箱全部行，改邮箱连带更新组成员表）；手动新增=全局作用域 source=manual（不被采集覆盖）；改名即转 manual；组端点移除成员走 POST `/members/remove`（DELETE+body 兼容性） |
| `api/user_drafts.py` | **草稿统一 API**（v0.4 P3）：CRUD + 附件上传/删除 + 定时/取消 + 发送 + AI 待审流转（丢弃/恢复/带指令重写/按邮件拟稿） | status 全集 editing/scheduled/pending_review/sent/discarded，origin 区分 ai/human；列表 LEFT JOIN in_reply_to 原邮件作上下文；发送走 `core/outbox.send_user_draft` 唯一通路（pending_review 同样适用）；`/regenerate-for-email` 供邮件视图一键拟稿；原 api/drafts.py 已退役删除（路由 `/api/drafts` 不复存在） |
| `api/meta.py` | `GET /api/meta`：分类枚举下发（key/label/color/badge_cls） | 真源 `ai/categories.py`；前端 `useMeta` 拉取一次长期缓存，徽章/图表色不再手写 |
| `api/compose_extras.py` | 写信台模板/签名 KV（Markdown 文本整存整取）+ `POST /markdown` Markdown→消毒 HTML 转换 | 存 settings KV（compose_templates/compose_signatures） |
| `api/ai.py` | 单邮件问答、总管家问答（会话持久化）、**Agent 对话**（v0.4 P6）、写作辅助、用量、AI 整理 | 问答/总管家均有 `/stream` SSE 版本，中途错误以 `{"error":...}` 事件下发；**Agent**：`POST /api/ai/agent/stream`（SSE 事件 text/tool_call/tool_result/approval_required/error/done，轨迹落会话）、`/agent/action/{id}/decide`（批准/拒绝，批准时权限复核+参数可改）、`/agent/action/{id}/undo`（撤销）、`/agent/actions`（审计列表）；对话/写作接受 `profile_id` 临时切换档案；AI 整理为异步 job |
| `api/jobs.py` | `GET /api/jobs/active`（观测口）、`GET /api/jobs/{id}`（前端 useJob 轮询） | 任务体注册在业务模块（pipeline/batch_ops），core/jobs 只管调度与登记 |
| `api/notifications.py` | 通知中心 | — |
| `api/sender_lists.py` | 白/黑名单（邮箱或 @域名） | 管线中零成本先过滤 |
| `api/chats.py` | 总管家会话持久化（chat_sessions/messages）：列表/消息/置顶/重命名/删除 | 列表 置顶>updated_at 倒序；删除级联；`append_message` 供 ai.py 落库复用 |
| `api/profiles.py` | AI 配置档案 CRUD/激活/模型列表代理（`POST /api/ai/models`，显式 URL/Key 优先、回退档案已存值）+ AI 总开关（`PUT /api/ai/enabled`） | 密钥语义：响应回显 `api_key` 明文（本地单用户应用，所见即所存，清空保存=清除）；`ai_enabled=false` 即传统邮件模式，档案保留（/models 属配置辅助不受开关限制） |
| `api/digest.py` | 每日摘要查看/手动生成/重要邮件清除（`POST /api/digest/important/{email_id}/dismiss`） | 清除=快照 JSON 落 `dismissed_important` 记录，GET 过滤展示；同日重新生成经 build_digest 沿袭不清单（不复活），跨天随新摘要自然重置 |
| `api/ext.py` | **对外 API**（v0.4 P7，REDESIGN_PLAN §7）：`/api/ext/v1/*`——health（免认证）/accounts/emails（列表/详情/附件）/emails/actions（批量，慢动作返回 job_id 经 /jobs 轮询）/drafts（列表/创建/approve 发送）/folders（+/sync 按需同步）/contacts/digest/agent（chat 非流式+SSE/decide 审批） | `require_key(scope)` 依赖：api_enabled 总开关（403）→ X-Api-Key sha256 查表（401）→ scope 校验（403）→ 60 次/分钟内存滑动窗 + 每 Key 每日上限（429）；端点全部薄壳转调内部实现（emails/user_drafts/folders/contacts/digest/agent 零新邮件操作）；agent 调用 origin=api 全量进 ai_actions；指南见 docs/对外API使用指南.md |
| `api/extkeys.py` | 对外 API 密钥管理（仅内部设置页，走常规来源校验） | 明文存 secrets.json（`ext_api_key:{id}`，所见即所存回显），表内只留 sha256 哈希；生成/改名/scope/每日上限（0=不限）/重置（旧串立即失效）/吊销（行保留供日志对账）；`/enabled` 总开关+日志开关；`/calls` 调用日志（30 天保留） |
| `core/providers.py` | 20 个服务商预设（含中文授权码提示）+ 未收录域名自动探测 | 按域名自动匹配；`probe_server()`：autoconfig 标准接口 → 常见主机名 993/465 并发试连（只收加密端口） |
| `core/imap_client.py` | IMAP/SMTP 封装 | 连接/读写超时 60s；`iter_new_mail` 分块产出新增邮件（SEARCH UID 清单 → 稠密窗口区间 FETCH、稀疏窗口逐 UID 精确拉取——移入型文件夹如「已删除」日期与 UID 不单调，QQ 会把任何多 UID 集合按 min:max 连续展开）；网易系需 IMAP ID 命令；SMTP 端口 465=SSL/587=STARTTLS；`append_sent` 发送后归档；`MailConfig.access_token` 非空时 IMAP 走 `xoauth2`、SMTP 走 `AUTH XOAUTH2`（不广播时回退裸 docmd） |
| `core/oauth.py` | Gmail/Outlook OAuth2 授权与令牌管理（PKCE 授权码流程、XOAUTH2 编码、令牌刷新） | 服务商参数内置（Gmail scope 仅 `https://mail.google.com/`、Outlook 用 outlook.office.com 资源 + offline_access；端口 465=SSL/587=STARTTLS）。**客户端来源（v0.4 P5，D1=A）**：`BUILTIN_CLIENTS` 内置公开桌面客户端凭证开箱即用（redirect_path="/"，来源 Thunderbird 公开源码，免责见模块 docstring）；用户自建（secrets `oauth_client:{provider}`，redirect_path 缺省 `/oauth/callback`）永远优先，`get_client()` 回退链带 source 标记。令牌存 `oauth_token:{account_id}`（expires_at 预扣 120s 余量、微软轮换覆盖、**client_id=签发客户端**）；`client_for_refresh` 按签发者选边刷新（内置/自建混用不互相污染）；`ensure_access_token` 按账号加锁防并发重复刷新；令牌交换跟随全局代理（`netproxy.httpx_proxy_arg`）；教程见 docs/OAuth2 使用指南.md（快速授权）与自建教程（高级） |
| `core/netproxy.py` | 网络代理（被墙服务商场景）：跟随系统、零开关零配置的建连层（语义=浏览器） | 地址解析：自动检测系统代理（urllib.getproxies：macOS 系统代理/Windows 注册表/env，每次连接现读；socks:// 归一 socks5），无手动地址无开关（`network_proxy` 设置已整体移除）；所有账号 IMAP/SMTP/OAuth 统一生效（无账号级字段，`accounts.use_proxy` 已废弃不读）；PySocks 套接字 + 标准库注入（IMAP4_SSL 覆盖 `_create_socket`、smtplib 覆盖 `_get_socket`，httpx 显式传 proxy），不全局替换 socket（保本地回环与并发隔离）；socks5 rdns=True 防污染；坏配置静默直连；本机回环永不代理（Proton Bridge） |
| `core/mailbox.py` | 账号凭据/连接统一入口（全项目唯一 MailConfig 构造点） | `load_account`（账号行+密钥 → AccountHandle，缺一抛 `MailError`；OAuth 账号先 `oauth.ensure_access_token` 刷新令牌再装配）、`has_credentials`、`open_imap`；API 层 `_imap_for` 等拼装点逐步迁移至此（IMPROVEMENT_PLAN §3.1）；添加账号入库前的表单直连预检除外 |
| `core/folders.py` | 服务器文件夹缓存与 CRUD（v0.4 P2，REDESIGN_PLAN §4） | folders 表只做缓存（服务器为真）；SPECIAL-USE 标记优先、名称启发式兜底（sent/drafts/junk/trash/all；不做 archive 启发式防误标）；`folder_guard` 系统文件夹守卫；`ensure_archive_with_mb` 归档文件夹惰性创建；删除/服务器消失的文件夹清理本地邮件行/断点/缓存/附件目录 |
| `core/contacts.py` | 通讯录采集与联想（v0.4 P4，REDESIGN_PLAN §5.3） | `upsert_contact` SELECT-then-UPDATE/INSERT（表达式索引不支持 upsert 冲突目标且作用域含 NULL）；source=manual 只计数不覆盖姓名；`collect_sender`（sync 新邮件）/`collect_addresses`（发送 To/Cc/Bcc，支持「Name <a@x>」）受 `contacts_auto_collect` 开关门控（关=不入册，已有数据保留）；`suggest` 全局去重取最优行、use_count×最近加权；管理侧 `list_contacts_agg`/`list_groups`/`set_members`（成员按 email 记，删除联系人后清孤儿行） |
| `core/sync.py` | UID 增量同步 | 分块断点续拉（每块入库+断点同一事务提交，中断从断点续传）；`start_sync` 后台线程执行（防重入），进度写账号 status=`syncing`+status_detail；网络异常自动重试一次；首同步限 30 天；UIDVALIDITY 变化自愈；登录失败→`auth_error`+一次性通知；增量拉取后 FLAGS 对账（`UID SEARCH UNSEEN/FLAGGED` ↔ 本地 is_read/starred，只翻差异行——外部客户端已读/星标变化的入网点，SEARCH 失败跳过不阻塞同步）；新邮件按服务器 FLAGS 初始化已读/星标；缺凭据的 OAuth 账号置 `auth_error`+一次性通知（不再静默跳过），授权恢复后自动回 `ok`；同步完成后触发 AI 流水线 |
| `core/outbox.py` | 草稿发送唯一实现（API 与调度器共用）+ 旧数据迁移 | `send_user_draft`：状态校验（editing/scheduled/**pending_review**）→地址解析→消毒+纯文本派生→`mailbox.send_message`→标记 sent/清附件/回复原邮件补标已读；失败抛 `MailError`；`draft_dir` 为附件目录唯一出处。`migrate_legacy_ai_drafts`：v0.4 P3 启动期一次性把旧 drafts 表（AI 待审）并入 user_drafts（Markdown→HTML 与原 approve 同源、Re: 主题、收件人=原发件人、状态映射 pending→pending_review；KV `legacy_drafts_migrated` 门控，门控与数据同一事务原子提交）；旧 drafts 表保留只读 |
| `core/jobs.py` | 轻量任务执行器（ThreadPool 2 线程） | `@runner(kind)` 注册表 + `submit`（dedupe 防双击）+ `report`（进度/阶段入 jobs 表）+ 失败进表；`GET /api/jobs/*` 供前端 useJob 1s 轮询 |
| `core/batch_ops.py` | 批量 IMAP 动作任务体（trash/move/archive/unarchive 异步化） | 按账号分组共用连接、进度按账号上报；R2 语义（拿不到新 UID 删行交增量重建）与「服务器成功才动本地」保持；archive 逐账号惰性建归档夹再移动；打标类在端点同步执行 |
| `core/pipeline.py` | 白/黑名单 → AI 批量分类 → 营销自动归档 → 生成草稿 → 通知 | AI 未配置诚实降级；批量 20 封/请求。**v0.4**：营销/黑名单归档经 `_sweep_server_archive` 落服务器归档文件夹——archived_local 只是移动前暂存标记（失败保留、下次管线自动重试）；存量迁移决策未做（KV=0）时清扫挂起；AI 拟稿直接写 user_drafts(pending_review, origin=ai)（P3 起与手写同表同通路） |
| `core/mail_html.py` | nh3 白名单消毒 + 远程图片拦截 + `<style>` 放行 + cid 内联 + Markdown→HTML | 三层防护：nh3 消毒在前；图片控制在后（放行时追踪像素=声明尺寸≤2px 置 display:none、缺 alt 的远程图补空 alt 防裂图）；`<style>` 标签 nh3 默认连内容剥离且不可放行（tag 与 clean_content_tags 同现 panic），先摘出 CSS 按图片口径清洗再注回，拦截口径同步剥 style 属性远程 url() 与 @import（data: 保留）；另供发件方向 `sanitize_outgoing_html`（放行 data: 内嵌图）与 `html_to_plain_text`/`wrap_email_body_html` |
| `core/update_check.py` | 应用内更新检查：GitHub Releases 对比 + 通知中心提醒 | 仅匿名 GET api.github.com（UA=Nmail/版本），24h 缓存；开关 `update_check_enabled`；按 ref_id=版本去重，升级后自动清理旧提醒 |
| `ai/llm.py` | OpenAI 兼容客户端（流式 `iter_deltas` / 非流式） | connect 5s / 读写 15s 快速失败 |
| `ai/profiles.py` | AI 配置档案存储/解析（settings JSON + secrets 分离）+ 总开关 | 解析顺序：显式 profile_id > 激活档案 > 第一个；`resolve_config()` 在总开关停用时直接抛 `ProfileNotConfigured`（全任务统一拒绝）；不预建档案（全新安装为空列表）；旧单配置首读迁移为以模型名命名的档案，历史自动生成的「默认」档案一次性按模型名重命名；列表双写备份（`ai_profiles_backup`）——主值缺失/损坏时自愈恢复，绝不静默走旧配置重建；孤儿密钥对账：不被档案引用的 `ai_profile_key:*` 即读即清 |
| `ai/tasks.py` | 分类/草稿/问答/写作/摘要综述 + 用量日志 | 所有任务接受 `profile_id` 并经 `_ai_config()` 按档案解析；所有调用写 `ai_logs` |
| `ai/digest.py` | 每日摘要：统计（零成本 SQL）+ AI 综述（一次调用） | 当天已生成则复用 |
| `ai/prompts.py` | 全部提示词模板 | 结构化输出要求纯 JSON，`_extract_json` 容错解析；分类枚举段由 `ai/categories.py` 生成 |
| `ai/categories.py` | 分类枚举单一来源（key/label/color/badge_cls/判定说明） | prompts 分类段、tasks 校验、pipeline 自动归档、digest 分桶、`/api/meta` 下发全部消费此处——**加分类只改本文件** |
| `ai/tools.py` | 总管家工具集（v0.4 P6，REDESIGN_PLAN §6.3） | 15 个工具（6 读 + 9 写），薄壳转调既有能力（emails 查询/folders/outbox/jobs/contacts）；ToolSpec 带 kind（read/write）与 grant（read/draft/organize/send/delete）；`resolve_grants` 多账号取交集（缺失按旧 ai_permission 映射）；`recipient_allowed` 自动发送收件人白名单（通讯录∪历史往来）；**无任意 HTTP/文件系统/命令类工具**（白名单即安全边界） |
| `ai/agent.py` | 总管家 Agent 循环（v0.4 P6，REDESIGN_PLAN §6.2/§6.5/§6.6） | JSON 工具协议（`{"tool","args"}` 经 `_extract_json` 容错，本地模型通吃）；MAX_STEPS=8 防失控；写类审批模式出卡（ai_actions pending）并以 approval_required 结束本轮、批准由 decide 端点执行（权限复核）；自动模式约束：发送收件人白名单、无附件草稿、每日 ≤20 封发送 / ≤200 动作；写动作全量落 ai_actions（含 undo_json）；系统提示词注入防护（正文指令≠用户指令） |
| `db/database.py` | 连接（WAL）+ `MIGRATIONS` 版本化迁移 + KV 设置 | 迁移只追加不改历史 |
| `scheduler.py` | 每 60s tick：到期账号增量同步 + 摘要到点生成 + 定时草稿派发 | 「检查到期」而非每账号注册任务，改设置无需重建调度；定时草稿到期调 `core.outbox.send_user_draft`（不依赖 API 层），成功/失败写通知中心，失败退回 editing；轮询只拉 INBOX，其他文件夹按需同步（树选中触发）且不进 AI 管线（`sync.py` 仅 INBOX 新邮件进管线） |

## 前端（frontend/src/）

| 部分 | 内容 |
|------|------|
| `pages/` | MailPage（**邮件基座**：FolderTree + 视图组合——聚合收件箱/账号收件箱/服务器文件夹走 MailBrowser、**草稿=DraftsHubPage**（v0.4 P3：AI 待审+手写合并，分段筛选 待审/编辑中/定时中/已发送/已丢弃，origin 徽章，批准发送/编辑后发送/重写/丢弃/恢复/取消定时）；选中非 INBOX 文件夹触发按需同步；拖拽移动走 batchAction job；内置存量本地归档一次性迁移弹窗；视图初值取 URL，旧路由 /drafts /mydrafts → /?view=drafts、/archived → /）、DigestPage（ECharts 摘要）、ManagerPage（**AI 总管家 2.0**：对话 Agent——审批/自动模式开关（localStorage 记忆，切自动二次确认）、账号范围/档案选择、工具调用卡/结果卡/审批动作卡（批准/拒绝/撤销），SSE 事件流 streamAgentEvents）、SettingsPage（侧边栏分类：通用/邮箱账号（含 AI 权限面板=5 授权位+AI 专属邮箱）/通讯录（2026-09-12 改版：左树=智能视图+联系组右键管理、自动采集开关，右列表/详情双态，详情可写信（openNew 带初始收件人）/编辑/加入移出组）/AI 配置/AI 用量（含 AI 操作记录查看器）/API（v0.4 P7 对外 API：总开关+日志开关+密钥生成/重置/吊销+明文遮蔽回显/调用日志，ExtApiSection 组件）/关于） |
| `components/` | Layout（**v0.4 无侧栏**：顶部标签条=邮件基座页签（唯一常驻）+ 可开启页面页签（AI/摘要/设置，经右侧图标按钮点击产生，记忆 localStorage）+ 写信页签覆盖层（写信激活时底层 display:none keep-alive）+ 右侧图标按钮区 通知/AI 总管家/每日摘要/设置/新邮件）、FolderTree（**v0.4 P2 完整版**：智能视图 + 账号折叠组（状态点/展开记忆/懒加载 folders 缓存）；服务器文件夹层级树（INBOX→Archived→系统→自定义，分隔符组树）；右键菜单=新建（子）文件夹/重命名/删除/刷新（系统文件夹守卫）；拖拽落点（同账号邮件移入，跨账号忽略）；All Mail 守卫置灰不可点）、ContextMenu（通用右键菜单：定位夹紧/Esc 关闭）、MailBrowser（三态：列表/分屏/全屏；账号/文件夹由树经 `initialAccountId`/`initialFolder` 下发换 key 重挂；行可拖拽（多选集合一起拖，`application/x-nmail-ids`）；键盘 j/k/x/o/e/#/c///；筛选栏留星标+分类+面包屑）、EmailReader（消毒 iframe+操作栏+AI 面板）、HtmlMail（sandbox=allow-same-origin+allow-popups，外链新标签打开，ResizeObserver 高度自适应+zoom 注入+正文基础样式兜底）、compose/（写信工作台：ComposeContext 多标签状态中枢挂 App 级 + 草稿缓存恢复、ComposeWorkbench 当前标签表单、ComposeForm 字段+附件上传落盘+定时+自动保存、RichEditor=TipTap v3 富文本、AiWriteDialog 指令生成/快捷改写→预览→替换或插入、InsertDialogs 模板/签名菜单与管理弹窗、quote.ts 回复/转发引用、ui.tsx Dropdown/Modal）、AddAccountModal、AiPanel、NotificationBell（浏览器通知）、Markdown（react-markdown+gfm） |
| `api/` | `client.ts`（REST 封装，FormData 不设 JSON 头）、`stream.ts`（SSE 解析，错误可见）、`useAI.ts`（AI 总开关 hook，与设置页共享 ['ai-profiles'] 缓存；停用时全应用隐藏 AI 入口——含树「待审草稿」节点与 AI/摘要图标） |
| 字号系统 | `index.css` 三档 CSS 变量（`--fs-xs/sm/md/lg`+行高），`<html data-font>` 切换（FontApplier 读设置应用）；**t-\* 是唯一字号入口**——`scripts/lint-font.mjs` 门禁（`npm run build` 前置）禁止 Tailwind 裸字号类与 `text-[Npx]`（白名单：Markdown/HtmlMail 富文本渲染），裸类不随档位缩放是历史「字号不一」根因；正文字号独立经 iframe zoom 注入 |

## 数据表（nmail.db）

`settings`(KV) · `notifications`(保留 500 条) · `accounts`(含 ai_permission/ai_grants v17 五授权位 JSON/is_ai_mailbox AI 专属邮箱/style_prompt/archive_folder) · `emails`(含分类/needs_reply/archived_local——**v0.4 起为「待服务器归档」暂存标记**) · `attachments` · `folders`(v15 文件夹缓存) · `contacts`(v16 通讯录，v21 加 phone) · `contact_groups`/`contact_group_members`(v21 自定义联系组，成员按 email 记) · `ai_actions`(v17 Agent 动作审计：tool/params/mode/origin/status/undo_json，pending 24h 过期语义) · `api_keys`(v20 对外 API 密钥：sha256 哈希/scopes JSON/daily_limit/revoked，明文在 secrets.json) · `api_calls`(v20 调用日志，保留 30 天) · `sync_state`(uid/uidvalidity) · `emails_fts`(trigram) · `drafts`(**v19 起退役**，只读保留) · `user_drafts`(**唯一草稿存储**：editing/scheduled/pending_review/sent/discarded + origin + instruction + send_at) · `user_draft_attachments` · `ai_logs`(全量 AI 用量，保留 90 天) · `sender_lists` · `digest_history` · `chat_sessions`/`chat_messages` · `jobs`(后台任务进度/结果)

迁移版本：v1 基础表 → v2 邮件核心+FTS → v3 AI 层 → v4 摘要+ToneDNA → v5 会话持久化 → v7 date_sort 排序修复 → v8 user_drafts → v9 草稿附件+send_at → v10 语气学习退役→文风提示词（tone_dna 数据转存 style_prompt 后删列）+ AI 总开关（settings KV `ai_enabled`） → v11 清语气学习残留用量日志（ai_logs task_type='tone_dna'） → v12 jobs 后台任务表 → v15 folders 缓存表 + accounts.archive_folder + 存量归档迁移标记（KV `archive_migrate_done`，有 archived_local 存量才落 0） → v16 contacts 通讯录表 → v17 AI 2.0：accounts.ai_grants 五授权位 JSON（按 ai_permission 映射回填）+ is_ai_mailbox + ai_actions 审计表 → v19 草稿体系合并：user_drafts 加 origin/instruction（数据并入走启动期 `outbox.migrate_legacy_ai_drafts`，KV `legacy_drafts_migrated` 门控） → v20 对外 API：api_keys（sha256 哈希/scopes/daily_limit/revoked）+ api_calls 调用日志（18 跳号——原预留 API key 改走 v20） → v21 通讯录改版：contacts 加 phone + contact_groups/contact_group_members（成员按 email 记，匹配「同邮箱聚合一行」口径）

## 关键流程

### 同步管线（每次轮询/手动收信）
```
UID 增量拉取 → 落库+附件落盘 → FLAGS 对账(UID SEARCH UNSEEN/FLAGGED ↔ 本地 is_read/starred)
→ 白名单(留收件箱)/黑名单(直接归档)
→ AI 批量分类(category/importance/needs_reply/reason)
→ 营销(promo)自动本地归档 → 需回复且账号权限≥draft_review → 生成草稿+通知
```

### 安全模型
- HTML 邮件：nh3 白名单（http(s) 链接强制 target=_blank + rel=noopener）→ 远程图默认拦截（计数）→ 前端 sandbox iframe（allow-same-origin+allow-popups-to-escape-sandbox，无脚本；外链点击在新标签由浏览器正常打开，不在 iframe 内导航）；srcdoc 注入 body 基础样式（sans 字体栈+行高，仅兜底继承），邮件自带 `<style>` 随消毒放行（拦截口径下其 CSS 远程资源已剥）
- 发信：multipart/alternative（写信工作台：TipTap HTML 经 `sanitize_outgoing_html` 白名单消毒 → `decorate_outgoing_html` 收件端兜底内联化（编辑器排版来自本地 CSS，收件人客户端没有——发送前把同参数样式写进内联 style：段距/标题/引用/代码块/表格边框等，用户已有内联样式不覆盖；与 index.css 编辑器样式保持同参）→ `wrap_email_body_html` 基础样式外层 + 派生纯文本；AI 草稿 approve 同走 `imap_client` 发送）；草稿 approve 带 In-Reply-To 并归档 Sent
- 密钥：本地 `secrets.json`（POSIX chmod 600，原子写：临时文件+`os.replace`；进程内 `threading.Lock` 串行化读改写——整文件覆盖模型下无锁并发会丢键，曾致 OAuth 令牌全失）；AI key 按档案存放（`ai_profile_key:{id}`）明文回显（所见即所存）；OAuth 令牌按账号存放（`oauth_token:{id}`，含 refresh_token）与客户端配置（`oauth_client:{provider}`）不回传前端；服务仅 127.0.0.1
- 来源校验（main.py 中间件）：Host 必须为本机主机名（端口与实际监听一致才严格比对）；浏览器附带 Origin 时必须为本机源——挡恶意网页对 127.0.0.1 的 drive-by POST 与 DNS rebinding。**例外**：`/api/ext/*`（对外 API，v0.4 P7）豁免两道来源校验、改持 X-Api-Key 认证（外部脚本经自建隧道到达时 Host/Origin 本非本机；浏览器跨站带不上自定义头——预检不通，drive-by 由密钥兜住）；全部 ext 调用（含被拒的）落 api_calls（/health 除外）
- 对外 API 密钥：api_keys 表存 sha256 哈希（唯一索引）+ scopes JSON + 每日上限；明文存 secrets.json（`ext_api_key:{id}`）所见即所存；限流 60 次/分钟/密钥（内存滑动窗）；api_enabled 总开关默认关

## 分发与打包

| 产物 | 路径 | 说明 |
|------|------|------|
| 源码开发 | `python run.py` | 注入 `backend/` 路径后调 `app.cli:main` |
| PyPI 包 | `pyproject.toml` | 发行名 `nmail-app`（"nmail" 在 PyPI 已被占用），console script `nmail = app.cli:main`；版本单一来源（T5）：`app/config.py` 运行时解析链——源码直跑读仓库根 `pyproject.toml`（tomllib）、冻结包读 `nmail.spec` 打入的随包副本、wheel/uvx 读包元数据，兜底 `"0.0.0"`；前端产物经 `scripts/sync_frontend.sh` 同步进 `backend/app/static` 打入 wheel |
| 三平台单文件 | `nmail.spec` | PyInstaller onefile；hiddenimports 显式声明 uvicorn 延迟导入子模块；前端资源随包 |
| 发布流水线 | `.github/workflows/release.yml` | 打 tag `v*` → wheel 发 PyPI（`uvx --from nmail-app nmail`）+ Windows/macOS/Linux 二进制挂 GitHub Release +（可选 secret `HOMEBREW_TAP_TOKEN`）自动同步 Homebrew tap |
| winget | winget-pkgs PR | `winget install nathanpenny520.Nmail` / `winget upgrade`；portable 型，SHA256 对齐 Release 资产 |
| 发版脚本 | `scripts/release.sh` | 一条命令：改 pyproject.toml 版本号 → 提交打 tag → 盯 CI → 自动提 winget 版本 PR；手册与踩坑见 `docs/RELEASE.md` |

已知分发注意点：Windows SmartScreen 对无签名 exe 会警告（缓解：onedir/误报申诉/买签名证书）；macOS 未公证二进制需右键打开或 `xattr -cr`（公证需 Apple Developer 账号）。
