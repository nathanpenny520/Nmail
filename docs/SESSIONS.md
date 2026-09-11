# 多会话看板（docs/SESSIONS.md）

> 多个 Claude 会话并行共享同一工作树是常态。本文件是唯一的会话登记处：**开工先读这里，收工必更这里**。
> 配套铁律见 [CLAUDE.md](../CLAUDE.md) 工作流规范 8–10（开工三件事 / 即时重读 / 提交纪律）。

## 使用规则（一分钟版）

1. **开工**：读完本文件。目标文件/模块与任一「进行中」会话的范围重叠 → 换范围或等它完成；否则到「进行中」登记（ID、目标、预计触碰文件、开始时间）。
2. **进行中**：每完成一个大阶段顺手更新一次状态行；会话被压缩/重启后，先来这里恢复上下文再动手。
3. **收工 / 中断**：条目移到「已完成 / 已中断」，写清产出（提交哈希）、遗留事项、给下一个会话的提示。发现超过 24 小时无更新的「进行中」条目，任何会话可将其移入「已中断」并注明原因。
4. **撞车**：发现文件被改得与预期不符 → 以磁盘现状为准，对照 `git log` 弄清发生了什么，调整自己的方案而不是覆盖别人。

## 会话 ID 约定

`S-MMDD-HHmm-<主题>`，例：`S-0911-2230-打包`。以开工时刻为准，请勿复用他人 ID。

## 进行中

<!-- 有新会话开工时按下方模板登记 -->

### S-0911-1416-全面提升计划
- 目标: 全量代码审核（架构/扩展性/质量/鲁棒性）复查后沉淀为可执行提升计划——以降耦合、降开发难度为主线，保留鲁棒性/安全/测试洞察
- 范围: docs/IMPROVEMENT_PLAN.md（新增）、docs/SESSIONS.md；**不改任何代码**
- 产出: docs/IMPROVEMENT_PLAN.md 已落盘（含 A/R/S/Q/T 编号项与 M1–M4 里程碑，供后续会话按编号认领）；提交后回填哈希
- 遗留: 计划本身待用户取舍排期；M1 各项为小步快修可直接认领
- 时间: 2026-09-11 14:20 完成

### S-0911-1530-空草稿懒持久化
- 目标: 尊重"空邮件也能存草稿"的用户行为——点写信不再立即落库（懒持久化，首编辑/显式保存才建行），撤销全部空稿自动清理；标签引入稳定 tabId 支持创建后换绑真实 id
- 范围: frontend components/compose/ComposeContext.tsx、ComposeForm.tsx、ComposeWorkbench.tsx、components/Layout.tsx、pages/UserDraftsPage.tsx；docs（此前已代提交 S-0911-2500 成果 9480351）
- 产出: 提交 2b73d32（见 CHANGELOG「空邮件可存草稿（懒持久化）」条目）
- 遗留: 上一版遗留的库内空稿不会被自动删（用户关标签选丢弃手动清）；刷新时未保存的 ephemeral 标签内容会丢（有 beforeunload 拦截提示）
- 时间: 2026-09-11 15:45 完成
- 目标: 调研草稿箱/写信台保存链路，修复发现的 bug（缓存过期误删草稿等）
- 范围: frontend components/compose/ComposeContext.tsx、ComposeForm.tsx、pages/UserDraftsPage.tsx；docs
- 产出: 提交 1c57697（见 CHANGELOG「草稿保存机制调研修复」条目）；机制全貌：点写信即建行 → 编辑 1s 防抖 PATCH + 回写缓存 → 发送/定时/关闭决策前 flush → 空稿在恢复/草稿箱/关闭三处即见即清
- 遗留: 保留草稿确认时若最后 <1s 的输入尚未防抖落盘，flush 机制已覆盖（registerFlush）；仅极端并发双开浏览器标签场景可能互删空稿（单用户可忽略）
- 时间: 2026-09-11 14:50 完成

### S-0911-1420-工作台标签化 ✅
- 目标: 空草稿治理（恢复时清理+写信按钮复用空标签+保留空稿即删）+ 侧栏页面标签化（点一次开 tab、再点去已有 tab、可关闭、localStorage 记忆）
- 范围: frontend components/Layout.tsx（WorkspaceTabs 重写）、components/compose/ComposeContext.tsx；docs
- 产出: 提交 db30ef3（见 CHANGELOG「空草稿治理 + 侧栏页面标签化」条目）
- 遗留: 无；页面标签切换仍是路由卸载/重挂（仅收件箱+写信台 keep-alive），页面滚动位置不保留——AI 会话/草稿列表等状态在库里，无实质损失
- 时间: 2026-09-11 14:30 完成

### S-0911-1350-写信台修补 ✅
- 目标: 三个用户反馈修复——抄送/密送可收起、存草稿后草稿可寻（新增草稿箱页）、右侧下拉面板贴边裁切
- 范围: frontend components/compose/ui.tsx、InsertDialogs.tsx、ComposeContext.tsx、ComposeForm.tsx、Layout.tsx、pages/UserDraftsPage.tsx（新增）、App.tsx；docs
- 产出: 提交 63d8db6（见 CHANGELOG「fix：写信台三处用户反馈修补」条目）；Dropdown 支持 align=right；Provider 增 openDraft + user-drafts 列表失效
- 遗留: 无；注意本会话 docs 提交代提交了「AI 用量面板全中文」会话的 CHANGELOG 条目（其 SettingsPage.tsx 改动仍留在工作树，由该会话提交）
- 时间: 2026-09-11 14:00 完成

### S-0911-1315-写信台二期 ✅
- 目标: 收件箱/写信同层标签切换（keep-alive）+ 附件持久化 + 定时发送 + 模板/签名 + AI 写作对话框（生成可用富文本）
- 范围: backend 迁移 v9、api/user_drafts.py、api/compose_extras.py（新增）、api/ai.py、ai/tasks.py、scheduler.py、core/mail_html.py；frontend Layout、compose/*（AiWriteDialog/InsertDialogs/ui/ComposeWorkbench 新增）、App.tsx、types/client；docs
- 产出: 提交 cabdda3——同层标签条（收件箱固定+写信标签，keep-alive 隐藏不卸载）、附件选择即落盘（迁移 v9 + drafts/<id>/ 目录）、定时发送（scheduled 状态 + 调度器到期派发 + 失败退回编辑态写通知 + 横幅取消）、模板/签名（/api/compose-extras KV + Markdown 转富文本插入）、AI 写作对话框（compose 指令生成 + want_html 转换 + 预览替换/插入）
- 遗留: ① 用户重启进程生效（迁移 v9 自动补跑）② AI 真实生成质量与定时实发需真实账号验证 ③ 定时草稿重启后恢复为标签可取消，但通知中心条目暂不可点跳转 ④ 附件数量不设限（SMTP 服务商大小限制由发送时报错兜底）
- 时间: 2026-09-11 13:35 完成

## 已完成

### S-0911-1546-提升计划修订与M1快修
- 目标: 逐条核实 IMPROVEMENT_PLAN 后修订并执行修订版 M1 全清单
- 范围: docs；backend api/emails.py、api/ai.py、ai/digest.py、db/database.py、main.py、core/mailbox.py（新增）、core/sync.py；frontend api/client.ts、vite.config.ts
- 产出: 计划修订 6fbf821（R1/R10/A9 同步侧/T6 确认已被同步引擎系列提交解决而移出待办、M3 缩窄为 AI 整理异步化、修正路径与横幅规模）；M1 八项全部落地——R2 move 拿不到新 UID 删行交增量重建 4c22b2f、R4 删零调用 /api/emails/send（附件名路径注入）393293e、R9 get_setting 容错 208443c、R6 时间窗/排序切 date_sort 56b9883、R8 总管家先验配置后落库 d34a54a、S1 Origin/Host 校验中间件+vite changeOrigin 9ab675a、3.1 core/mailbox.py 唯一 MailConfig 构造点并切 sync fadc747、3.2 tx()+autocommit 同一提交切换 0b549c9；每项均过 ruff/构建/隔离实例冒烟（S1 为 8 项 curl 矩阵，tx() 为提交/回滚断言）
- 遗留: M2 待认领（发送通路归一 + 删 _imap_for + AI 收口 + 分层规则）；tx() 存量多语句点随触碰机械替换；真实账号回归建议用户重启进程后顺手验证 R2（批量移动邮件）与 S1（正常使用不受影响）
- 时间: 2026-09-11 16:06 完成

### S-0911-1230-发版自动化
- 目标: 发版压成一条命令并沉淀手册，供未来 AI 会话直接使用
- 范围: scripts/release.sh、docs/RELEASE.md、CLAUDE.md（常用命令）、README、ARCHITECTURE 分发表、CHANGELOG
- 产出: 提交 ddf3d0d——release.sh（预检→双文件版本号→tag→盯 CI 全绿→取 exe SHA256→自动提 winget 版本 PR；--dry-run 已实测通过）；RELEASE.md 沉淀 winget 全部实战踩坑；**下次发版 = bash scripts/release.sh X.Y.Z，收尾清单见手册**
- 遗留: 脚本未跑过完整真流程（dry-run 已验），首次真实使用若有出入按 RELEASE.md 故障表修
- 时间: 2026-09-11 完成

### S-0911-1249-写信工作台 ✅
- 目标: 写信从弹框改为全页多标签工作台 + user_drafts 自动存草稿 + TipTap 富文本编辑器（P1+P2 合并一次提交）
- 范围: backend/app/db/database.py（迁移v8）、backend/app/api/user_drafts.py（新增）、backend/app/core/mail_html.py；frontend/src/pages/ComposePage.tsx（新增）、components/compose/*（新增）、App.tsx、MailBrowser.tsx、api/client.ts、types.ts、index.css；docs
- 产出: 提交 6bfaaca——写信工作台（/compose 多标签、1s 防抖自动保存、关闭确认、刷新恢复）、TipTap v3 富文本工具栏（字体字号/BISU/颜色高亮/列表对齐/引用代码表格链接图片）、发信消毒+纯文本派生+In-Reply-To 串线；npm build + ruff --select F 通过，隔离实例 curl 全往返通过
- 遗留: ① 用户后端进程需重启生效（run.py，迁移 v8 首次启动自动补跑）② 真实账号 SMTP 发送一封验证（含回复串线）③ 附件不持久化（刷新需重选，P3 候选）④ 插入模板/签名/分别发送/定时发送未做（P3 候选）
- 时间: 2026-09-11 13:10 完成

### S-0911-1224-外链与正文高度 ✅
- 目标: 修复邮件内 http(s) 外链在沙箱 iframe 内导航被目标站拒绝嵌入（「拒绝连接」）+ 正文高度测量滞后导致显示不全
- 范围: backend/app/core/mail_html.py、frontend/src/components/HtmlMail.tsx、docs
- 产出: 提交 42a0a4c——消毒时 http(s) 链接强制 target="_blank"（rel=noopener 原有）+ 前端 sandbox 加 allow-popups(-to-escape-sandbox)；HtmlMail 高度改 ResizeObserver 即时复测（定时复测降兜底）。ruff + npm build 通过；恶意输入无（消毒未放宽）
- 遗留: 后端进程需重启生效（run.py）；真实账号验证外链点击与长图邮件高度。注：CHANGELOG 条目因并行会话同时提交被 8a7c179 一并带入历史（非本会话提交）
- 时间: 2026-09-11 中午 完成

### S-0911-1040-更新机制
- 目标: 应用内更新检查 + 包管理器分发渠道（winget / Homebrew）
- 范围: backend/app/core/update_check.py、api/system.py、api/settings.py（开关）、api/cli.py（--version）、frontend types/client/SettingsPage、release.yml、README/docs、外部仓库 homebrew-nmail 与 winget-pkgs
- 产出: 24h 匿名更新检查（UA=Nmail/版本，不带本机数据，设置可关）+ 通知中心提醒（按版本去重、升级后自动清理）；tap 仓库 nathanpenny520/homebrew-nmail（macOS arm64 0.1.0，brew tap nathanpenny520/nmail && brew install nmail）；CI 新增 homebrew-tap 自动同步 job（可选 secret HOMEBREW_TAP_TOKEN，未配置自动跳过）；winget manifest PR 已提交：microsoft/winget-pkgs#432990（fork 默认分支为 master，首轮脚本等 main 超时的乌龙已修正）
- 遗留: winget PR #432990 审核中，需以 nathanpenny520 身份签 Microsoft CLA；HOMEBREW_TAP_TOKEN 未配置（配好即生效）；真实账号验证 uvx/exe
- 时间: 2026-09-11 完成

### S-0911-1028-apple-touch-icon ✅
- 目标: apple-touch-icon 按 Apple 规范重排（去掉自带圆角/阴影导致的「图标套图标」问题）
- 范围: scripts/gen_icons.py、frontend/public/apple-touch-icon.png、docs/CHANGELOG.md、backend/app/static（仅同步产物）
- 产出: 提交 f8e00d4（gen_icons.py apple_touch() 改为放大 6% 裁切+四角弧内取样渐变补底，由后续会话代提交）；npm build 通过；dist 与 backend/app/static 均已同步（哈希核对一致）
- 遗留: 无（favicon/exe 图标无需跟进，浏览器不套蒙版不受此问题影响）
- 时间: 2026-09-11 上午 完成

### S-0911-2300-UI密度与侧栏拖拽 ✅
- 产出：d6dec7c（遮蔽修复见 CHANGELOG d6dec7c 条目，属高影响 bug）
- 遗留：EmailReader 拦截横幅仍为固定 text-xs（微小，可并入下轮 UI 清理）
- 提示：打包后务必跑 scripts/sync_frontend.sh 或删 backend/app/static，否则旧快照会遮蔽新构建（现已由解析顺序根治）

### S-0911-2330-设置保存UX
- 目标: 设置页保存体验修复（后端版本守护提示、通用表单粘性保存栏、字号即选即存）
- 范围: frontend/src/pages/SettingsPage.tsx
- 产出: 提交 65d208d + 20c4d77（由协作体系会话代登、后经 git log 确认收工——看板首个闭环案例）
- 时间: 2026-09-11 深夜 完成

### S-0911-2320-发布首发
- 目标: gh CLI 授权、PYPI_API_TOKEN secret、v0.1.0 触发发布流水线并修复失败
- 范围: .github/workflows/release.yml、pyproject.toml（发行名）、README、docs
- 产出: PyPI nmail-app 0.1.0 + GitHub Release v0.1.0 三平台二进制；修复链 25912b4/e7cf7b8（发行名被占→nmail-app、Release 写权限）
- 遗留: PyPI token 曾暴露于对话，待用户轮换；真实账号验证 uvx/exe 安装路径
- 时间: 2026-09-11 完成

### S-0911-2340-协作体系
- 目标: 多会话并行透明度机制化（CLAUDE.md 规范 8–10 + 本看板）
- 范围: CLAUDE.md, docs/SESSIONS.md, docs/CHANGELOG.md
- 产出: 本文件与 CLAUDE.md 新规；起因是当日两次"文件被并行会话先改"（settings.py 字号、nmail.spec 图标）靠运气未撞车
- 时间: 2026-09-11 深夜

### S-0911-2200-P4主线
- 目标: 会话持久化 + AI 配置档案 + 服务商探测 + 打包分发
- 范围: backend/app/**, frontend/src/**, pyproject.toml, nmail.spec, .github/workflows, docs/**
- 产出: 提交 7f49125（主工作）、095be6a（CHANGELOG 回填）；条目见 CHANGELOG
- 遗留: AI 档案切换待真实账号验证（tag/发布已由 S-0911-2320-发布首发 完成）
- 时间: 2026-09-11 深夜 完成

### S-0911-2100-图标
- 目标: 应用全套图标（favicon/PWA/打包图标）
- 范围: assets/, scripts/gen_icons.py, frontend/public, frontend/index.html, nmail.spec
- 产出: 提交 65bb14d；Windows 图标缓存刷新提示见 CHANGELOG
- 时间: 2026-09-11 完成

### S-0911-2400-AI用量中文化
- 目标: 设置页 AI 用量面板中英文混杂修复（任务类型补映射、tokens/tk 措辞中文化）
- 范围: frontend/src/pages/SettingsPage.tsx, docs/CHANGELOG.md
- 产出: 待提交（TASK_LABELS 补 digest/tone_dna，tk→Tokens、k→万单位，任务名全中文）；npm build 通过
- 遗留: 提交后回填 CHANGELOG 哈希
- 时间: 2026-09-11 深夜

### S-0911-2500-AI透明化与设置侧边栏 ✅
- 目标: ①语气学习（Tone DNA）退役 → 每账号「文风提示词」（迁移 v10 转存旧数据）②AI 总开关（关闭=传统邮件模式，隐藏全部 AI 入口）③设置页改侧边栏分类（通用/邮箱账号/AI 配置/AI 用量/关于）
- 范围: backend(db/ai/api) + frontend(types/client/useAI新增/SettingsPage重写/Layout/MailBrowser/EmailReader/ComposeForm小改/DigestPage/DraftsPage/ManagerPage) + docs
- 产出: 提交 9480351（由写信台会话代提交，条目见 CHANGELOG）；ruff + npm build 通过；隔离实例 curl 全往返（迁移 v10 schema、style_prompt 设置/清空、停用态 400 文案、ai_enabled 开关）
- 协调: 与草稿保存会话并行无冲突（ComposeForm 新鲜重读后仅加条件渲染）；期间误向真实库插入过测试账号 t@t.com，已当场清理（id=3，无关联数据），真实账号未受影响
- 遗留: 提交后回填 CHANGELOG 哈希；后端改动需重启 python run.py 生效；AI 总开关与文风提示词待用户真实账号验证
- 时间: 2026-09-11 深夜 完成

### S-0911-2530-AI配置体验修补 ✅
- 目标: ①Base URL 填完自动拉取模型列表（免手动按钮、免先保存）②API Key 输入框默认明文可见（带显隐切换）③取消「默认」档案概念——全新安装不预建档案、旧迁移档案按模型名命名、历史自动生成的「默认」档案一次性按模型名重命名
- 范围: backend(ai/profiles.py, api/profiles.py) + frontend(client.ts, SettingsPage, ManagerPage 切换器标签) + docs
- 产出: 提交 2f941f5；ruff + npm build 通过；隔离实例 curl 全往返（见 CHANGELOG 验证行）
- 遗留: 自动拉取需用户真实 Key 验证（3c 已真实打到 DeepSeek 得 401 证明链路通）；后端改动需重启
- 备注: 用户明确规范「谁改动谁提交」——本会话起完成即自行 commit，不再留待提交（已增补 CLAUDE.md 规范 10）
- 时间: 2026-09-11 深夜 完成

### S-0912-0010-同步性能与Errno22 ✅
- 目标: 大批量邮件同步慢 + QQ 账号 [Errno 22] Invalid argument 根因修复（方案经用户确认：全做四步）
- 范围: backend(core/sync.py, imap_client.py, scheduler.py, api/accounts.py) + frontend(types/client/SettingsPage/AddAccountModal/MailBrowser/NotificationBell) + docs；顺带处理用户反馈：模型拉取 405（后端未重启所致，口头解答）+ AI Key 刷新后不可见（改明文回显，与 S-0911-2530 同链路）
- 产出: 提交 e8c0084；ruff + npm build 通过；隔离实例验证重试链路与 connection_error 标记（服务端视角）
- 遗留: 大邮箱断点续传待用户重启后验证
- 跟进: ①search→uids 误用修复 ②稀疏 UID 集合被服务器按区间展开 → 密度自适应拉取 ③账号/文件夹下拉持久化 ④最终真凶：畸形 Date 头(1900-01-01 垃圾邮件)致 astimezone 抛 Errno 22 同步死循环，容错降级修复，真机端到端 ok=True 新增 383 封（efd36e2）
- 备注: 期间用户 AI 档案被重建为单个 default 档案、key 为已失效遗留 key（****42b0，当日在 DeepSeek 平台侧已失效），已引导重新生成；另发现 notifications@whizzzest.com 冒用用户域名发 1900 日期垃圾验证码邮件，建议拉黑
- 备注: 用户两把 DeepSeek key（****42b0/****71b2）经真实验证均被平台判无效（42b0 当日早些时候曾成功，后于平台侧失效），已引导重新生成，非程序问题
- 时间: 2026-09-12 凌晨 完成

### S-0911-1614-AI密钥401排障与测试语义修复 ✅
- 目标: ①查清设置页 401「****42b0 is invalid」根因与保存机制是否有问题 ②语气学习「已下线」用量行删除 ③测试连接语义修复（用户选定范围）
- 范围: backend(ai/llm.py, api/profiles.py, db/database.py) + frontend(SettingsPage) + docs
- 排障结论: 非程序问题——key 在 DeepSeek 平台侧被删/重置（ai_logs 同 key 至 04:16 成功 58 次、07:27 起 401，本地零变更；裸 curl 复现）。保存管线四处一致无损。secrets.json 孤儿密钥 ****75dc（已删档案 83c543e0 残留）实测有效，已写回激活档案，测试连接 ok
- 产出: 测试连接空密钥直测不回退 + llm.friendly_error 401 人话提示（test/models 两处）+ 迁移 v11 清 tone_dna 用量（2 条）+ 前端删 TASK_LABELS 映射；ruff + npm build 通过；隔离实例（真库副本）curl 三态语义与迁移验证
- 遗留: 后端改动需重启 python run.py 生效（密钥恢复已即时生效，secrets.json 按请求读）；孤儿密钥对账清理、保存后卡片回读同步两项加固用户选暂缓；secrets.json 仍有 2 把无主孤儿 key（c9f6765f/39693236，GLM 疑似）待用户决定去留
- 时间: 2026-09-11 16:14 完成
