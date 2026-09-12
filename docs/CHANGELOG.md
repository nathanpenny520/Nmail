# Nmail 变更记录（docs/CHANGELOG.md）

> 规范：每次功能变更在同一提交内在此追加一条。格式：`## 提交短hash — 标题` + 要点。
> 与 git 提交一一对应；本文件是"发生了什么"，ARCHITECTURE 是"现在是什么样"。

## 待提交 — 设置页加宽减少左右留白
- 用户反馈设置页左右留白过多：主容器与粘性保存栏 `max-w-4xl`(896px) → `max-w-6xl`(1152px)，宽屏下内容区多出约 256px 可用宽度；两侧页边距与内边距（p-8/gap-8）保持不变

## 2466fd0 — 授权码明文回显（所见即所存）
- 用户反馈「授权码看不见会以为丢失」：`GET /api/accounts` 回传 `password` 明文（secrets.json 本就明文存储，与 AI API key 同一口径；对外 API ext 的 accounts DTO 为独立窄字段，不受影响）——配置编辑器授权码框预填当前值 + 小眼睛显隐，改新码直接覆盖保存；保存按钮要求非空（清空不再静默视为不修改）
- 验证：pytest 141 全绿（+授权码回显往返/OAuth 空串用例）；ruff + npm build 通过；openapi 快照再生

## 490ed13 — fix: 服务器配置编辑器布局塌陷
- 用户真机走查发现（1a1d0e4 引入）：账号「配置」面板里服务器输入框塌回默认宽度、端口框被推出卡片右缘——外层 `<label>` 只挂了 `flex-[2]` 参与行布局但自身不是 flex 容器，内部 input 的 `flex-1` 不生效。三个 label 补 `flex flex-col` 修复；全页扫描确认其余表单均用 `w-full` 的 inputClass 无同类问题

## 5ff1fbe — 通讯录改版：Thunderbird 式双栏管理 / 联系组 / 手机号 / 自动采集开关
- 用户 2026-09-12 反馈指定形态（对照 Thunderbird 截图）：通讯录仍留设置页（D7 不变），分区重写为**双栏管理**——左树=四个智能视图（所有联系人/自动采集/手动添加/未分组，带计数）+ 自定义联系组（右键重命名/删除，底部新建）；右侧列表⇄详情双态：列表列＝复选框/姓名（首字母头像）/邮件地址/手机/来源/往来次数/最近联系，支持搜索、新增（含手机）、批量删除；点击行进**详情视图**（首字母大头像、元信息、各账号归属明细、组徽章）——写信（openNew 加可选初始收件人参数，带姓名地址直达写信台）/编辑（姓名/邮箱/手机/备注）/更多菜单（加入组二级菜单/移出组/复制地址/删除）
- 三项拍板：①同邮箱多账号**聚合为一行**（与写信联想同口径）——编辑/删除按 email 作用于该联系人全部行，改邮箱连带更新组成员表，详情页展示各账号归属；②支持**自定义联系组**——迁移 v21 加 `contact_groups`+`contact_group_members`（成员按 email 记），组全局不挂账号；③加**手机号**字段（contacts.phone）
- **自动采集开关**：设置 KV `contacts_auto_collect`（默认开），关=收信发件人/发信收件人两侧均不再自动入册（已入册保留，手动增改与联想不受影响）；开关放左树顶部（注：采集是规则行为非 AI 调用，故命名「自动采集」）
- 验证：pytest 140 全绿（净增 3：采集开关/聚合列表+email 作用域改删+组连带/组 CRUD+成员）；ruff 门禁通过；npm run build 通过；openapi 快照+schema.d.ts 再生；隔离实例 curl 冒烟（建组加成员/改邮箱连带/开关持久化/删除清孤儿）通过；待用户重启 python run.py 后真机走查

## 1a1d0e4 — UX 体验修：通讯录直改 / 时间显示统一 / 账号服务器配置可编辑
- 用户反馈三组问题，核实与修复：
- **通讯录「无法直改」与「搜索后列更多」**：核实两者皆非缺陷——当前构建搜索前后渲染同一张 6 列表格；用户截图的 2 列版是浏览器残留的旧构建页面（后端按请求读盘 dist，已打开的页面不刷新不换 JS），刷新即一致。真正的可用性问题在编辑入口：仅姓名可点改且无视觉提示 → ①邮箱也支持点击直改（PATCH 新增 email 字段：规范化+同账号作用域查重；改后 auto 行不被覆盖逻辑不受影响）；②副标题与悬浮提示明确「点击姓名或邮箱可修改」
- **时间显示统一审计**：存储约定不变（邮件原时区+date_sort UTC、其余 datetime('now') UTC naive、send_at 特意的本地 naive），修三处前端把 UTC naive/UTC 串当本地显示的漏网——通讯录「最近联系」原 slice(0,10) 显示 UTC 日期（UTC+8 晚间往来会显示成前一天）→ 归一解析转本地；草稿箱列表 updated_at（UTC naive）按本地解析差 8 小时 → 与 send_at（本地 naive）分开解析；更新检查「上次检查」slice UTC 串 → 本地日期；relativeTime 超 7 天回退同样改本地日期
- **账号服务器配置可编辑**：SMTP/IMAP（授权码）账号此前服务器填错只能删号重加（丢本地邮件与账号设置）——PATCH /accounts/{id} 新增 imap_server/imap_port/smtp_server/smtp_port（OAuth2 账号拒绝，服务器随服务商预设）；保存前用存量授权码试连新服务器，失败即 400 不落库；服务器变更自动清空该账号本地邮件与同步断点并后台重同步（防新服务器 UID 撞旧断点漏信）。设置页账号卡片新增「配置」按钮（授权码账号专属）：改服务器四项+可选更新授权码；授权失效红条文案同步改指「配置」按钮（原文案让用户「更新授权码」但界面根本没有入口）
- 验证：pytest 全绿（新增 contacts 邮箱直改/查重、账号服务器变更重同步用例）；ruff 门禁通过；npm run build 通过；openapi 快照+schema.d.ts 再生；待用户重启 python run.py 后真机走查

## cd8b7ad — 发版脚本联动官网自动部署
- 背景：官网（nmail.whizzzest.com）内容全部构建期拉取（GitHub Releases + 主仓 docs），此前发版/改文档后站点不会自动跟上，需手动重建部署
- `release.sh` 新增第 5 步「官网联动」：`gh workflow run deploy.yml -R nathanpenny520/nmail-site`（用本机 gh 登录态，零新增凭据），发版流程末尾自动触发官网重建，1–2 分钟内同步新版；触发失败仅提示、不阻塞发版
- 配套在 nmail-site 仓库（提交 d8aafe7 + 12b2f93，已推送）：deploy.yml 加每日定时构建（兜底 docs/Releases 变更）与 workflow_dispatch；wrangler 入 devDependencies（修 CI 无 TTY 取消）；GITHUB_TOKEN 认证修构建期 GitHub API 限流；仓库 .npmrc 统一官方源——npmmirror 对平台可选包元数据缺失、持续产出无 version 的损坏 lock 条目，是 CI `npm ci` 全环境秒败真因（此前误判为 Secrets 未配）
- RELEASE.md 自动步骤清单补第 6 步
- 验证：`bash -n` 通过；nmail-site CI 实测 npm ci + build + wrangler 调用全部通过，仅剩 `CLOUDFLARE_API_TOKEN`/`CLOUDFLARE_ACCOUNT_ID` 两个 Secrets 待配置后即全自动

## 107947d — 审查修复 P2 体验打磨：拖拽反馈 / 审批过期 / 未读徽章 / 已读节流等
- 接上条（P0+P1，756fe37），落审查地图 P2 项：
- **U1 拖拽移动反馈**（原 `.catch(() => undefined)` 吞错，最伤感知）：`MailPage.onDropEmails` 重写——乐观更新（被拖邮件先从本地列表摘除）+ 后台 job 进度浮条（复用 useJob 1s 轮询）+ 成功/失败提示；失败回滚快照并提示「列表已还原」；REDESIGN_PLAN §4.3 承诺按原设计落地
- **U2 审批动作 24h 过期**：`expired` 原先只有 schema 注释、pending 永久挂起——scheduler.tick 新增 `expire_stale_actions`（pending 且 created_at 超 24h → expired + 原因落 error）
- **U3 右键「移动到…」二级菜单**：ContextMenu 支持子菜单（悬停右侧展开、限高内滚），条目按被右键邮件**所属账号**的文件夹清单生成（聚合视图下与当前筛选账号区分），排除邮件当前所在夹；单封/多选分别走单封/批量动作
- **U3 未读徽章**：`folders.cached_list` 每夹附 `unread`（一条 GROUP BY 本地 SQL，零外呼）→ 树节点右侧计数徽章（99+ 截断）；MailBrowser 的 invalidateMail 顺带失效 `folder-cache`（打标/移动/同步完成徽章即刷新）；草稿入口加 AI 待审数徽章（复用 `['user-drafts','pending_review']` 查询缓存，60s 兜底轮询）
- **U4 已读合并写**：点击邮件先本地乐观置已读，800ms 内连续点击合并为一次批量 IMAP SEEN（原先逐封直发、快速浏览连打服务器）；卸载前把未落地队列 fire-and-forget 发出；失败提示由 20s 列表轮询校正
- **C2 归档夹显示名**：树节点硬编码 `'Archived'` 改为显示服务器实名（账号可自定义 archive_folder 名，如「已归档」；图标仍标识归档属性）
- 小项：**F6** IMAP ID 版本号从包元数据取（`config.APP_VERSION`，单一来源 pyproject，原硬编码 0.1.0）；**F7** 摘要「重要邮件」排序改 critical 优先、组内最新在前（原升序最新一封沉底）；**C4** `refresh_cache` 空 LIST 防御（网络抖动返回空时保留本地缓存并告警，不再误 purge 全部文件夹）
- 核实后不修（记录口径）：**S3** 读类工具计入 200 次/日限额是 REDESIGN_PLAN §6.6 规范本身（全部动作≤200/天）；实际仅会话内内存计数含读、持久化审计只记写类，跨会话读不占额度，维持现状；**C3** 「已拦截 N 张图片」横幅用详情现算的消毒结果，口径天然一致，核实无不符路径
- 验证：pytest 135 全绿；ruff（app 门禁）通过；npm run build（tsc + 字号门禁）通过；隔离实例 `/api/health` 冒烟 ok
- 遗留：拖拽进度/徽章/二级菜单为 UI 行为，待用户重启后真机走查；`FolderCacheItem` 增 `unread` 字段（后端响应为无 schema dict，openapi 快照无变化，types.ts 手动同步）

## 756fe37 — 审查修复 P0+P1：摘要判定 / AI 工具越权 / 时区 / 本地推理兼容等七项
- 依据 v0.4 审查问题地图（2026-09-12，22 项逐条核实：15 项属实、3 项部分属实、C3 拦截计数核实为不成立），先修两个 P0 与五个 P1：
- **P0-1 每日摘要「需要回复」失效**（F1）：`ai/digest.py` 仍查已退役的旧 `drafts` 表（sent_ids/_has_draft），用户已回复的邮件在摘要里恒显示需回复、「已有草稿」标记恒 False——改查 `user_drafts`（`status='sent' AND in_reply_to`；待审 pending_review 计入已有草稿标记且保持需回复）；新增 `test_digest.py` 两例回归
- **P0-2 AI 工具会话范围越权**（F2）：`ai/tools.py` 的 search/list_recent/list_folders/create_folder/start_organize 接受模型传任意 `account_id` 不校验、digest_stats 无账号过滤（汇总全部账号）——`execute()` 统一收口：args.account_id 必须 ∈ 会话范围（缺省回落主账号）；`run` 签名加 scope 参数，`_scope_guard` 改按会话范围集合（顺带修复多账号会话读副账号邮件被误拒的问题）；digest_stats 四条 SQL 加范围过滤；agent 循环与审批端点传入范围；新增 3 例越权回归
- **P1 时区**（F3/F5）：`api/ai.py` `_manager_context` 用 naive 本地时间与 UTC 的 date_sort 直接比较（UTC+8 下「最近 N 天」少 8 小时）→ 边界改 aware datetime 转 UTC 生成；`ai/digest.py` `_to_local_dt` 把 naive 按 UTC 解释，与 `sync._norm_date` 的按本地解释相反 → 统一为按本地（`astimezone()`）
- **P1 本地推理兼容**（F4）：`llm.py` `iter_deltas` 无条件传 `stream_options={"include_usage": True}`，旧版 Ollama/LM Studio 等兼容端点直接报错、与「100% 本地推理」冲突 → 失败去参重试一次（退化为无用量回填的普通流）
- **P1 自动模式收件人解析**（S2）：`recipient_allowed` 只按逗号切分，「姓名 <邮箱>」整串比对通讯录必不命中 → 带显示名的草稿恒降级审批；`contacts.py` 新增 `extract_addresses`（与 collect_addresses 同口径解析出纯 email）复用
- **P1 审批参数校验**（S1）：`execute_action` 的 args_override 原样落库执行（如 `read:"false"` 被 bool() 当真、必填缺失）→ `tools.normalize_args` 按工具参数表做类型矫正+必填校验：execute 内联生效（agent 直执行路径同享）+ 审批路径前置校验，失败置 failed 不执行
- **P1 回复后服务器已读回写**（C1）：发送回复仅本地 `is_read=1`，服务器 SEEN 不同步（网页端仍显示未读、重同步后本地漂回）→ `outbox._mark_original_seen` 尽力 IMAP STORE `\Seen`（失败仅告警，不影响发送结果）
- 测试修整：`test_api_emails` 搜索断言收进账号范围（原全局 LIKE 断言 `q="邮"==4` 被任何新夹具邮件污染，本次新增用例即触发；意图不变：账号内跨文件夹 LIKE 搜索）
- 验证：pytest 135 例全绿（净增 8：digest 2 + 越权 3 + 参数/收件人 3）；ruff（app 门禁）通过；隔离实例 `/api/health` 冒烟 ok
- 遗留：C1 与 F4 的真实账号行为待用户重启 `python run.py` 后验证

## 816c90f — 文档补齐 + 文档上站（nmail-site /docs）
- **主仓新增三篇用户文档**（官网与仓库共用）：
  - `docs/使用指南.md`——完整操作手册：界面导览（基座+页签+三栏）、收信与文件夹管理（拖拽/右键/快捷键表/真实归档）、AI 总管家（双模式/权限矩阵/自动边界/审计撤销/防注入）、写信草稿通讯录（富文本/自动保存/chips 联想/定时/AI 写作/统一草稿）、每日摘要、通知、设置速览、网络代理
  - `docs/FAQ.md`——按主题分类的高频问题（安装启动/Gmail 被墙代理/授权码/AI 401 与本地推理/同步与归档/数据迁移/API 限流），沉淀自真实踩坑（SmartScreen、Gatekeeper、org_internal 403、POP/IMAP 未开、uvx 单横线笔误等）
  - `docs/隐私与安全.md`——数据位置表、仅有的两类外呼（AI 端点+匿名更新检查）、127.0.0.1 网络边界、内容安全（消毒/沙箱/防注入）、密钥管理约定
- **官网文档中心（nmail-site，提交 aecf3f0 已部署）**：`/docs/` + `/docs/<slug>` 9 篇——`scripts/sync-docs.mjs` 构建期（prebuild）把主仓 docs/**白名单**文档同步渲染；来源优先级 环境变量 NMAIL_DOCS_DIR → 本地同级仓库 → GitHub raw main（CI 兜底）；自动改写相对 md 链接为站内路由（白名单外指 GitHub）+ 剥 H1 路径注记；**安全约束：主仓 docs/ 有含凭据被 gitignore 的内部文档，同步绝不整目录拷贝（白名单显式列举）**；Docs 布局（分组侧栏 导航元数据 src/config/docs.ts）+ 文档首页；顶导航加「文档」；生成文件不入库（单一来源=主仓）
- 决策变更：REDESIGN_PLAN §10.1「文档链接 GitHub 不双维护」→ 用户 2026-09-12 拍板改为构建期同步上站（仓库仍是唯一维护处）
- 验证：sync 9/9 篇（链接改写与 H1 清理抽查）；astro build 17 页通过；线上 https://nmail.whizzzest.com/docs/ 与 guide/faq/api 全部 200
- 备注：官网同期由 Pages 迁 Workers 静态资产（nmail.whizzzest.com 自定义域名入 wrangler.toml 自动建，见 nmail-site 仓库提交）

## 0ede5e2 — v0.4 P7: 对外 API（/api/ext/v1 · API Key 认证 · scope 分级）
- 依据 docs/REDESIGN_PLAN.md §7/§13 P7（D3=A：仅 127.0.0.1，外部设备走用户自建隧道）
- **`/api/ext/v1/*`**（`api/ext.py` 新增）：health（免认证）·accounts·emails（列表/搜索/详情/附件）·emails/actions（批量动作，移动类异步返回 job_id 经 /jobs/{id} 轮询）·drafts（列表/创建/approve 发送，统一草稿体系）·folders（+/sync 按需同步，名走查询参数）·contacts·digest·jobs/{id}·agent（chat 非流式+chat/stream SSE+actions/{id}/decide 审批）——端点全部薄壳转调既有实现（emails/user_drafts/folders/contacts/digest/agent），零新邮件操作
- **认证与限流**：`X-Api-Key` 请求头 → sha256 查 api_keys 表（明文存 secrets.json `ext_api_key:{id}`，所见即所存与 AI key 同惯例，表内只留哈希）；scope 四级 read/write/send/agent；校验链=api_enabled 总开关（默认关，403）→密钥（401）→scope（403）→60 次/分钟内存滑动窗+每 Key 每日上限（429）；last_used_at 节流回写（≥60s 一次）
- **来源校验豁免（main.py）**：`/api/ext/*` 跳过 Host/Origin 两道本机校验改持 API Key——隧道可用性前提；浏览器跨站带不上自定义请求头（预检不通），drive-by 由密钥兜住；`/health` 不记日志，其余 ext 调用（含被拒的，key_id=0）经中间件线程池落 api_calls（30 天保留，`api_log_enabled` 可关）
- **迁移 v20**：api_keys（name/key_hash 唯一/scopes JSON/daily_limit 0=NULL 不限/last_used_at/revoked 行保留供对账）+ api_calls（key_id/method/path/status）
- **设置页「API」分类**（`ExtApiSection.tsx` 新增）：总开关+日志开关（即改即生效）、密钥表（备注/遮蔽密钥显隐+复制/scope 徽章/上限/最近使用/重置=旧串立即失效/吊销）、生成表单（备注+四 scope 勾选+每日上限）、基础地址+curl 速览、调用日志（最近 50 条，无密钥调用显示「无密钥」）、安全提示（scope 最小化/定期轮换/看日志）
- **`_AgentSSE` 加 origin 参数**（api/ai.py）：对外 agent 调用 origin=api，动作照常受账号授权位×模式约束、全量进 ai_actions 审计；ext 非流式 agent 把循环内 error 事件转 400（如无可用账号），不再 200 空回答
- **文档**：`docs/对外API使用指南.md` 新增（三步上手/scope 安全模型/端点一览+调用示例/三种隧道最小配置 cloudflared·Tailscale·SSH/FAQ）；ARCHITECTURE 同步（ext/extkeys 模块、v20 数据表、安全模型豁免与密钥条目）
- 验证：pytest 127 例全绿（新增 test_ext_api.py 13 例：health 免认证/未启用 403/缺坏 key 401/read 端点矩阵/scope 越权 403/批量动作契约/限流 429 monkeypatch/每日上限 429/密钥重置吊销往返/Host 豁免边界（ext 200 内部 403）/调用日志落库/agent 未配 AI 400）；ruff（app 门禁）通过；npm build（含 lint:font+tsc）通过；openapi.json+schema.d.ts 按新端点再生成；隔离实例（8807）冒烟——curl 矩阵（生成密钥→启用→读 accounts/drafts/contacts→坏 key 401→read-only 写 403→隧道场景外部 Origin+域名 Host 200→恶意 Host ext 豁免 200 内部 403→调用日志含被拒调用）+ 设置页 API 区截图确认
- 遗留：**真实隧道场景待用户**（自建 cloudflared/Tailscale/SSH 任一，按指南 §3 复现外部设备调用）；agent/chat/stream 真实 AI 配置下走查顺延（P6 遗留项一并）

## fe3d111 — v0.4 P6 验收修复（用户实测三问题）
- **总管家泄漏内部工具标记**：部分模型把自带的原生工具调用语法（实测 `<|DSML|invoke ...>` 形态）当普通文本输出，JSON 解析失败后整段泄漏给用户并终止会话——`_parse_model_action` 二次提取：JSON 协议失败后用正则抓取 DSML invoke 块（工具名+args JSON）还原为标准动作继续执行；系统提示词新增「禁止任何特殊标记语法」；纯文本回答不受影响
- **系统右键冲突**：应用层全局屏蔽 contextmenu（输入框/编辑区保留），树与邮件行的自定义右键不再被浏览器菜单抢焦点
- **邮件行右键菜单补齐（§4.3 承诺项）**：列表行右键 = 打开/标已读未读/星标切换/归档/删除/发件人加白名单/黑名单（多选状态下作用于整组）
- **文件夹排序**：大小写不敏感（`sensitivity: base` + numeric）——修复小写命名文件夹（如 test）沉底
- 验证：pytest 114 例全绿（+DSML 提取用例：标记→标准动作、纯文本→None）；npm build 通过；隔离实例（8793）浏览器验证文件夹新排序与行右键菜单渲染

## 56c1a95 — v0.4 P6: AI 总管家 2.0（对话 Agent · 双模式 · 审计）
- 依据 docs/REDESIGN_PLAN.md §6/§13 P6（方案核心工作量）
- **Agent 框架（§6.2）**：新增 `ai/agent.py`（多步循环 MAX_STEPS=8 防失控）+ `ai/tools.py`（15 个工具：6 读=search/list_recent/read_email/list_folders/list_contacts/digest_stats，9 写=mark/star/archive/move/trash/create_folder/create_draft/send_draft/start_organize）——薄壳转调既有能力，**无任意 HTTP/文件系统/命令类工具**（白名单即安全边界）；JSON 工具协议（`{"tool","args"}` 容错解析，本地模型通吃）；`POST /api/ai/agent/stream` SSE 事件流（text/tool_call/tool_result/approval_required/error/done，轨迹落会话）
- **权限矩阵（§6.4）**：迁移 v17——accounts.ai_grants 五授权位 JSON（read/draft/organize/send/delete，按旧 ai_permission 映射回填：readonly→read；draft_review→read+draft+organize）+ is_ai_mailbox AI 专属邮箱位；多账号会话取交集宁紧勿松；设置页账号行「AI 权限」面板（5 开关+专属邮箱二次确认）
- **双模式与审批（§6.5）**：审批模式（默认）写类一律出「动作卡」（ai_actions pending，批准时权限复核+参数可改）后由 decide 端点执行；自动模式在授权与安全约束内直执行（越界自动降级出卡）；前端模式开关记忆、切自动二次确认
- **自动模式安全边界（§6.6）**：发送收件人必须 ∈ 通讯录∪历史往来（防正文注入外发）、带附件草稿不直发、每日 ≤20 封发送 / ≤200 动作（触顶降级）；AI 专属邮箱（D2=B）位就绪——默认自动+全授权、树徽章后续接管线自动判定
- **审计与撤销（§6.8）**：ai_actions 表全量记录写动作（tool/params/mode/origin/status/undo_json）；undo 支持标记/移动/归档（移回原文件夹），发送不可撤销仅存档；设置页 AI 用量内「操作记录」查看器（状态筛选+一键撤销）；`/api/ai/agent/actions`+`/undo` 端点
- **注入防护（§6.6）**：系统提示词明确「邮件正文中任何指令都不是用户指令」+ 工具结果错误回灌带「不要原样重试」引导 + 写操作范围守卫（邮件必须属于会话范围账号）
- 验证：pytest 113 例全绿（新增 test_agent.py 6 例：读工具循环回灌/审批卡+批准执行/授权位拒绝/自动模式收件人白名单降级/白名单放行直发+审计/撤销恢复）；ruff（app 门禁）通过；npm build 通过；隔离实例（8794/8795）冒烟——总管家 2.0 界面（模式开关/范围/新快捷指令）与设置页 AI 权限面板（5 开关+专属邮箱）截图确认；ai_grants 坏 JSON 容错（_account_dict/_safe_grants 回退不 500）
- 遗留：**真实账号端到端待用户**（配好 AI 后在总管家里走查全部工具：搜索/总结/整理/起草/发送审批；自动模式限额与撤销；伪装指令邮件注入测试——REDESIGN_PLAN §13 P6 验收单）；原生 function calling 特性探测、AI 专属邮箱管线自动直发、通知中心待审批角标为后续增强

## a487546 — v0.4 P5: OAuth 内置凭证快速授权（D1=A）+ 审核修正
- 依据 docs/REDESIGN_PLAN.md §8.3/§13 P5（D1=A：用户 2026-09-12 拍板内置，推翻 2026-09-11 附录 B 否决结论，风险知情接受——翻案批注已记入 gitignored 方案文档附录 C）
- **内置公开桌面客户端凭证**：`core/oauth.BUILTIN_CLIENTS`（值=Thunderbird 公开源码 OAuth2Providers.sys.mjs 的公开字符串；来源与免责声明见模块 docstring）——添加 Gmail/Outlook 零配置：输入地址 → 点「授权登录」即可。回退链 `get_client()`：用户自建永远优先，未配置回退内置（source 标记 user/builtin）；内置登记回调路径 `/`（这类客户端只豁免端口不豁免路径，附录 B 实测结论）
- **令牌绑定签发客户端**：oauth_token 记录新增 client_id（签发者）；刷新经 `client_for_refresh` 按签发者选边——「授权用内置、之后配自建」（或反之）不会用错客户端导致 refresh_token 失效；旧版无记录令牌回退生效客户端
- **接口**：`/api/oauth/status` 三态（configured=自建已配置 / builtin_available / can_authorize + client_source + 生效客户端掩码与回调地址，openapi 已再生成）；PUT config 的 configured 语义收窄为「自建已配置」；授权失败回调页附「高级区配置自建客户端」降级引导
- **前端分层（§8.2）**：OauthSettings 卡片改「快速授权（默认，说明一行：零配置直接授权+公开信息免责）+ 各服务商行状态徽章（自建 xxx / 内置凭证·可直接授权）+「高级」按钮（自建表单收进行内，长教程移出操作区、留文档链接）」；AddAccountModal 授权按钮条件改 can_authorize，内置来源时提示「无需注册应用」，不可用时引导高级区
- **审核修正**：通知铃与「开启桌面通知」按钮块级堆叠把顶部图标区撑成两行 → flex 并排（b262021）；页签关闭 ✕ 在固定宽后悬在文字旁 → 标题 flex-1 占满、✕ 贴右缘（3b24fc8）
- **文档**：OAuth2 使用指南重构（§0 快速授权零配置置顶，原注册教程降级为 §1 高级）；ARCHITECTURE 两行同步
- 验证：pytest 107 例全绿（新增 test_oauth 3 例：内置回退+自建优先/refresh 绑定签发者/零配置 authorize；status 三态与自建往返用例更新）；ruff（app 门禁）通过；npm build 通过；隔离实例（8795）冒烟——status 三态字段全对、零配置 authorize URL（client_id=内置、redirect_uri=根路径、URL 不含 secret）、设置页分层 UI 截图确认
- 遗留：**真实账号端到端授权待用户**（零配置点授权 → 浏览器登录 → 回调建号 → 收发信；两台机器各自验证）；若服务商限制内置凭证，走高级区自建（引导已内置）

## a4c87f9 — v0.4 P4: 通讯录（自动采集 · 写信联想 · 管理界面）+ 审核修正
- 依据 docs/REDESIGN_PLAN.md §5.2-5.4/§13 P4
- **审核修正（e0a9bd9）**：AI 总管家/每日摘要入口从右上角按钮移入文件夹树「智能视图」分区（点开为页签，右上角仅剩 通知/设置/新邮件）；顶部页签统一宽度（w-44，浏览器式，标题截断）——修复「不同标签页长短不一」（关闭按钮 opacity-0 占位 + 基座页签无关闭位所致）
- **自动采集（零操作）**：v16 contacts 表（source auto/manual、use_count、last_seen_at；表达式唯一索引 COALESCE(account_id,0)+email 兜住 NULL 作用域去重）；sync 新邮件入库采集发件人；`outbox.send_user_draft` 发送成功采集 To/Cc/Bcc（支持「Name <a@x>」形态）；手动编辑过姓名（source=manual）的行不被采集覆盖、仅累计计数
- **写信联想**：新增 RecipientChipsInput——收件人/抄送/密送改 chips 形态（值仍是逗号分隔地址串，自动保存/发送无感）；输入触发 `/api/contacts/suggest`（150ms 防抖，use_count×最近加权、跨账号去重），↑↓ 选择、Enter 确认、逗号/失焦提交、退格删上一枚、非法地址红框
- **管理界面**：设置页新增「通讯录」分类——搜索、手动新增（全局作用域）、行内改名（转 manual）、删除；来源徽章（自动采集/手动）；导入/导出按钮置灰（v0.5）
- **接口新增**：`GET /api/contacts`（列表/搜索）、`GET /api/contacts/suggest`（写信联想）、`POST/PATCH/DELETE /api/contacts[/{id}]`（openapi 快照已再生成）
- 验证：pytest 104 例全绿（新增 test_contacts.py 3 例：采集 upsert+manual 保护/地址串采集+联想排序/API CRUD+守卫）；ruff（app 门禁）通过；npm build 通过；隔离实例（8796）冒烟——suggest 中英文/拼音子串命中、写信台输入「张」出联想（张三 <...> 5 次）→Enter 生成 chip、设置页通讯录表格（来源徽章/计数/删除）截图确认
- 遗留：真实账号下采集效果待用户验证（收几封信+发一封即见）；CSV/vCard 导入导出顺延 v0.5；拼音首字母匹配（trigram 覆盖全拼）待真实数据再调

## 554f896 — v0.4 P3: 草稿体系合并（待审+草稿箱 → 统一草稿）
- 依据 docs/REDESIGN_PLAN.md §5.1/§13 P3
- **数据统一**：user_drafts 成为唯一草稿存储（v19 加 origin ai/human + instruction 列，status 扩展 pending_review）；旧 drafts 表（AI 待审）数据由启动期 `outbox.migrate_legacy_ai_drafts()` 一次性并入——Markdown→HTML 与原 approve 发送同源、主题 Re: 化、收件人=原发件人、in_reply_to=原邮件软引用、状态映射 pending→pending_review/sent→sent/discarded→discarded；KV `legacy_drafts_migrated` 与数据同一事务原子提交（防中断出半份拷贝），旧表只读保留
- **发送通路归一**：`outbox.send_user_draft` 接受 pending_review——AI 待审「批准并发送」与手写发送同一条路（In-Reply-To/消毒/Sent 归档全复用），并对回复原邮件补标已读；api/drafts.py 退役删除（/api/drafts 路由不复存在），丢弃/恢复/带指令重写并入 /api/user-drafts（discard/reopen/regenerate + regenerate-for-email 供邮件视图一键拟稿）；调度器定时发送不受影响（只拉 editing/scheduled）
- **合并视图**：新增 DraftsHubPage（树单「草稿」节点进入）——分段筛选 待审/编辑中/定时中/已发送/已丢弃，行上 ✦AI/✎手写 徽章 + 指令徽章；待审稿操作=批准并发送/编辑后发送（进写信台同一通路）/重写（指令框）/丢弃；scheduled 可取消定时（回到来源态）；discarded 可恢复；详情预览走 HtmlMail 沙箱；列表 LEFT JOIN 原邮件带上下文
- **pipeline**：AI 拟稿直接写 user_drafts(pending_review, origin=ai)，主题 Re: 化、收件人=发件人
- **顺带修复**：通知面板在顶部图标区不可见（旧 bottom-0 锚定向上展开出视口）→ 改 top-full 向下展开（20e4b97）
- 验证：pytest 101 例全绿（新增 test_user_drafts.py 3 例：旧数据并入+幂等/待审流转+发送状态机/列表状态过滤+邮件上下文）；ruff（app 门禁）通过；npm build 通过；隔离实例（8797）冒烟——重启后旧 drafts 迁移进 pending_review（API 验证 origin/to/Re: 主题/HTML/instruction 全对），浏览器确认 /drafts→/?view=drafts 重定向、树单草稿节点、分段筛选、AI 徽章与 Markdown 正文预览渲染正常；编辑中手写稿的启动页签恢复为既有设计（非回归）
- 遗留：真实账号端到端（AI 生成→编辑后发送→原邮件标已读）待用户验证；树「草稿」节点未读/待审计数徽章顺延

## c56fd5c — v0.4 P2: 资源管理器（文件夹树完整版 · 归档=服务器移动）
- 依据 docs/REDESIGN_PLAN.md §4/§13 P2
- **归档语义改造（§4.6）**：archive=真实移动到每账号服务器端 Archived 文件夹（accounts.archive_folder，缺省 Archived，首归档惰性创建）；unarchive=移回收件箱；archived_local 降级为「待服务器归档」暂存标记（移动失败保留、下次管线自动重试）。单封走端点同步移动，批量/迁移走 imap_batch job；营销/黑名单自动归档经 pipeline `_sweep_server_archive` 落服务器
- **存量迁移流**：迁移 v15 对有 archived_local 存量的库落 KV `archive_migrate_done=0`（暂停自动清扫，防止未确认就搬历史邮件）；前端基座弹一次性提示「迁移 N 封 / 保留原地」；`GET /emails/archived_pending`+`POST archived_migrate/dismiss` 三端点；v15 同时建 folders 缓存表 + accounts.archive_folder 列
- **文件夹体系（§4.4）**：新增 core/folders.py（folders 表缓存、SPECIAL-USE 识别+中文启发式、folder_guard 系统文件夹守卫、RENAME 本地缓存/邮件/断点跟随、DELETE 清邮件行/断点/附件）+ api/folders.py（列表/刷新/创建/重命名/删除；改名删除的名字走查询参数——IMAP 名含分隔符）；旧 accounts.py 两端点迁入路径不变；账号删除连带清 folders 缓存
- **前端树完整版**：FolderTree 渲染服务器文件夹层级（INBOX→Archived→系统→自定义，分隔符组树、图标区分）；右键菜单=新建（子）文件夹/重命名/删除/刷新列表（确认弹窗，系统文件夹无改删项）；拖拽移动（列表行多选集合拖到树节点/账号行=INBOX，跨账号拖拽忽略=D4 决策）；All Mail 置灰守卫；MailBrowser 去账号/文件夹下拉与建夹 UI（树为唯一入口，留星标/分类/面包屑），新增键盘 j/k/x/o/Enter/e/#/c/// 与行拖拽源；MailBrowser 保留批量栏「移动到…」下拉（复用树缓存）
- **sync**：AI 管线只吃 INBOX 新邮件（按需同步的其他文件夹不分类/不生成草稿/不归档）
- **接口变更**：openapi.json 快照与 schema.d.ts 已再生成；`GET /accounts/{id}/folders` 返回 folders 表缓存行（name/delim/special_use/subscribed/is_system/is_archive）
- 验证：pytest 98 例全绿（新增 test_folders.py 3 例：识别矩阵/系统守卫/缓存与默认归档夹；batch 归档改为 job 契约测试）；ruff（app 门禁）通过；npm build 通过；隔离实例（8798，种假账号+存量归档数据）浏览器冒烟——迁移弹窗出现/保留原地关闭/账号展开文件夹层级渲染/Archived 选中切换（面包屑 demo@qq.com/Archived）/All Mail 置灰逐项截图确认
- 遗留：真实账号端到端验收待用户（Gmail+Outlook+QQ 各一：建夹/改名/删除/跨文件夹拖 50 封/归档后网页端可见/All Mail 不可误同步——REDESIGN_PLAN §13 P2 验收单）；树未读计数徽章与订阅文件夹低频轮询（§4.4 订阅同步）顺延；归档文件夹改名 UI（账号设置）顺延

## 651b070 — v0.4 P1: UI 骨架改版（砍侧栏 · 邮件基座 · 字号统一门禁）
- 依据 docs/REDESIGN_PLAN.md §3/§9/§13 P1（2026-09-12 定稿），本阶段纯前端
- **导航重设计**：删除应用左侧竖栏；「邮件」成为唯一常驻基座页签，AI 总管家/每日摘要/设置改为标签条右侧小图标按钮（点击才产生/激活页签，沿用 PAGE_TABS 记忆机制），通知铃与新邮件按钮同区；应用标识移至标签条最左
- **文件夹树骨架**：新增 `FolderTree`（智能视图：聚合收件箱/待审草稿/草稿箱/已归档 + 账号折叠组：状态点/展开记忆/INBOX 子节点）+ `MailPage`（基座组合页，视图初值取 URL）；MailBrowser 支持 `initialAccountId` 由树下发（key 换绑重挂）；树 P1 为只读骨架，服务器文件夹节点与拖拽随 P2
- **旧路由重定向**：/drafts→/?view=review、/mydrafts→/?view=mydrafts、/archived→/?view=archived；InboxPage/ArchivedPage 删除（并入 MailPage）；待审草稿节点与 AI/摘要图标在 AI 停用时隐藏（沿用 AI_ONLY 语义）
- **字号统一**：t-* 令牌成为唯一字号入口——88 处裸 text-xs/sm 等 + 19 处 text-[Npx] 全量迁移（standard/large 档数值微调 +0.5px，t-* 补行高）；新增 `scripts/lint-font.mjs` 门禁（npm run build 前置）禁止裸字号类回潮，白名单 Markdown/HtmlMail 富文本渲染
- 验证：npm run build（lint:font+tsc+vite）通过；隔离实例（8799，NMAIL_DATA_DIR=/tmp）浏览器冒烟——新布局/树选中/路由重定向/三档字号变量与视觉/AI 停用隐藏与恢复/写信按钮（无账号静默=既有行为）逐项截图确认
- 待办：真实账号下的树导航视觉走查由用户在下轮验证；P2 将把账号/文件夹下拉与树统一

## 31941a4 — fix: AI 档案被外力清空后不再自动恢复的自愈缺口（macOS 实例数据已恢复）
- 用户 mac 实例 AI 配置"消失"：排障确认主值 `ai_profiles` 在昨日 16:32 被旧版 ensure_migrated 静默重建缺陷写成空列表（备份停在 14:31 即为其指纹——正常删除走 save_profiles 会同步备份），空列表是合法 JSON，自愈只认"缺失/损坏"而不触发；随后孤儿密钥对账把失档 API key 清掉，造成"配置没了"
- 修复：`ensure_migrated` 把"空主值 + 非空备份"纳入自愈条件（正常删除走 save_profiles 时备份同步为空，不会误恢复故意删空的场景）
- 用户本机数据已按备份恢复（deepseek / api.deepseek.com / deepseek-flash，id 85efe150，设为激活）；密钥因孤儿对账已不在本机，需重新粘贴
- 验证：pytest 95 例全绿（新增 test_ai_profiles 5 例：清空恢复/故意删空保持/损坏恢复/备份双写契约/全新安装）；ruff 通过
- 说明：本次未触碰真实数据目录的写操作仅上述恢复（用户确认）；所有测试/冒烟均在临时目录

## 63dd644 — fix: SQLite 共享连接并发竞态（macOS 启动 500 根因）
- 用户 macOS 冷启动首屏并发（/api/settings、/api/ai/profiles）报 `sqlite3.InterfaceError: bad parameter or other API misuse` 且间歇自愈——潜伏 bug 在所有平台都存在，Python 3.14 调度时序把它炸了出来
- 根因（实测定位）：`get_conn()` 全局共享一条 sqlite3 连接，**Python sqlite3 层对同一连接的并发 execute 并不安全**——16 线程稳定复现 InterfaceError 与 `IndexError: tuple index out of range`，且只有带参数的语句中招（无参读/tx 写零错误）：语句缓存与参数绑定状态被并发重置；SQLite 序列化模式（threadsafety=3）只保护单次 C API 调用，兜不住 Python 层多步执行序列。原懒初始化还把半初始化连接（PRAGMA 未跑完）提前发布，属第二重竞态
- 修复：`get_conn()` 改为**每线程独立连接**（threading.local，线程内复用；WAL 下多连接读写互不阻塞，写侧仍由 tx() 全局写锁串行）；新增 `close_thread_conn()`，同步一次性线程（`sync.start_sync` 每次 spawn daemon 线程）收尾时关闭防连接泄漏
- 验证：并发锤 16×300 次参数化读+写事务从 12-15 错误归零；pytest 90 例全绿（新增线程隔离/连接关闭 2 例回归）；ruff app 门禁通过；HTTP 冷启动 3 轮 × 32 并发全 200、服务端日志零 InterfaceError
- 遗留：用户重启进程生效

## 2135257 — OAuth 回调路径按客户端可配置（loopback 根路径兼容）
- 背景：用户拟内置公开桌面客户端凭据实现一键授权（方案文档含凭据值，审核后仅存本机不入库）。经审核：**凭据值不入仓库**（TB 源码明文禁止复用——"Don't copy these values for your own application"；公开仓库即分发，Google/Mozilla 均扫描公开代码），只采纳其技术基座——回调路径可配置；凭据由用户在各机设置页自行粘贴（secrets.json 随数据目录持久化，双机各配一次）
- 后端：`oauth_client:{provider}` 存储新增 `redirect_path`（缺省 `/oauth/callback`，坏值兜底回退默认；默认值不落盘保持旧配置结构不变）；授权 URL 与令牌交换按客户端路径拼装回调地址；`GET /` 新增根路径回调——按 state 参数与 SPA 首页分流（授权重定向必带 state），api_router 先于 SPA 挂载注册故仅拦截精确 `/`；`DIST_DIR` 解析从 main.py 移至 config.py（api 层需读取，避免循环导入）
- 前端：回调地址下沉到各服务商行内（地址随登记路径变化，带复制按钮），编辑面板新增「回调路径」输入；`/api/oauth/status` 响应移除顶层 `redirect_uri`、改为逐服务商 `redirect_path` + `redirect_uri`（**接口变更**，openapi.json 快照与 schema.d.ts 已同步再生成）
- 动机（技术事实）：Google/微软对 localhost 回环只豁免端口、不豁免路径——登记为根路径 `http://localhost` 的客户端（公开桌面端凭据均如此）必须以 `/` 回调，原固定 `/oauth/callback` 必报 redirect_uri_mismatch
- 验证：pytest 88 例全绿（新增 redirect_path 往返/坏值兜底/状态端点契约/根路径分流 5 例）；ruff（app 门禁）通过；npm build（含 tsc）通过；隔离实例冒烟——根路径无 state 出 SPA、带 state 出回调页、SPA 子路由不受影响、未构建时 404
- 遗留：真实凭据端到端授权待用户双机（Windows/macOS）各粘贴一次后验证；tests/ 目录 3 处既有 ruff 提示（F841/SIM117 等，官方门禁只查 app/）不属本变更

## 58c2216 — docs: OAuth2 使用指南（面向使用者的实操手册）
- 新增 docs/OAuth2 使用指南.md：三层配置总览（OAuth 客户端 → Nmail 授权 → Outlook 邮箱侧开关）、Gmail/Outlook 客户端注册步骤（含桌面型 vs Web 型选择）、大陆网络与代理策略、**11 条排错对照表**——全部为本日真实踩坑（org_internal / redirect_uri_mismatch / client_secret missing / assertion required / 10061 / authenticated but not connected / 535 / WRONG_VERSION_NUMBER 等）
- 起因：用户单日连续踩完上述全部坑后的总结诉求；每个 Outlook 邮箱需单独开 POP/IMAP（应用侧链路正确时仍报 authenticated but not connected 的唯一原因）
- 设置页 OAuth 卡片步骤列表补指南指引；npm build 通过

## 5d633f0 — fix: SMTP XOAUTH2 认证回调契约（Gmail 发信必败修复）
- 用户真实发信首测即中：smtplib.auth 的 authobject **首次是无参调用**（取 SASL 初始响应），lambda 带一个必选参数直接 TypeError（`_smtp_auth.<locals>.<lambda>() missing 1 required positional argument`）——Gmail OAuth 发信 100% 失败
- 修正回调签名：`lambda _challenge=None: auth_str if _challenge is None else ""`——无参调用回初始响应串；服务器 334 挑战（XOAUTH2 错误应答约定）回空串让服务器给出最终错误。IMAP 侧不受影响（imaplib 的 authenticate 恒带参调用）
- 该报错同时佐证用户代理链路已通：连接与 EHLO 均成功，仅认证步骤崩
- 验证：pytest 84 例全绿（新增回调契约回归：无参初始响应=完整 XOAUTH2 串、挑战应答=空串）；ruff 通过

## f74dfdb — fix: OAuth 换令牌代理降级——代理不可达自动直连（Outlook 误伤修复）
- 用户实测：Outlook 授权在大陆直连可达，但换令牌被"无条件跟随全局代理"设计拦死（代理端口没开 → WinError 10061 拒绝）——原设计假设"OAuth 服务商都是被墙方"不成立
- 修正：全局代理非空时优先走代理；**建连类失败**（transport 标记：拒绝/超时/ImportError）自动降级直连重试一次；**业务拒绝**（invalid_client 等）不重试（直连结果相同）；未配置代理行为不变（httpx trust_env 仍生效）。Gmail 直连必死场景如实报错，文案不变
- 设置页代理提示文案同步改为「优先走此代理、代理不可达自动直连」
- 验证：pytest 83 例全绿（新增 3 例：代理拒绝→直连兜底/业务拒绝不重试/无代理只直连一次）；ruff + npm build 通过

## ad2a43a — 网络代理：被墙服务商（Gmail/Outlook）的 IMAP/SMTP/OAuth 可走本机代理
- 背景（用户真实实测）：大陆裸连 imap.gmail.com 全挂（10054 重置/10060 超时），QQ/163 正常；浏览器与 httpx 认代理环境变量所以授权能通，IMAP/SMTP 是裸 socket 直连撞墙。单封邮件操作同时 502 证明是连接层不通而非同步量过大
- 用法：设置-通用 填「网络代理」地址（socks5://127.0.0.1:7890，支持 socks5h/socks4/http 与 user:pass@）→ 邮箱账号列表对被墙账号点「代理」开启；Gmail/Outlook OAuth 令牌交换无条件跟随全局代理（服务商本身就是被墙方，QQ/163 不走 OAuth）；本机回环地址（Proton Bridge 等）始终直连豁免
- 实现：新增 `core/netproxy.py`——PySocks（纯 Python 新依赖）套接字 + 标准库注入点子类化（imaplib `IMAP4_SSL._create_socket` / smtplib `_get_socket`），不做全局 socket 替换（避免波及本地连接与并发线程串代理）；socks5 默认远端解析（rdns）规避 DNS 污染；代理地址坏配置时静默直连由 connection_error 兜底。迁移 v14（accounts.use_proxy）；设置 `network_proxy` 即时校验（422 人话文案）；IMAP/SMTP/OAuth 三处建连全部接管
- 验证：pytest 80 例全绿（新增 10 例：URL 解析矩阵/本地豁免/开关×地址组合/坏配置降级/httpx 参数/类选择/建连配置捕获/设置往返与 422/账号开关往返）；ruff 通过；npm build 通过；隔离实例冒烟（设置往返、非法代理 422、账号开关 404 语义）；本机真实探测复证裸连 Gmail 超时而 QQ 0.06s
- 说明：自动探测（autoconfig）未接代理——未收录域名的探测多为可达目标，需要时随触碰再接

## 304e4a4 — fix: OAuth 回调两处加固（真实用户首授权发现）
- **OAuthError 缺 `.message` 属性**：回调捕获授权错误后取 `exc.message` 渲染错误页时抛 AttributeError，把可处理的业务错误（如 Google 拒绝换令牌）变成裸 500——报错本体贴不出来。补齐属性（对齐 MailError 形态）；mailbox.load_account 同链路一并受益
- **回调绝不裸 500**：回调是浏览器直接导航的落地页，try 范围扩到换令牌→建号→首同步全程，任意意外异常渲染为 200 错误页（含异常类型+消息，截断 300 字）并落流程状态供前端展示
- **错误翻译补齐**：Google 对 Web 型客户端缺 secret 只回 `error_description`（`client_secret is missing.`），翻译层现按描述文本识别并给出可操作指引（补填 client_secret 或改用桌面应用类型）；`_token_request` 另接住 SOCKS 代理环境变量缺 socksio 的 ImportError（非 HTTPError 子类，实测会裸 500）
- 验证：pytest 70 例全绿（新增 4 例回归：.message 属性/错误翻译矩阵/SOCKS ImportError/回调任意异常不 500）；ruff 通过
- 用户实测触发：Google 控制台建的是 Web 型客户端且未填 client_secret——修好后补填 secret 或改桌面型即可走通

## ed79b87 — Gmail / Outlook OAuth2 授权登录（XOAUTH2）
- 依据 docs/自建邮箱客户端 Gmail+Outlook OAuth2 完整教程.md 落地：Google/微软已停用账号密码直连，Gmail/Outlook 账号改走 OAuth2 授权码 + PKCE 流程（用户自建 OAuth 客户端，client_id 填设置页；不内置凭据）
- 后端：迁移 v13（accounts.auth_type/oauth_provider）；新增 `core/oauth.py`（PKCE/授权 URL/换令牌/令牌刷新按账号加锁防并发、XOAUTH2 编码、流程状态 TTL）与 `api/oauth.py`（status/config/authorize/flow 轮询 + `/oauth/callback` 回环回调直出自关闭 HTML，回调里完成换令牌→建/转账号→首同步）；`imap_client`/`mailbox` 支持 `access_token` 认证通路（IMAP `xoauth2`、SMTP `AUTH XOAUTH2` 带裸 docmd 回退）；删除账号联动清令牌，OAuth 账号拒绝改密
- 令牌存储：secrets.json `oauth_client:{provider}` / `oauth_token:{account_id}`（expires_at 预扣 120s 余量；微软轮换 refresh_token 随保存覆盖），不回传前端
- 前端：新增 `components/OauthSettings.tsx`（设置页 OAuth 配置卡：client_id/secret 登记、回调地址复制、分服务商步骤提示；账号行「重新授权」按钮 + useOauthAuthorize 弹窗轮询公共 hook）；AddAccountModal 识别 Gmail/Outlook 域名时展示「使用 XX 账号授权登录」入口（未配置时给指引）；账号列表 OAuth2 徽章
- 验证：pytest 66 例全绿（新增 22 例：XOAUTH2 编码二进制 \x01/PKCE/授权 URL 参数契约/令牌刷新轮换与容错/流程 TTL/API 语义矩阵/回调建号与转号/删号清令牌）；ruff 通过；npm build（tsc 含）通过；隔离实例冒烟（迁移 v13 到位、动态回调地址随端口、Gmail/Outlook 授权 URL 参数、未配置 400 文案、回调无效 state/access_denied/轮询终态、前端托管正常）
- 遗留：真实 Google/Microsoft OAuth 客户端的端到端授权（换真实令牌、IMAP/SMTP 实连）待用户按教程完成控制台配置后验证

## 5afa93a — 工程化：OpenAPI 类型生成基建（3.7a）
- 新增 devDependency `openapi-typescript` + `npm run gen:api`；`frontend/openapi.json` 为后端 schema 快照（随 API 改动更新、同提交），生成 `src/api/schema.d.ts` 供接口类型消费
- CLAUDE.md 常用命令新增更新流程一行；存量 types.ts 手写类型按计划渐进替换（新增端点优先走生成类型）
- 验证：tsc + vite build 通过（schema.d.ts 与现有类型无冲突）

## 7cdb59e — 重构：前端公共件归拢（3.7b）——hooks/useFlash + utils/format
- `hooks/useFlash`：通知横幅统一定时清理（重发重置计时、卸载清定时器），替代 DraftsPage 手写 flash 与 MailBrowser ×9 的 `setTimeout(setSyncMessage(null))`
- `utils/format`：shortDate/formatDate/fmtSize/relativeTime 四处定义归一，四文件改为导入，行为逐字保留
- 顺修遗留：MailBrowser「同步失败」横幅此前没有定时器、永不清除——现由 useFlash 默认时长兜底
- 验证：npm build（tsc 含）通过

## b4050a8 — 工程化：新增 CI 门禁（T3）
- `.github/workflows/ci.yml`：push main / PR 触发——backend job（`pip install -e . pytest ruff` → ruff 五规则+TID251 → pytest 44 例）+ frontend job（npm ci → build 含 tsc）；此前主干只有 tag 触发的 release.yml，无任何门禁

## 372bf0a — 测试：pytest 基础层 44 例（T1，纯函数层优先）
- 覆盖：mail_html 消毒 XSS 样本集（script/onclick/javascript:/iframe/远程图计数与占位/data: 收发差异/cid 内联与缺文件降级）、`_extract_json` 稳健解析、`match_sender_list` 契约（写入侧已 lower）、`reply_subject`、autoconfig `_server_from_xml`（SSL/缺省端口/坏端口回退/明文拒绝）、`_is_newer` 数值比较与垃圾输入、迁移幂等（连跑两遍 + v12 到位）、tx() 提交/回滚、get_setting 坏值容错、TestClient 下的 list_emails 筛选矩阵与 batch 归档往返、S1 守卫五形态
- conftest 以一次性临时目录隔离数据（绝不触碰真实用户数据）；pyproject 增 pytest 配置（testpaths/pythonpath）
- 修正测试自身的三处初版误设：搜索按设计忽略文件夹过滤（4 封全含「邮」）、tx 直插裸值经 json.loads 还原为 int、名单大小写契约在写入侧
- 验证：44 passed

## 0690420 — 工程化：版本号单一来源（T5）
- `app/config.py` 运行时读 `importlib.metadata.version("nmail-app")`；源码直跑/冻结环境无元数据回退常量——改版本只需改 pyproject.toml；ARCHITECTURE 分发表说明同步更新
- 验证：源码模式 /api/health 正常回退 0.1.0

## 71d1aea — 工程化：ruff 扩规则一次收敛（T2）
- 检查命令升级 `--select F,E9,B,SIM,UP,TID251`（CLAUDE.md 同步）；存量 42 条清零——UP 时区别名/collections.abc、SIM105 contextlib.suppress 化 ×6、B904 raise-from 补全 ×6、B905 zip strict、B023 闭包改参数传递（iter_new_mail._fetch_one）
- 两处 noqa 为已知误报/惯用法：SIM118（sqlite3.Row 的 `in` 是值语义不是键）、B008（FastAPI `File(...)` 依赖注入）
- 验证：ruff 全绿 + 隔离实例 /api/health 冒烟

## e5eafc9 — fix：R7 本地库保留策略——启动时通知留 500 条 / ai_logs 留 90 天，UIDVALIDITY 重置清附件孤儿目录
- notifications / ai_logs 无界增长（本地单机库长年累月必胀）；启动（lifespan）执行 `cleanup_retention`——通知按 id 留最新 500 条、ai_logs 删 90 天前；断言验证 600→500、过期清/近期留
- UIDVALIDITY 重置分支此前只删 emails 行（附件行随 FK 级联），磁盘 `accounts/<id>/attachments/<email_id>/` 成孤儿——重置时先收旧 id 再顺带 rmtree 各自目录
- 验证：ruff（F,TID251）；隔离库断言 600→500 / 过期 0 / 近期 1

## d1c3a1b — 功能：批量 trash/move 异步化——core/batch_ops 任务体 + 端点分支 + 前端批量进度条
- 批量删信/移动需逐账号 IMAP 操作，耗时随批量线性增长——从 api/emails.batch_action 迁出为 `core/batch_ops.imap_batch_job`（按账号分组共用连接、进度按账号上报，R2 删行重建语义原样保留）；端点对 trash/move 立即返回 `{ok, job_id}`，打标/归档类快操作仍同步返回原结构
- 前端：`useJob` 第二实例跟踪批量任务，列表工具条内联进度条（JobProgressBar 复用），终态展示 `{updated, failed}` 并失效列表缓存；批量按钮在任务运行期间统一禁用
- 验证：ruff、npm build；隔离实例端到端——trash 立即返回 job_id、IMAP 不可达时任务 done 且 `{updated:0, failed:3}`（服务器失败不动本地语义保持）、进度字段就位

## 8f6b417 — 功能：AI 整理异步化——organize 提交 job 立即返回 + 进度上报，前端 useJob + 进度条（M3 核心）
- 「AI 整理」原同步执行（大账号分钟级 HTTP 挂起、双击重复触发）——迁为 `core/pipeline.organize_job`：逐账号补分类并按账号上报进度，结果结构不变写入 result_json；`POST /api/ai/organize` 立即返回 `{job_id}`，同账号重复点击去重复用同一 running 任务
- 前端新增 `api/useJob.ts`（1s 轮询、终态自动停并回调）：MailBrowser「AI 整理」改走 job + 工具条内联进度条（百分比+当前账号），完成后展示与原版一致的汇总文案
- runner 注册机制：业务模块 `@jobs.runner(kind)` 自注册，main.py 导入 pipeline/batch_ops 确保注册先于可用
- 验证：ruff、npm build；隔离实例端到端——organize 立即返回 job_id、任务 done 携带 skipped_no_ai 语义、重复提交去重；执行器单测式断言（进度 0.5→1.0、result_json 落库）

## fde0745 — 功能：jobs 基建——迁移 v12 + core/jobs 执行器 + GET /api/jobs/*（M3 第一步）
- 迁移 v12（只追加）：jobs 表（kind/account_id/status/progress/stage/detail/result_json/时间戳）+ running 索引
- `core/jobs.py`：ThreadPoolExecutor(max_workers=2) + `@runner(kind)` 注册表 + `submit`（dedupe 可选：同 kind+同账号 running 复用）+ `report`（进度/阶段/明细）+ 失败进表不进 HTTP + `get_job`/`list_active`
- 新增 `GET /api/jobs/active`（观测口）与 `GET /api/jobs/{id}`（前端轮询用，404 语义）
- 验证：ruff；隔离实例——v12 生效（max version=12）、active 空列表、404 形态、执行器提交→上报→done 全链路断言

## 9f0bc5e — 工程化：ruff banned-api 固化分层规则（T4）
- pyproject `banned-api` 禁 `app.api`（main/api/tests 白名单放行），CLAUDE.md 检查命令升级 `--select F,TID251`
- 实测：core/ 下违规 import 被拦截、现库全绿——「core/scheduler/ai 不得依赖 API 层」从约定变成门禁

## 54ef776 — 重构：分类枚举单一来源 ai/categories.py + GET /api/meta（解 A6）
- 加分类从改 6 处 → 改 1 处：CATEGORIES（key/label/色板/徽章类/判定说明）一处定义——prompts 分类段自动生成（「六选一」随枚举数动态化）、tasks 结果校验、pipeline 自动归档集合、digest 分桶顺序、`GET /api/meta` 下发，全部消费同一来源
- 前端 `api/useMeta.ts`（react-query 拉取一次长缓存 + 内置回退清单）：MailBrowser 分类筛选/行内徽章、DigestPage 图表色改走下发数据；色值与徽章类保持原值不变（原 ΔE 调色板校验结论仍成立）
- 验证：ruff、npm build（tsc 含）通过；隔离实例 `/api/meta` 冒烟返回六分类完整字段

## 6b57584 — 重构：AI 收口——deps 统一错误翻译 + tasks._logged 统一用量记账（解 A5）
- `api/deps.py` 新增 `ai_config_or_400`（未配置/停用 → 400，副作用前预检用）与 `ai_result_or_http`（AI 调用统一翻译：未配置 400 / ValueError 400 / 其余 502）；ai.py ×5 端点 + drafts.regenerate 的 try/except 样板全部收口——**新增 AI 端点零样板**（拿 write 端点当样例）
- `ai/tasks.py` 新增 `_logged` 上下文管理器：正常退出记成功用量（可 `ok(usage)` 注入）、异常记失败日志（摘要=异常截 200）再抛——classify/draft/chat/write/digest 六函数七对样板归一；流式路径以 `usage_out` 共享 dict 保留「失败也记累计用量」语义
- 验证：ruff 通过；隔离实例冒烟——未配置 AI 时 write 与总管家流式均 400 且文案正确区分、usage 正常

## 2cd5e74 — 重构：发送通路归一——mailbox.send_message 唯一发送 + core/outbox 草稿发送，调度器脱离 API 层（解 A2/A8，删 _imap_for）
- **唯一发送路径**：`core/mailbox.py` 新增 `send_message()`（SMTP 未配置校验→发送→归档 Sent）与 `split_addresses()`（原 emails.re_split 迁入）；新增 `core/outbox.py`——`send_user_draft()` 是写信台草稿发送的唯一实现（状态校验/地址解析/消毒+纯文本派生/In-Reply-To/标记 sent/清附件），失败一律抛 `MailError`（后台线程不再出现 HTTPException）
- **A2 消除**：scheduler 定时派发改调 `core.outbox.send_user_draft`，`scheduler → app.api` 反向依赖归零（grep 验证 scheduler/core/ai 无 app.api 引用）
- **API 薄壳化**：新增 `api/deps.py`（MailError→HTTP 统一翻译表）；user_drafts/emails(batch+单封)/drafts.approve/accounts(文件夹×2) 全部改走 `mailbox.load_account/open_imap/send_message`；`_imap_for` 删除
- **MailConfig 构造 8→1**：全项目仅剩 `mailbox.load_account` 一处；accounts.py 两处（添加账号预检/改密预检）为文档化例外——密码来自请求而非凭据库
- 验证：ruff 通过；隔离实例预置账号+草稿，端到端 6 项冒烟——无 SMTP 400/空收件人 400/草稿不存在 404/文件夹 404/health 正常/失败不污染草稿状态；**真实账号发信回归（user_draft + AI approve 串线与 Sent 归档）待用户重启后验证**

## 06f2da2 — fix/加固：AI 档案一致性——双写备份防丢 + 主值丢失自愈 + 孤儿密钥对账清除 + 保存回填所见即所存
- 背景（接 8e8dd2f 排障结论）：`ai_profiles` 主值曾在 09-11 05:25–07:27 间被外力抹掉，`ensure_migrated` 把「读不到」误判为旧版升级，静默重建单档案——真实档案全部消失、密钥成孤儿、失效旧 key 复活成现役（401 事故闭环）。用户拍板三条硬要求：保存即所见=所存、删除即删干净、绝不刷新后丢失
- **双写备份**：`save_profiles` 同步写 `ai_profiles_backup`（最后一份有效列表）；`ensure_migrated` 读不到主值（缺失/损坏/非列表）时先从备份完整恢复（active 失效则回落首个档案），有备份绝不走旧配置重建；无备份才回落全新安装/旧迁移路径
- **孤儿对账**：`ensure_migrated` 末尾 `prune_orphan_secrets`——不被任何档案引用的 `ai_profile_key:*` 即读即清（增删改/恢复/重建全路径兜底）；legacy `ai_api_key` 不在清理范围
- **secrets.json 原子写**：临时文件 + `os.replace`——写一半崩溃/并发写不再可能留下损坏 JSON（坏 JSON = 全部密钥读回 None）
- **前端保存回填**：档案卡保存成功后用落库返回值回填输入框（后端已 trim），页面显示与本地存储强制一致，不再依赖 refetch 时序
- 验证：ruff、npm run build 通过；隔离实例（真库副本）场景矩阵——S1 首读即清 3 把孤儿（83c543e0/c9f6765f/39693236，legacy 与在用密钥保留）+ PATCH trim 往返一致 + 备份落盘；S2a 删除主值→备份完整恢复（含 api_key）；S2b 主值坏 JSON→自愈重写；S3 空目录全新安装→空列表且不建 secrets.json

## 8e8dd2f — fix：AI 密钥 401 排障（恢复有效密钥）+ 测试连接空密钥直测不回退 + 401 人话提示；迁移 v11 清语气学习残留用量
- **排障结论（非程序问题）**：设置页 401「****42b0 is invalid」根因是该 key 在 DeepSeek 平台侧被删除/重置——ai_logs 证实同 key+model 至 09-11 04:16 仍成功跑 58 次、07:27 起同一存储密钥连吃 401，期间本地零变更；裸 curl 绕开应用复现同错。保存管线无损：界面显示=DB 档案=secrets.json=报错指纹四处一致
- **处置**：secrets.json 里仍存有用户后生成的有效 key（****75dc，属已删档案 83c543e0 的孤儿密钥），已写回激活档案，测试连接实测 ok（1.3s）
- **测试连接语义修复**：前端由「api_key 非空才发送」改为全量直发——清空 Key 点测试=按空密钥直测（占位 EMPTY），不再偷偷回退已存旧密钥误导排障；省略字段（None）回退档案密钥的便捷语义保留
- **401 人话提示**：`llm.friendly_error` 给鉴权类错误统一追加「401 通常不是保存失败，而是该密钥已在服务商平台被删除/重置」提示，`/api/ai/test` 与 `/api/ai/models` 两处生效
- **迁移 v11**：`DELETE FROM ai_logs WHERE task_type='tone_dna'`——语气学习（v10 退役）残留的 2 条历史用量清除，AI 用量页不再出现「语气学习（已下线）」行；前端同步删 TASK_LABELS 的 tone_dna 映射
- 验证：ruff、npm run build 通过；隔离实例（真库副本）curl 往返——v11 迁移后 tone_dna 2→0、usage by_task 无 tone_dna；test 端点「省略=回退档案密钥 ok / 空串=EMPTY 直测不回退 / 坏 key=带人话提示」三态逐一验证

## 0b549c9 — 重构：数据库事务边界 tx() + autocommit 切换（同一提交，行为等价）
- 落地 IMPROVEMENT_PLAN §3.2：连接改 `isolation_level=None`（autocommit，单条语句即生效）——存量 ~30 处 `conn.commit()` 变无害 no-op，现有调用点无需同步改造；补 `PRAGMA synchronous=NORMAL`（WAL 推荐档，免逐提交 fsync 拖慢分块入库）与 `busy_timeout=5000`（跨进程写冲突兜底）
- 新增 `tx()`：进程内全局写锁 + `BEGIN IMMEDIATE`，成功提交、异常回滚（含 SQLite 已自动回滚的容错）——多语句原子性有了显式入口，后续新增代码一律走 tx()；存量多语句点（batch_action、_apply_classification 等）随触碰机械替换
- 语义验证（隔离库）：多语句原子提交 ✅ / 中途异常全量回滚 ✅ / set_setting 往返与坏值容错 ✅；应用启动冒烟通过

## fadc747 — 重构：新增 core/mailbox.py（账号凭据/连接统一入口），sync.py 切换为首个消费者
- 落地 IMPROVEMENT_PLAN §3.1：`load_account`（查账号行+读密钥 → AccountHandle，缺一抛 `MailError(not_found|missing_credential)`）成为**全项目唯一 MailConfig 构造点**，`has_credentials`/`open_imap` 一并收口
- `core/sync.py` 切换：`sync_account` 的 get_secret+MailConfig 拼装与 `connect_imap` 直连改走 `mailbox.load_account`/`mailbox.open_imap`，`start_sync` 的凭证预检改 `has_credentials`——原「缺少密码凭证」文案由 MailError.message 承接，行为不变
- API 层其余 7 处拼装（accounts/emails/drafts/user_drafts）按计划 M2 逐个迁移后删除 `_imap_for`；添加账号入库前的表单直连预检为文档化例外
- 验证：ruff 通过；隔离实例冒烟 /api/health、无账号手动同步 404 正常

## 9ab675a — 安全：本机 API 加 Origin/Host 来源校验中间件（挡 drive-by POST 与 DNS rebinding）
- 服务虽仅绑定 127.0.0.1，但恶意网页可向 `http://127.0.0.1:8720` 发 multipart 无预检 POST 触发本机 API（drive-by，例如伪造发信/改数据）；公网域名经 DNS rebinding 解析到 127.0.0.1 后亦可携带自身域名访问（IMPROVEMENT_PLAN S1/R5）
- main.py 新增中间件：Host 必须为本机主机名（端口与实际监听一致才严格比对）；浏览器附带 Origin 时必须为本机源（curl 等无 Origin 的本机工具不受影响）；静态资源与 /api 一并覆盖
- `vite.config.ts` 代理补 `changeOrigin: true`——否则 dev 代理转发时保留 `localhost:5173` 作 Host，会被新校验拒绝
- 验证：隔离实例 curl 矩阵——正常访问 200 / 坏 Host 403 / 外站 Origin 403 / `Origin: null` 403 / 同源 Origin 放行；ruff、npm run build 通过

## d34a54a — fix：总管家流式接口先验 AI 配置再落库用户消息（原未配置时留孤儿消息）
- `POST /api/ai/chat-manager/stream` 原顺序：先 `append_message(user)` 落库，再创建生成器——AI 未配置/停用时抛 AINotConfigured 返回 400，但用户消息已入库，且 assistant 回复永不出现，会话里留下孤儿提问（IMPROVEMENT_PLAN R8；非流式版本顺序本就正确）
- 修复：入口先 `tasks._ai_config(profile_id)` 预检（与生成器内部同一校验），未配置直接 400，不落库；M2 的 deps.py 依赖收口将替代此调用

## 56b9883 — fix：AI 上下文/每日摘要改用 date_sort 排序（原混合时区 e.date 字符串比较漏算日界）
- `_manager_context`（总管家上下文）与 digest `_collect_stats` 的 `e.date >= ?` 时间窗、`ORDER BY e.date`、"重要邮件"排序全部建立在混合时区 ISO 串的字典序上：+08:00 与 +00:00 的邮件交错时，日界多算/漏算、排序错位（IMPROVEMENT_PLAN R6）
- 统一切到迁移 v7 已建的 `date_sort`（UTC 归一）：SQL 比较/排序用 `COALESCE(e.date_sort, e.date)`（畸形日期无 date_sort 时回落原值）；摘要"重要邮件"的 Python 侧排序同切 date_key，对前端展示字段 `date` 无影响

## 208443c — fix：get_setting 容错损坏的设置值（原 json.loads 裸抛 → 所有读取请求 500）
- settings 表单值若被外部写坏（非 JSON 字符串），`get_setting` 的 `json.loads` 裸抛异常，所有依赖该设置的接口（轮询间隔、摘要时间、AI 开关等）集体 500，且无自愈路径
- 修复（IMPROVEMENT_PLAN R9）：解析失败回退 default；坏值在下次 set_setting 保存时自然被覆盖

## 393293e — fix/安全：删除死代码端点 POST /api/emails/send（附件名路径注入 + 发送逻辑三轨之一）
- 前端写信台二期后该端点零调用（client.ts 的 sendEmail 无人调用），发送已收敛到 user_drafts 一条链路——保留只会三处各写一遍消毒/纯文本派生/归档 Sent（IMPROVEMENT_PLAN A8），且其附件落盘 `tmp_dir / f.filename` 未剥路径分隔符，恶意 multipart 文件名（`../../x`）可写任意位置（R4）
- 删除：后端端点与临时目录逻辑、前端 `sendEmail` 客户端方法；`_imap_for` 保留（M2 收口时随 core/mailbox.py 迁移）
- 验证：ruff、npm run build 通过；隔离实例冒烟——POST /api/emails/send 已无处理器（405）、/api/health 与 /api/emails 正常

## 4c22b2f — fix：move 邮件拿不到新 UID 时旧 uid 写进新文件夹（撞 UNIQUE + 增量跳过）→ 删行交增量重建
- 批量与单封 move 此前 `uid = COALESCE(?, uid)`：服务器未回目标文件夹新 UID 时，旧 uid 原样写进新文件夹——与源文件夹同 uid 的行撞 `(account_id, folder, uid)` UNIQUE 报错，即使侥幸写入，下次增量同步从新文件夹 last_uid 起步也永远扫不到它，信"消失"
- 修复（[IMPROVEMENT_PLAN](IMPROVEMENT_PLAN.md) R2）：批量 `batch-action` 与单封 `action` 两处一致——拿不到新 UID 即删除本地行，交下次增量同步按服务器真实状态重建；不再有中间态脏行

## 6fbf821 — docs：IMPROVEMENT_PLAN 修订（对齐代码现状）
- 逐条对照当前代码核实提升计划：R1（IMAP 超时）、R10/3.5（分块拉取）、A9 同步侧（后台化+进度）、T6（.gitignore）确认已由同步引擎系列提交（e8c0084…28ef2df）解决，移出待办；M3 缩窄为「AI 整理/批量动作异步化」；修正前端文件路径（src/types.ts、components/MailBrowser.tsx）与通知横幅规模（flash ×8 + syncMessage ×19）；A4→A5 编号笔误、MailConfig ×8 等其余断言经核实成立

## efd36e2 — fix：Errno 22 真凶——畸形 Date 头（1900-01-01）令 astimezone 抛 OSError，同步死循环
- 埋点复现终于定位真凶：QQ「已删除」文件夹里 3 封垃圾邮件（notifications@whizzzest.com 伪造验证码）Date 头为 `1900-01-01T00:00:00`，`astimezone()` 在 Windows 换算 1900 年越界抛 `OSError: [Errno 22] Invalid argument`——同一封邮件每次同步必死、断点永远推不进。此前所有 Errno 22（含最初 14:16 那次）皆为此因；INBOX 无此邮件故一直正常。前几轮的分块/断点/退避是真实加固（保留），但真正命门在此
- 修复：`_norm_date` 容错——astimezone 失败降级为原值入库、date_sort 置空（排序沉底），摘要的 `_to_local_dt` 同步扩展异常类型。真机端到端验证：真实 sync_account 跑通「已删除」文件夹 ok=True 新增 383 封 54.5s，账号状态恢复 ok；顺带发现 1900-01-01 垃圾邮件冒用用户自有域名发验证码，建议拉黑
- 附带：重试改为 3 次退避（15s/45s）；分块调小至 25 封并加块间节流，缩短被服务商掐断时的损失窗口

## bb9d796 — fix：稀疏文件夹（已删除/已发送）同步撞超时 → 按密度自适应拉取 + 账号/文件夹选择持久化
- 用户重启后 QQ「Deleted Messages」仍报 `[Errno 22]`。时间剖析定位真相：此类文件夹的邮件是**移入**的，UID 按删除时间单调但日期不单调——30 天日期搜索出的 42 个 UID 数值区间里夹着 346 封旧邮件，`UID a:b` 区间分块被服务器整段展开（实测一把拉回 388 封 31s，大文件夹即撞 60s 超时，Windows SSL 把超时报成 Errno 22）；进一步实测 QQ 对**逗号 UID 集合同样按 min:max 展开**，无法精确
- 修复：`iter_new_mail` 按密度自适应——窗口内 UID 跨度 ≈ 数量（如收件箱）走区间快路径；稀疏窗口逐 UID 精确拉取（单 UID 服务器无法展开）。真机四组合验证：QQ 收件箱 159 封 28s / QQ 已删除 388 封 31.7s（用户刚批量删信进去的稠密场景）/ 自定义账号两文件夹均过
- UI：收件箱页账号/文件夹下拉选择持久化到 localStorage（刷新/切标签不再重置为「全部邮箱+INBOX」，选择已删除账号时自动回落）

## 6d25ec3 — fix：同步误用 search 的收尾 + health 暴露代码版本
- `python run.py` 无热重载，用户进程停在修复前代码上反复报 `'search'` 错——行为探测（POST sync 后读状态）确认为旧进程而非代码问题；引导重启解决
- `GET /api/health` 新增 `commit` 字段（启动时读 git 短哈希，打包环境为空省略）：以后「改了没生效」一条 curl 对照 `git log` 即可甄别

## e0df0af — fix：同步分块误用 MailBox.search → uids（真机首翻即 AttributeError）
- e8c0084 的 `iter_new_mail` 调用了不存在的 `MailBox.search`（imap-tools 正确方法为 `uids`）——隔离冒烟未接真实 IMAP 未暴露，真机一同步两账号全报 `'MailBox' object has no attribute 'search'` 连接异常
- 修复并真机只读验证（不落库）：QQ 账号最近 30 天 167 封、自定义账号 11 封，分块拉取链路（uids SEARCH → 逐块 FETCH → 解析）全部通过

## e8c0084 — 功能/UX：同步引擎四步优化（分块断点/批量入库/超时重试/后台化进度） + AI Key 明文回显
- **同步慢+报错根因**：`bulk=True` 整批一条 FETCH（大邮箱首翻=巨型响应，QQ 中途掐断，Windows SSL 层报 `[Errno 22] Invalid argument`）+ 每封一提交（5000 封=5000 次 fsync）+ 同步阻塞请求线程/调度 tick；且失败时 last_uid 未落库，下次原地重放同一巨型请求，反复失败
- **分块断点续拉**：`fetch_new` 重做为 `iter_new_mail` 生成器——先轻量 SEARCH UID 清单，按 ~100 封/块升序 `UID a:b` FETCH；每块「入库+断点」同一事务提交，中断/失败从断点续传，不再整批重放
- **批量入库**：每块一个事务；`_upsert_email` 用 rowcount/lastrowid 判重，去掉每封回查 SELECT 与逐封 commit
- **超时与重试**：`MailBox(timeout=60)`（原 None 可僵死）；网络类异常自动重连重试一次（登录失败不重试），断点已在、重试只补剩余
- **后台化+进度**：新增 `start_sync` 后台线程（进程内防重入），手动同步/添加账号/调度器轮询全走它——API 秒回，长同步不再卡界面与调度；账号行新增「同步中」状态（蓝点脉冲）+ 实时「同步中：已收 n 封」进度；新增邮件通知到达时全局刷新邮件列表（NotificationBell），MailBrowser/设置页在同步期间 2s 轮询账号状态、结束即刷列表
- **AI Key 明文回显**（用户反馈"刷新后 Key 又没了"）：本地单用户应用，`GET /api/ai/profiles` 回显 `api_key` 明文，界面所见即所存（清空保存=清除，"清除已存密钥"按钮与"留空不变"语义移除）；档案接口不再返回 `api_key_set`（前端类型同步）
- 验证：ruff --select F、npm run build 通过；隔离实例 curl——不可达服务器后台同步 started→两次重试日志→+4s 正确标记 connection_error（服务端视角复核）、无凭证 started:false+no_credentials、404 形态、api_key 回显与无 api_key_set 断言；**大邮箱真实账号首翻/断点续传待用户重启后验证**

## 2f941f5 — UX：AI 配置体验修补（自动拉模型 + Key 明文可见 + 告别「默认」档案）
- **模型列表自动拉取**：Base URL 填写即防抖 700ms 自动拉取模型（点选即填，无需先保存再点「获取模型列表」按钮，按钮删除）；`GET /api/ai/models` 重做为 `POST /api/ai/models`——显式 base_url/api_key 优先（未保存的新配置用输入框现值直连），缺省回退档案已存密钥；拉取中/失败均有内联提示，AI 停用态仍可用（属配置辅助不执行任务）
- **API Key 默认明文可见**：输入框默认 text（本地应用输入即可核对），右侧眼睛图标一键显隐；占位文案改「留空 = 不改动已存密钥」
- **告别「默认」档案**：全新安装不再预建任何档案（空列表引导创建，首建自动设为使用中）；旧版单配置迁移档案改以模型名命名；历史版本自动生成的「默认」档案一次性按模型名重命名（用户自行改过名的不动）；总管家切换器空选项「默认模型」→「跟随使用中」，选项「名称（模型）」在同名时去重只显示一个
- 验证：ruff --select F、npm run build（tsc 含）通过；隔离实例 curl——全新安装 profiles=[]、种子「默认」档案被重命名为 deepseek-flash（GLM 不动）、POST /models 四形态（空 URL 提示 / 不可达端点 / profile_id 回退已存 URL+密钥真实打到 DeepSeek 得 401 / AI 停用态可用）全部符合预期

## 2b73d32 — fix：空邮件可存草稿（懒持久化，撤销空稿自动清理）
- 用户反馈"空邮件为什么不能存草稿？这是用户行为"——此前把空稿当垃圾自动清理（恢复时删、草稿箱过滤、关标签保留即删），越权替用户做决定。现改为**懒持久化**根治：点「写信」只开本地空白标签（ephemeral，不落库），首次编辑/点存草稿/传附件/定时才创建记录——随手点开的空标签不再进库，而用户显式保存的空稿（哪怕全空）合法保留、进草稿箱、重启恢复
- 实现要点：标签引入稳定 tabId（draftId 换绑时 tabId 不变，表单不重挂、光标不丢）；附件/发送/定时前经 ensurePersisted 确保持久化；撤销上一版的恢复清理、草稿箱过滤、保留空稿即删三处越权逻辑；「写信」对已有空白标签仍复用不重复开
- 注：上一版已存在的空稿残留不再被自动删，关标签选「丢弃」即可清掉
- 验证：npm run build 通过

## 9480351 — 功能：语气学习退役 → 文风提示词 + AI 总开关 + 设置页侧边栏分类
- **语气学习（Tone DNA）下线**：黑盒学习"已发送邮件语气"（学到的可能不是用户想要的）改为每账号**手写「文风提示词」**——设置-邮箱账号 每行「文风」按钮展开编辑器（≤2000 字，留空保存即清除），AI 拟稿时作为明确要求注入 system 提示词，内容完全透明可控；删除 tone-dna 端点与前端按钮，`ai_logs` 历史 tone_dna 用量保留展示为「语气学习（已下线）」
- **迁移 v10**：`accounts` 增 `style_prompt` 列，已学得的语气描述原样转存为可编辑提示词（可改可清）后删除 `tone_dna` 列
- **AI 总开关**：设置-AI 配置 顶部「启用 AI 功能」开关（`PUT /api/ai/enabled`，settings KV `ai_enabled`）；关闭即**传统邮件模式**——侧栏隐藏 待审草稿/每日摘要/AI 总管家，隐藏 AI 整理/AI 拟稿/AI 助手/AI 写作/AI 重写入口，摘要生成按钮隐藏；后端 `resolve_config()` 统一在停用时拒绝所有 AI 任务（报错文案区分「已停用」与「未配置端点」），配置档案与历史数据原样保留，随时重开
- **设置页侧边栏分类**：参考网页邮箱设置，平铺长页改为左侧分类导航（通用/邮箱账号/AI 配置/AI 用量/关于，记忆所选分类）；更新检查移入「关于」；粘性保存栏随通用分类保留
- 验证：ruff --select F、npm run build（tsc 含）通过；隔离实例（临时数据目录）curl 往返——迁移 v10 后 schema 正确（tone_dna 删、style_prompt 在）、style_prompt 设置/清空（空串→NULL）往返、停用后 write 400 文案「AI 功能已停用…」、profiles 接口含 ai_enabled 且开关切换生效；摘要生成在停用态按既有降级输出仅统计版（AI 综述为空）

## 1c57697 — fix：草稿保存机制调研修复（缓存过期误删等 3 处）
- 严重：自动保存只写服务端、不回写前端草稿缓存，缓存停留在创建时刻的快照——空新建草稿写过内容后点 ×→「保留草稿」，关闭判断仍按过期快照判空 → **误删已保存的草稿**；写信按钮复用空标签的判断同样失真。修复：保存成功即回写缓存（patchDraft），关闭确认改为「先 flush 未保存内容 → 以服务端最新内容判空」双保险
- 空白草稿点「存草稿」会在库里留空行、草稿箱显示空白条目直到下次刷新才被清：草稿箱现展示层过滤空白稿并即时清理
- 自动保存失败（后端瞬时不可用）后不再静默等下一次输入：5 秒后自动重试一次（每轮失败限一次，草稿已删除时不会无限循环）
- 验证：npm run build 通过

## db30ef3 — fix/功能：空草稿治理 + 侧栏页面标签化
- 刷新后攒一排空「新邮件」标签根因治理：每次点写信都立即落库空记录、恢复时又不过滤。现在①启动恢复时空白草稿（收件人/主题/正文全空）不恢复且顺手删除②写信按钮/＋ 对已存在的空白标签直接复用激活，不再新建③关标签选「保留」时空白稿按丢弃处理
- 侧栏页面标签化（对齐浏览器式邮箱）：待审草稿/草稿箱/已归档/每日摘要/AI 总管家/设置 打开后以标签留在顶部标签条，重复点击回到已有标签不重复生成，标签可关闭，localStorage 记忆刷新不丢；直接输 URL 进入也会补标签
- 验证：npm run build 通过

## 63d8db6 — fix：写信台三处用户反馈修补
- 抄送/密送展开后可收起：行尾新增「收起」（内容保留，仅折叠界面）
- 草稿不再"存了找不到"：侧栏新增「草稿箱」页（/mydrafts，含定时中的草稿），整行点击回到写信台继续编辑、行尾可删除；写信台标签关闭/发送后列表自动刷新
- 签名/插入模板下拉面板贴右缘被视口裁切：面板改右对齐（align=right）
- 注：本条目所在提交同时带入「AI 用量面板」会话的 CHANGELOG 待提交条目（代提交，其 SettingsPage 代码由该会话自行提交）

## 9480351 — UI：AI 用量面板去英文混杂（并入设置页重写提交）
- 设置页 AI 用量：任务类型补全中文映射（digest→每日摘要、tone_dna→语气学习，此前缺映射直接裸显英文键）；分项「tk」缩写 →「Tokens」，大数改中文万单位（如 154,596 tk → 15.5万 Tokens），总计卡同步去 k 改万；任务名全中文，计量单位按行业惯例保留 Tokens
- 验证：npm run build 通过（tsc 类型检查含）

## cabdda3 — 写信台二期：同层标签互切 + 附件持久化 + 定时发送 + 模板/签名 + AI 写作对话框
- 标签排布对齐网页邮箱：主区顶部常驻标签条（收件箱固定 + 各写信标签 + ＋新写），一键互切；写信不再走路由，收件箱等页面 keep-alive（隐藏不卸载），切回即恢复列表/阅读状态；侧栏导航点击自动露出底层页
- 附件持久化：选择即上传落盘（data_dir/drafts/<id>/，迁移 v9 新表 user_draft_attachments），按个删除、随草稿恢复，发送后自动清理；回复"能添加几个"：数量不设限，单个为本地文件
- 定时发送：发送旁「定时」→ 时间选择 → 草稿转 scheduled 状态，调度器每分钟 tick 到期即发（复用 send_draft_now），成功/失败均写通知中心，失败自动退回编辑态；标签页橙色横幅可随时取消定时；重启后 scheduled 草稿仍恢复为标签可管理
- 模板与签名：工具栏「插入模板」「签名」下拉（插入光标处/末尾，Markdown 自动转富文本）；管理弹窗支持按账号存签名、模板增删改（settings KV 存 Markdown 文本，新端点 /api/compose-extras）
- AI 写作对话框（核心）：点「AI 写作」弹窗——指令描述直接生成整篇正文（新 compose 操作，支持把现有正文作背景），或一键润色/更正式/更简短/译中/译英；结果预览后「替换正文/插入末尾」，输出经后端 Markdown→HTML 转换（nh3 消毒），插入即得可用富文本，不再是纯文本覆盖
- 验证：npm build、ruff --select F 通过；隔离实例往返：附件上传/删除/磁盘落位/删稿清理、定时（过去/非法/未来时间校验、scheduled 列表、取消）、Markdown 转换、模板签名 KV、调度器到期派发失败路径（退回 editing + 通知）；AI 真实生成与 SMTP 定时实发待用户验证

## ddf3d0d — 发版自动化：一条命令 + 手册
- 新增 `scripts/release.sh X.Y.Z`：预检（版本文件干净/不落后 origin/tag 未占用/gh 登录）→ 同步 pyproject+config.py 两处版本号 → 提交打 tag 推送 → `gh run watch` 盯 release CI 全绿 → 等 Release 资产取 exe SHA256 → fork 建分支提 winget 版本更新 PR；支持 `--dry-run`（演练后还原）与 `--skip-winget`
- 新增 `docs/RELEASE.md` 发版手册：前置条件、流程、AI 收尾清单、故障处理表；沉淀 winget 全部实战踩坑（单层首字母折叠、locale.en-US 文件名、本地 validate 验不出路径规则、目录含子目录报错、fork 默认分支 master）
- CLAUDE.md 常用命令、README、ARCHITECTURE 分发表同步入口

## 6bfaaca — 功能：写信工作台（多标签 + 自动草稿 + 富文本）
- 写信从居中弹框改为全页工作台（/compose）：顶部多标签可并行写多封，标签条 + 新写按钮；点「写信/回复/转发」不再弹框而是开新标签
- 草稿持久化：新表 user_drafts（迁移 v8，与 AI 待审 drafts 独立）+ api/user_drafts.py（CRUD/发送）；编辑防抖 1s 自动保存，标签黄点=未保存，Ctrl+S 手动存；关闭未保存标签弹「保留草稿/丢弃」确认；保留的草稿下次启动自动恢复标签；有未保存内容时拦截页面刷新
- 编辑器升级：TipTap v3 富文本替换 Markdown textarea，工具栏对齐网页邮箱——撤销重做/清格式/字体/字号/加粗斜体下划线删除线/文字颜色/背景高亮/有序无序列表+缩进/三向对齐/引用/代码块/分隔线/链接/本地图片内嵌(≤1.5MB)/表格；AI 智能写作五操作保留，有选区替换选区、无选区整篇替换
- 发信链路：正文经 sanitize_outgoing_html 白名单消毒（放行 data: 内嵌图）→ 派生纯文本 alternative → 套基础样式外层；回复/转发引用升级为 blockquote 结构并带 In-Reply-To 正确串线；抄送/密送默认折叠（点「抄送/密送」展开）
- 附件随发送上传（与旧版一致，暂不持久化，刷新后需重选）；旧 /emails/send 端点保留兼容
- 验证：npm build 通过、ruff --select F 通过、隔离实例（临时数据目录）curl 全往返（创建/修改/读取/删除/校验 400/外键与消毒边界），真实账号 SMTP 发送待用户重启后验证

## 04808d1 — 功能：自建文件夹 + 导航/页眉再紧凑
- 文件夹下拉旁新增 + 按钮：输入名称回车即在服务器上创建（重复/INBOX 拦截，QQ 真机验证），创建后自动切换并同步
- 左导航栏与页眉加局部 zoom 0.75（与全局 0.85 叠加，视觉约为原 0.64），侧栏拖拽坐标按双重 zoom 换算

## 0c4350a — 功能：通知管理
- 通知单条删除（行尾悬停 ✕，新端点 DELETE /notifications/{id}）+ 页头「清除已读」（仅删已读，未读保留，POST /notifications/clear-read）
- 与既有能力合并后通知中心具备：单条点击跳转+单条已读、全部已读、单条删除、清除已读
- 真实数据验证：单删 24→23、清除已读 23 条、未读保留

## 9b98a9e — fix/功能：时区排序 + 未读辨识 + 通知可点击
- 排序根因：date 列为混合时区 ISO 串，字典序比较错序（+08:00 的 12:10 排在 +08:00 的 10:03 之后却早于 -07:00 的 21:15）——迁移 v7 新增 date_sort（UTC 归一）+ 索引，启动时 Python 回填历史数据，列表按 date_sort 排序（真实数据验证严格降序）
- 未读行增加左侧 indigo 竖条标识（选中态同列），与已读行区分度提升
- 通知中心：单条可点击——按类型跳转（AI 草稿→原邮件 / 摘要→摘要页 / 账号异常→设置），点击即单条已读（新端点 /notifications/{id}/read）

## 42a0a4c — fix：邮件外链新标签打开 + 正文高度即时自适应
- 外链「拒绝连接」根因：链接在沙箱 iframe 内部导航，目标站（如 console.volcengine.com 带 X-Frame-Options/CSP frame-ancestors）拒绝被网页内嵌，浏览器遂显示「拒绝连接」。修复：后端消毒时为 http(s) 链接强制 target="_blank"（rel=noopener 原有），前端 sandbox 增加 allow-popups + allow-popups-to-escape-sandbox，点击在新标签正常打开，同时支持 Ctrl/中键
- 正文显示不全根因：iframe 高度只靠加载后 0/500/1200/2500/4000ms 五次定时报复测，图片等资源 4s 后才就位则高度偏小（出现内部滚动条、内容截断）。修复：onLoad 后对 iframe body 挂 ResizeObserver，尺寸变化即时复测，定时复测降为兜底；卸载时断开

## 31a2f6d — docs：安装与更新指南 INSTALL.md
- 新增 docs/INSTALL.md：五种安装方式对比（单文件/winget/Homebrew/uvx·pip/源码）、各平台首次运行注意（SmartScreen/Gatekeeper/chmod）、首次使用五分钟引导、更新方式与升级安全性、数据目录/备份/卸载
- README 顶部加指南入口；winget manifest PR 已提交（microsoft/winget-pkgs#432990，fork 默认分支为 master 的乌龙修正）

## 6666dcc — 功能：邮件批量操作
- 列表每行复选框 + 表头「全选本页」；勾选浮现批量操作栏：已读/未读/星标/归档(恢复)/移动到/删除/取消
- 后端新端点 POST /api/emails/batch-action：归档类纯本地；IMAP 类按账号分组共用一条连接，同文件夹合并打标（不逐封请求）
- 真实账号验证：批量已读/星标（IMAP 生效）、归档 129→132→129、全部还原

## 80b16ee — 更新机制：应用内检查 + 包管理器渠道
- 应用内更新检查 `core/update_check.py` + `GET /api/update-check`：每 24h 匿名对比 GitHub Releases（UA=Nmail/版本，不带本机数据，可关闭），发现新版本写入通知中心（按版本去重，升级后自动清理旧提醒）；设置页「自动检查更新」开关 + 手动「检查更新」+ 当前版本展示
- Homebrew tap：新建 `nathanpenny520/homebrew-nmail`（macOS arm64，SHA256 对齐 Release 资产），`brew tap nathanpenny520/nmail && brew install nmail`；CLI 增加 `--version`
- winget：fork winget-pkgs 提交 `nathanpenny520.Nmail` 0.1.0 portable manifest（x64 + SHA256），PR 流程见 docs/SESSIONS.md 对应条目
- CI：release.yml 新增 homebrew-tap job（可选 secret `HOMEBREW_TAP_TOKEN`，未配置自动跳过），打 tag 自动更新 formula 版本与哈希

## d2e8dfa — 功能：图片放行体系 + AI 拟稿要求提示词
- 设置-通用新增「显示邮件外部图片」（默认拦截，选择即保存）；发件人粒度新增 image_trust 信任白名单（迁移 v6 重建 sender_lists 放宽 CHECK）
- 读信页拦截提示条新增「始终显示该发件人图片」；放行优先级：URL 参数 > 全局设置 > 信任白名单
- 读信页「AI 拟稿」点击展开要求输入框（可留空直接生成），生成后跳转待审
- 修复：辅助函数误插路由装饰器与 get_email 之间导致详情 422（真实数据全链路验证：10 图邮件 拦10→开0→关10→信任0→清理10）

## f0bb189 — fix：zoom 下应用底部留白
- 100vh 在 zoom 子树里是未缩放值：#root 高度改 calc(100vh / var(--app-zoom))，渲染高度恰好铺满视口

## 851e30f — UI：字号档位改为「变量 + 全局 zoom」
- 根因：浏览器「最小字号」钳制（中文 Chromium 常见默认 12px）导致纯 font-size 调不动
- 档位 = 字号变量（回归 10.5~14px 安全区）+ #root zoom（紧凑 0.85 / 标准 1 / 大 1.12），渲染结果绕过钳制，间距同步缩放
- 列表/导航拖拽坐标按 zoom 换算，拖拽手感不偏移

## 3867582 — UI/功能：文件夹按需同步 + 字号再降 + 专属 logo
- 文件夹下拉此前只切视图不同步（库里仅有 INBOX）——现在切换即按需拉取该文件夹，计数行显示同步中
- 三档字号再降约 1px（紧凑 8.5/10/11/12.5）；应用内左上角 logo 换为用户专属图标（icon-192，与标签页同源）

## a84deae — UI：工具条上移页眉
- 搜索（全局宽框）+ 收信 + AI 整理 + 写信 移入页眉（对齐阿里邮箱布局）；列表列只留筛选与计数
- 页眉在全屏阅读模式下隐藏；星标筛选按钮防挤压（nowrap+shrink-0），不再被挤成大方块

## 25912b4 — fix：发布流水线两项修复（首轮 CI 失败复盘）
- 发行包名 `nmail` → `nmail-app`：PyPI 上 "nmail" 已被第三方占用（Roman Solyanik 的 SMTP 发信工具），上传 403 "isn't allowed to upload to project"；产品名/命令名不变，uvx 改用 `uvx --from nmail-app nmail`
- release.yml 顶层加 `permissions: contents: write`：修复三平台 "附加到 GitHub Release" 403（默认 GITHUB_TOKEN 只读）
- v0.1.0 tag 将重指向修复提交（首轮发布均未成功，无版本号被占用）

## 98b34f8 — fix：设置页无法下滑
- 根因：侧栏重构时主容器误设 overflow-hidden，文档流页面（设置/摘要/总管家）超出视口被直接裁掉
- 主容器改 overflow-y-auto（邮件页自身 h-full 自管滚动，不受影响）
- 设置页全部字号挂入 t-* 变量体系，随界面字号档位缩放

## d6dec7c — UI 密度：遮蔽修复 + 紧凑下调 + 导航栏拖拽
- **根因修复**：源码模式下 backend/app/static（打包旧快照）优先于 frontend/dist 被服务——用户一直看旧界面；解析顺序改为 源码→frontend/dist 优先、wheel/frozen→app/static
- 紧凑档（默认）整体下调至 9/10.5/11.5/13.5px，标准/大档顺次上移；工具栏/列表/徽章/日期等写死字号全部挂 t-* 变量
- 列表行高压至 py-1；工具栏按钮 nowrap+min-w-0 防挤爆；列表 overflow-x-hidden
- 左侧导航栏可拖拽调宽（96–240px，双击复位 148，记忆本地）；≤132px 自动切纯图标模式（tooltip 补位）

## f8e00d4 — 图标：apple-touch-icon 按 Apple 规范重排
- 原实现把母版圆角方块+外阴影整幅贴进 180 画布、四角单色填充：iOS 再裁一次圆角会出现「图标套图标」双层圆角与角部接缝，违背 HIG「图内不要自带圆角与阴影，系统自行裁切」
- gen_icons.py 改为：母版放大 6% 居中裁切（烘焙的边缘光晕随之移出画布），四角用圆弧内侧取样色铺双线性渐变补透明月牙，内部 100% 保留原图；信封随放大至 ~74% 更饱满
- 产物同步 frontend/public 与 backend/app/static（后者为打包快照，随 sync 更新）

## 65d208d — fix：设置页保存体验
- 界面字号/正文字号改为**选择即保存**（单字段 PUT，即时生效，互不干扰）
- 轮询间隔/摘要时间等通用表单改**底部粘性保存栏**：有未保存更改才浮出（保存/放弃）
- 新增后端旧版本守护：保存响应缺新字段时明确提示「请重启 python run.py」（根因：旧进程 Pydantic 静默忽略新字段，返回成功假象）

## 2b24b90 — 协作：多会话协作体系
- 新增多会话看板 `docs/SESSIONS.md`：开工登记（ID/目标/范围）→ 进行中更新 → 收工交接（产出/遗留），24h 无更新可由任意会话判入「已中断」；含代登并行会话未提交 WIP 的先例
- CLAUDE.md 工作流规范新增 8–10：开工三件事（读看板/登记/看 log）、即时重读禁凭记忆覆盖（以磁盘现状+git log 为准）、按路径暂存与哈希回填纪律
- 背景：当日多会话并行两次出现"文件被另一会话先改"（settings.py 字号、nmail.spec 图标），靠运气未撞车，机制化透明度

## 65bb14d — 图标：应用全套图标落地
- 母版图（personal-data/Nmail邮箱应用图标.png，2048 黑底不透明）经新脚本 scripts/gen_icons.py 裁剪到圆角方块、黑底软阈值转透明，一次生成全套资产
- 前端：frontend/public 新增 favicon.ico（16/32/48）、icon-192.png、icon-512.png、apple-touch-icon.png（180 满幅不透明）；index.html 内联 SVG 占位 favicon 换为真实文件引用 + theme-color
- 打包：新增 assets/nmail.ico（16–256 多尺寸）与 nmail.icns；nmail.spec 按 sys.platform 挂 icon（Windows→ico、macOS→icns、Linux 忽略），CI 三平台二进制自动带新图标
- Windows 首次替换 exe 图标后资源管理器可能命中旧缓存（重命名或 ie4uinit -show 刷新即恢复）

## 7f49125 — P4：AI 总管家会话持久化与管理
- 总管家对话落库（chat_sessions/chat_messages，迁移 v5）：历史列表（置顶优先>更新时间倒序，含消息数与相对时间）、置顶、重命名、删除（级联清消息，二次确认）、点击恢复继续对话
- 会话懒创建：发首条消息才真正建会话，不留空会话；标题自动取首条消息前 30 字，手动重命名后不再覆盖
- 落库全量、传模型有界（上下文仍只取最近 6 条，token 不随历史膨胀）；流式中断保留已生成部分再落库
- 保留策略已拍板：仅手动删除选定会话，无自动清理

## 7f49125 — P4：AI 配置档案（多模型 / 多 API Key）
- 新增「AI 配置档案」：多套 base_url + 模型名 + API Key，一个全局激活档案；对话类请求可传 profile_id 临时切换
- 旧单配置自动迁移为「默认」档案（密钥搬运至 secrets.json 的 `ai_profile_key:{id}`，老用户无感、无重复输入）
- 新端点：`/api/ai/profiles` CRUD + `/{id}/activate`、`/api/ai/models`（代理 OpenAI 兼容 /models 供下拉选择）
- 全部 AI 任务（分类/草稿/问答/写作/摘要综述/Tone DNA）按档案解析配置；ai_logs 照常记录实际模型
- 设置页改档案卡片管理：新增/编辑/删除/设为使用中/按档案测试连接/「获取模型列表」点选模型名；总管家与邮件 AI 助手加模型切换器（多于一档时显示）
- `/api/settings` 不再承载 AI 配置；`/api/ai/test` 字段省略时回退激活档案

## 7f49125 — P4：服务商自动探测 + 打包分发
- 未收录域名自动探测：Mozilla autoconfig 标准接口（两处托管位）→ imap./mail./smtp. 常见主机名 993/465 并发试连（只收加密端口，新端点 `POST /api/accounts/probe`）
- 添加账号弹窗：探测到即自动预填服务器并展开高级区确认；未探到仍走手动兜底；预设库增补移动 139 邮箱
- 打包分发：pyproject.toml（包名 nmail，console script `nmail`）+ 前端产物入包（`backend/app/static`）+ `app/cli.py` 统一启动入口（run.py / nmail 命令 / 冻结包共用）
- 前端静态目录按运行形态解析：wheel 安装（app/static）→ PyInstaller 冻结资源 → 源码 frontend/dist
- 新增 scripts/sync_frontend.sh、nmail.spec（三平台单文件）、.github/workflows/release.yml（打 tag → wheel 发 PyPI + 三平台二进制挂 Release）

## 4e44cac — UI v2：分屏 + 拖拽 + 字号系统 + 草稿分屏
- 收件箱恢复分屏（列表|阅读区），分隔条可拖拽（240–640px，双击复位，记忆本地）
- 阅读区可切换全屏（记忆选择）；正文列宽自适应
- 界面字号三档 CSS 变量系统（`<html data-font>`）+ 邮件正文字号独立缩放（iframe zoom）
- 待审草稿改收件箱式分屏：列表+详情、高度自适应编辑、丢弃/恢复/彻底删除（新端点）、带指令 AI 重写
- 设置页新增「界面字号」「邮件正文字号」（后端 settings 校验）

## 3123e8b — AI 问答体验：SSE 流式 + Markdown
- 总管家/邮件助手改 SSE 流式（首字秒级，中途错误以 error 事件可见）
- react-markdown + remark-gfm 渲染 AI 回复与摘要综述

## e9b598a — AI 入口升级
- 侧栏新增「AI 总管家」全局问答（范围：全部/指定账号 × 7/30/90 天，批量上下文 150 封）
- 读信页「AI 拟稿」：手动触发草稿生成并跳转待审
- 字号整体再降一档

## 914822f — UI 重构：全文阅读 + Gmail 式密度
- 点开邮件占满主区域（Esc 返回）；列表改单行 Gmail 式密度；正文高度复测（图片异步加载/窗口 resize）

## 124b035 — P3：每日摘要与权限
- 定时 AI 摘要（统计零成本 + AI 综述一次调用）+ ECharts 可视化 + 导出 Markdown + 摘要一键直达邮件
- 浏览器桌面通知（Notification API，授权入口在侧栏铃铛旁）
- Tone DNA：从服务器已发送学习写作语气，注入草稿提示词；设置页「学习我的语气」

## 24532fa — P2：AI 层
- AI 批量分类（few-shot+JSON，20 封/请求，失败跳批）；营销自动本地归档
- 发件人白/黑名单（跳过 AI，右键式一键添加）
- needs_reply 自动生成回复草稿 + 待审流 + 通知
- AI 对话面板（单邮件）、写信 AI 辅助（润色/正式/简短/翻译）、AI 用量统计（ai_logs）
- 账号 AI 权限：readonly / draft_review（默认）；未配置 AI 诚实降级

## a61ca0c — P1：邮箱核心 MVP
- 19 服务商预设自动匹配 + 手动 IMAP/SMTP；UID 增量同步（首同步 30 天、UIDVALIDITY 自愈、网易 ID 命令）
- 收件箱/归档/搜索（FTS5 trigram + LIKE 回退）/读信（nh3 消毒+远程图拦截）/发送（multipart/alternative，Markdown→HTML）
- 附件收发、本地归档视图（不动服务器）、通知中心、授权码失效提醒、后台轮询调度

## f7bf592 — P0：项目骨架
- run.py 一键启动、FastAPI+React 壳、SQLite 迁移框架、设置页（AI 端点配置+测试）、MIT

## 3a063bd / 26144ac — 真实使用首轮修复
- imap-tools 日期条件 `date_gte`、uid 强转 int
- SMTP 配置未随账号传入、FormData 误设 JSON 头、iframe 高度随图片复测

（更早：docs/PRODUCT_PLAN.md v0.1→v0.2 方案与拍板记录）
