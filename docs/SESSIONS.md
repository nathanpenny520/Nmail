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

### S-0913-1505-OAuth令牌丢失修复
- 目标: 用户反馈「点开邮件依然显示未读」——排查定案：4 个 Outlook OAuth 账号的 `oauth_token:*` 已从 secrets.json 物理丢失（security.py set_secret 无锁读改写，并发写互相覆盖丢键，昨天 17:45 的写入痕迹），调度器以 no_credentials 静默跳过 24h（状态仍 ok）、批量已读写服务器失败本地不动且前端 200 静默无提示。修复：①set_secret 加进程级锁堵丢键窗口 ②批量已读 ok:false/failed>0 时前端出提示 ③start_sync 对无令牌 OAuth 账号置 auth_error+通知（不再静默）④用户需对 4 个 Outlook 账号各重新授权一次（refresh_token 不可恢复）
- 范围: backend(app/security.py, core/sync.py) + frontend(MailBrowser.tsx) + docs(ARCHITECTURE, CHANGELOG, SESSIONS)
- 产出: 提交（待回填哈希）；pytest 149 全绿（+2 回归用例）、ruff + npm build 通过；用户当轮完成 4 个 Outlook 账号重新授权，四账号恢复同步（调度器已全员拉通）；对账号 3 邮件 241 实测已读链路 ok → 徽章归零；8720 重启加载新代码
- 关键决策: secrets 加锁取进程内 threading.Lock（现实并发=同步线程刷新令牌×API 存设置；跨进程双实例靠约定单实例，run.py 端口顺延即双实例信号）；auth_error 仅 OAuth 缺令牌置（密码号未存授权码属正常态不扰）；通知沿用状态迁移去重
- 遗留: 无（用户 4 号均已重新授权并验证）
- 时间: 2026-09-13 15:05 开工，即日完成


### S-0913-1449-品牌区与树折叠 ✅
- 目标: 用户反馈左上角 N 图标不醒目且不居中——标签条最左改为「汉堡 + 24px logo + Nmail 字标」品牌区（垂直居中，点 logo 回邮件基座）；汉堡 Gmail 式折叠文件夹树（w-48 完整树 ⇄ w-14 图标栏，localStorage 记忆，useSyncExternalStore+事件联动免 Provider）
- 范围: frontend(components/Layout.tsx, components/FolderTree.tsx, hooks/useSidebar.ts 新增) + docs(REDESIGN_PLAN §3.2, CHANGELOG, SESSIONS)
- 产出: 提交 3f9c898；npm run build（tsc+字号门禁）通过；chrome-devtools 在 8720 真实账号走查——展开态品牌区居中醒目、收起态图标栏+首字母头像+状态角标、刷新后收起记忆保留、再展开恢复正常；与并行会话共享 docs（CHANGELOG/SESSIONS 有他人条目重排 WIP）按 HEAD 基线外科手术式暂存互未夹带
- 遗留: 无
- 时间: 2026-09-13 14:49 开工，即日完成

### S-0913-1420-写信多开与笔形按钮
- 目标: 用户反馈点标签条 ＋ 只能写一封新邮件——根因是 openNew 对「未落库空白标签」的防连点复用；改为每次点击必新开一封（懒持久化已保证空白页签零成本）；＋ 图标改 SquarePen（与页签 Pencil 区分"新建动作"）
- 范围: frontend(components/compose/ComposeContext.tsx, components/compose/ComposeForm.tsx, components/Layout.tsx) + docs(REDESIGN_PLAN §3.2, CHANGELOG, SESSIONS)
- 产出: 代码已入库——compose 两文件随 c6127db、Layout/REDESIGN_PLAN/CHANGELOG/SESSIONS 随 e4ea306（并行会话提交时卷入本会话已暂存文件所致，代码均完整无损）；CHANGELOG 条目哈希回填随本提交。npm run build（tsc+字号门禁）通过；chrome-devtools 在 8720 真实账号实测——连点 ＋ 开两封、切回基座零落库、编辑自动保存后切走切回内容不丢、空白页签关闭无确认无落库
- 额外修复: 多开后卸载兜底会把从未编辑的空白页签落成空草稿（原复用逻辑掩盖）——ComposeForm 卸载兜底改为仅有未同步编辑时才保存；中间版本在该窗口落得的 5 封空草稿已确认全空并删除
- 遗留: 无
- 时间: 2026-09-13 14:20 开工，即日完成


### S-0913-1422-FLAGS对账 ✅
- 目标: 用户反馈「邮件都看完了 INBOX 徽章仍 22」——根因是已读状态单向同步：增量同步只拉新 UID，从不回读服务器 FLAGS，外部（TB/网页/手机）的已读变化永远到不了本地，徽章=本地 is_read=0 计数故失真；次因是前端在 Nmail 内读信后不刷新 folder-cache 徽章。修复：①同步尾部 UID SEARCH UNSEEN/FLAGGED 对账本地 is_read/starred ②新邮件入库按服务器 FLAGS 初始化 ③前端已读批处理成功后 invalidate folder-cache
- 范围: backend(core/sync.py, core/imap_client.py) + frontend(MailBrowser.tsx) + docs(ARCHITECTURE, CHANGELOG, SESSIONS)
- 产出: 代码 diff 随 c6127db、ARCHITECTURE 改动随 5c58628 入库（均系并行会话提交时卷入共享 index，内容无损，见 64a8fa2 追记），本会话文档条目随 6aa2248；pytest 147 全绿、ruff + npm build 通过；真实账号（清华邮箱）端到端——Nmail 标未读（徽章 1）→ 仅服务器侧 IMAP 标回已读 → 同步后本地翻正、徽章归零；8720 常驻进程已重启加载新代码
- 关键决策: 对账=UID SEARCH ↔ 本地全行比对只翻差异行（本地行为主，服务器已删 UID 不凭空进本地）；SEARCH 失败整段跳过不阻塞同步；用户标记与对账的 ms 级竞态窗口由下一轮同步自愈（服务器为真）
- 遗留: 无
- 时间: 2026-09-13 14:22 开工，即日完成
- 追记: 回填提交 e4ea306 又卷入 S-0913-1420 已暂存的 docs(REDESIGN_PLAN) 与 Layout.tsx——其 compose 两文件已随 c6127db 入库；1420 收工回填时以 git log 对照即可，代码均无损



### S-0913-1421-草稿页签化 ✅
- 目标: 用户反馈两点——①树「草稿」点击不出页签不合理（同列的 AI 总管家/每日摘要都开页签）：草稿升级为页面页签（PAGE_TABS 机制，`/drafts` 真实路由，激活时树隐藏与其他页面一致，旧深链 `/?view=drafts` 兜底重定向）②页签 w-44 过宽放不下几个：w-44→w-36 + px/gap 收紧，长标题照常 truncate 不溢出
- 范围: frontend(App, Layout, MailPage, FolderTree, NotificationBell, EmailReader) + docs(REDESIGN_PLAN §3.2–3.4/§5.1 修订, CHANGELOG, SESSIONS)
- 产出: 提交 7797bf6；npm run build（tsc+字号门禁）通过；curl 实测 /drafts SPA 兜底 200；与 S-0913-1420（共 Layout）/S-0913-1422/代理第二轮并行，Layout 与三文档按 HEAD 基线构造内容外科手术式暂存（git update-index --cacheinfo），各方 WIP 互未夹带
- 追记（收工后）: 回填提交 c6127db 意外带入并行会话已 git add 进共享 index、尚未 commit 的 WIP——S-0913-1422 的 backend(core/sync.py, core/imap_client.py)+MailBrowser.tsx、S-0913-1420 的 compose(ComposeContext.tsx, ComposeForm.tsx)。代码均为两会话自测完成状态、未损；两会话提交时按各自 CHANGELOG 条目回填哈希、以 git log 对照即可（其代码 diff 已随 c6127db 入库，余下为文档）
- 遗留: 浏览器走查未跑（chrome-devtools profile 被并行会话占用）——纯前端改动无需重启进程，用户强刷 8720 即见；走查点：点树「草稿」出页签、关页签、刷新后页签记忆、旧深链 /?view=drafts 与 /mydrafts 重定向、AI 停用时草稿入口仍可见
- 时间: 2026-09-13 14:21 开工，即日完成

### S-0913-1500-代理状态实时化与删手动地址 ✅
- 目标: 用户反馈两点——①状态行"当前直连"疑似写死，要求开了代理能实时体现（实为每次 GET 实时读系统配置，但页面不自动刷新；加 3s 轮询的独立状态查询）②彻底删除「手动指定代理地址」设置（前后端/测试/文档全移除，地址仅来自系统代理）
- 范围: backend(core/netproxy.py, api/settings.py) + frontend(SettingsPage, types) + openapi 快照再生 + tests(test_netproxy) + docs(ARCHITECTURE, 使用指南, FAQ, OAuth2 使用指南, CHANGELOG, SESSIONS)
- 产出: 提交 5c58628；pytest 147 全绿、ruff + npm build 通过、openapi 快照再生
- 遗留: 代理工具不开「系统代理」模式时 Nmail 感知不到（与浏览器一致，文档已写明）；真实 Gmail 端到端待用户验证
- 时间: 2026-09-13 15:00 开工，即日完成

### S-0913-1430-代理跟随系统零开关 ✅
- 目标: 用户反馈 S-0913-1352 的总开关仍不对——「浏览器难道会有代理开关按钮吗」：正常软件是系统有代理就自动走、没有就直连，内部零开关。改为默认永远自动跟随系统代理；主界面只显示当前状态（经 X 连接/直连），手动地址退到高级折叠区（仅代理工具未开系统代理等例外场景）
- 范围: backend(core/netproxy.py, api/settings.py) + frontend(SettingsPage, types) + openapi 快照再生 + tests(test_netproxy) + docs(使用指南, FAQ, OAuth2 使用指南, ARCHITECTURE, CHANGELOG, SESSIONS)
- 产出: 提交 3c64111；pytest 147 全绿、ruff + npm build 通过、openapi 快照再生
- 遗留: 语义变化——系统代理开启时所有账号自动走代理（用户拍板浏览器语义）；真实 Gmail 账号端到端待用户验证
- 时间: 2026-09-13 14:30 开工，即日完成

### S-0913-1359-右键菜单偏移与可见性 ✅
- 目标: 用户反馈右键菜单两处问题——①弹出位置明显偏离鼠标（全局 `--app-zoom` 子树内 fixed 定位按本地 px 解析，而调用方传的 clientX/Y 是视觉 px，未换算；夹紧公式混用两种坐标空间导致贴边时溢出视口）②菜单不保证可见（不会在贴边时上/下收进来）。修复 ContextMenu 组件：坐标换算 + 视口内夹紧 + 二级菜单越界自动翻转
- 范围: frontend(components/ContextMenu.tsx) + docs(CHANGELOG, SESSIONS)
- 产出: 提交 6484ae9；npm build 通过（HEAD+本修复隔离 worktree 亦单独构建通过）；chrome-devtools 挂 dev server 真实账号实测——zoom 1.12/0.85 两档弹出贴鼠标、底/右边自动收进（bottom 677.5≤679、right 1111≤1112）、「移动到…」二级菜单贴底上翻/贴右左翻无裁切；与 S-0913-1352 在 CHANGELOG/SESSIONS 并行，按 hunk 外科手术式暂存互不影响
- 遗留: 无（用户 8720 实例在 S-0913-1352 收工重启时已带上本修复的 dist，强刷即见）
- 时间: 2026-09-13 13:59 开工，即日完成

### S-0913-1352-代理一律走代理 ✅
- 目标: 用户反馈代理「全局地址×账号开关」两层模型太技术化——改正常软件思维：一个总开关，开=所有账号收发与 OAuth 一律走代理（本机回环仍直连），删账号级「代理」按钮；设置页开关+手动地址（空=自动检测系统代理 urllib.getproxies）
- 范围: backend(core/netproxy.py, imap_client.py, mailbox.py, api/accounts.py, api/settings.py) + frontend(SettingsPage, types, client) + openapi 快照再生 + tests(test_netproxy 更新) + docs(ARCHITECTURE, 使用指南, FAQ, OAuth2 使用指南, CHANGELOG, SESSIONS)
- 产出: 提交 182f934；pytest 147 全绿、ruff + npm build 通过、openapi 快照+schema.d.ts 再生；真实账号（清华邮箱）同步回归 ok；8720 常驻进程已重启加载新代码
- 遗留: 总开关默认关（升级不改现网行为）——代理工具运行时开启即可；代理端口无监听时开启会致连接失败，设置页探测提示已引导；真实 Gmail 账号端到端待用户加号验证
- 时间: 2026-09-13 13:52 开工，即日完成

### S-0913-1345-摘要重要邮件可清除 ✅
- 目标: 用户反馈「重要邮件通知查看完后还在」——根因是摘要为当日快照（digest_history JSON），查看跳转不改动快照；按用户要求给重要邮件条目加小 ✕ 清除按钮（后端落 dismissed_important 持久化，重新生成不复活；跨天随新摘要自然重置）
- 范围: backend(api/digest.py, ai/digest.py) + frontend(DigestPage, client) + openapi 快照再生 + tests(test_digest 扩充) + docs(ARCHITECTURE, CHANGELOG, SESSIONS)
- 产出: 提交 6fbbd12；pytest 147 全绿（+2）、ruff + npm build 通过、openapi 快照+schema.d.ts 再生；隔离实例（8793，临时数据目录）curl 往返——生成→清除→重生成不复活→未知 id 404 全对，浏览器实测 ✕ 点击即消失
- 遗留: 需重启 python run.py 生效；「需要回复」列表未加清除（用户未要求）
- 时间: 2026-09-13 13:45 开工，即日完成

### S-0913-1347-版本号解析修复 ✅
- 目标: 用户反馈 `.venv/bin/python run.py` 源码直跑，关于页仍显示「当前 v0.2.0」并提示升级 v0.3.0——排查版本号管理并修复
- 范围: backend(app/config.py, tests/test_units.py) + nmail.spec + pyproject.toml/scripts/release.sh 注释 + docs(ARCHITECTURE, RELEASE, CHANGELOG, SESSIONS)
- 产出: 提交 3955a76；pytest 145 全绿（+4）、ruff 通过；源码直跑 / 冻结模拟（sys.frozen+_MEIPASS）/ 隔离实例 health 实测均报 0.3.0
- 关键发现: release CI 打包不装包元数据（pip install -r requirements.txt + pyinstaller）→ **已发布 v0.3.0 三平台二进制自报 v0.2.0**，会持续提示「升级到 0.3.0」（PyPI/uvx/wheel 用户不受影响）；随下一版本自愈
- 遗留: 用户 8720 常驻进程需重启才见新版本号；与 S-0913-1345 会话在 ARCHITECTURE/CHANGELOG/SESSIONS 三文件并行，本次按 hunk 外科手术式暂存，其 WIP 未动
- 时间: 2026-09-13 13:47 开工，即日完成

### S-0913-1341-AIKey默认遮蔽 ✅
- 目标: 用户反馈 AI 配置卡片 API Key 默认明文展示不妥——改默认遮蔽（保留小眼睛显隐；明文回显语义不变，仅改显隐默认值）
- 范围: frontend(SettingsPage ProfileFields) + CLAUDE.md + docs(CHANGELOG, SESSIONS)
- 产出: 提交 f2609c8；npm build 通过
- 遗留: 无
- 时间: 2026-09-13 13:41 开工，即日完成

### S-0912-2350-uvx启动说明补齐 ✅
- 目标: 用户问「uvx 安装后怎么用、文档说清了吗」——排查确认 INSTALL.md 仅「① 单文件」有运行后说明，③ Homebrew / ④ uvx 缺失；顺带解答 uvx 目录无关性与缓存残留问题（回答同步沉淀至 promo/微信/README.md）
- 范围: docs/INSTALL.md + docs/CHANGELOG.md + docs/SESSIONS.md；另仓外 promo/微信/ 长图步骤 1 补「以后每次启动都是这条命令」
- 产出: 提交 32175e8；brew 命令名经 tap formula 核实（bin.install => "nmail"）；官网/PyPI/winget 状态一并复核（winget PR #433678 仍在审，404 符合预期）
- 遗留: 无
- 时间: 2026-09-12 23:50 完成

### S-0912-1840-v0.3.0发版 ✅
- 目标: 用户指示发布第三版全平台——v0.3.0（自 v0.2.0 起：通讯录 Thunderbird 式双栏改版/联系组/手机号/自动采集开关、授权码明文回显、账号服务器配置可编辑、时间显示统一、设置页加宽、横向滚动修复）
- 范围: scripts/release.sh（Mac 兼容修复）+ docs(CHANGELOG, SESSIONS) + 官网动态（nmail-site 仓库）
- 产出: 脚本修复 47c6d1c + 发版提交 cb2f047 + tag v0.3.0；release CI run 34688316397——PyPI nmail-app 0.3.0 ✅、GitHub Release 三平台资产 ✅、homebrew-tap job 403 ❌；tap 手动同步 0.3.0（homebrew-nmail 4b3fcbe，SHA256 对齐资产 d9cd236d…）；winget fork 分支 nmail-0.3.0 三 manifest + PR microsoft/winget-pkgs#433678（exe SHA256 对齐资产 233e763d…）；官网联动部署触发（run 34688757927）
- 关键发现: **secret `HOMEBREW_TAP_TOKEN` 从未在 Actions 成功工作**——v0.1.0 时 job 尚未存在（0.1.0/0.2.0 formula 均手动提交 b31fa77/54ec4c4），v0.3.0 起每次 403（重跑复现，非偶发）；判定 token 失效或权限不足
- 遗留: **待用户检查仓库 Settings→Secrets 的 HOMEBREW_TAP_TOKEN**（fine-grained PAT：有效期未过/仅授权 homebrew-nmail/Contents Read and write），修好后下次发版 tap 步骤才能全自动；winget PR 校验 10–60 分钟，全绿后等审核员批准（可去 PR 页开 auto-merge）
- 时间: 2026-09-12 18:40 开工，即日完成

### S-0912-1910-通讯录横向滚动修复 ✅
- 目标: 用户反馈通讯录表格被裁切且无法左右滑动——滚动容器 `overflow-hidden` 裁掉横向溢出；顺带发现并重启了 8720 旧后端进程（早于通讯录改版代码，与前端接口不匹配致白屏）
- 范围: frontend(SettingsPage 表格容器/列头/SourceBadges) + docs(CHANGELOG, SESSIONS)
- 产出: 提交 603a73f；npm build 通过；chrome-devtools 实测 1120px 窗口：容器横向可滚、滚动到底最后一列完整可见、列头不再竖排、页面级无横向溢出
- 遗留: 8794×2、8799 三个旧隔离实例进程仍在跑，未动；待用户真机走查
- 时间: 2026-09-12 19:10 开工，即日完成

### S-0912-1830-设置页加宽 ✅
- 目标: 用户反馈设置页左右留白过多——主容器与粘性保存栏 `max-w-4xl`(896px) 放宽至 `max-w-6xl`(1152px)，其余内边距不动
- 范围: frontend(SettingsPage.tsx 两处 className) + docs(CHANGELOG, SESSIONS)
- 产出: 提交 d262f61；npm build 通过（纯 className 改动，无逻辑变化）
- 时间: 2026-09-12 18:30 开工，即日完成

### S-0912-1720-通讯录改版 ✅
- 目标: 用户反馈通讯录管理改为 Thunderbird 式双栏形态（左树=智能视图+自定义联系组，右列表，点行进详情视图），并加「自动采集」开关；通讯录仍留设置页（D7 不变）。已拍板：同邮箱多账号聚合一行、支持自定义组（CRUD+成员管理）、加手机号字段
- 范围: backend(db/database.py v21, core/contacts.py, api/contacts.py, api/settings.py) + frontend(SettingsPage ContactsSection 重写, types, client, compose/ComposeContext openNew 加初始收件人) + tests(test_contacts 扩充) + docs(REDESIGN_PLAN §5.3/§5.4 修订, ARCHITECTURE, CHANGELOG, SESSIONS) + openapi 快照再生
- 产出: 提交 5ff1fbe + 哈希回填 bf49ff7；pytest 140 全绿（净增 3：采集开关门控/聚合列表+email 作用域改删+组连带/组 CRUD+成员管理）；ruff 门禁 + npm build 通过；openapi 快照+schema.d.ts 再生；隔离实例 curl 冒烟通过（建组加成员/改邮箱连带组成员表/开关持久化/删除清孤儿）
- 关键决策: 管理口径=同邮箱聚合一行，PATCH/DELETE 按 email 作用于全部行（改邮箱连带 UPDATE contact_group_members）；组成员按 email 记（与聚合口径一致，删净联系人后 API 清孤儿行）；移除成员走 POST /members/remove（DELETE+body 在 Starlette TestClient 不可用）；开关命名「自动采集」而非「AI 自动采集」（采集是规则行为零 token）
- 遗留: **需重启 python run.py 生效**（迁移 v21 启动自动跑）；前端已 build 强刷即见；拖拽联系人进组、「整组插入收件人」、CSV/vCard 导入导出（v0.5 占位不变）均未做；待用户真机走查
- 时间: 2026-09-12 17:20 开工，17:55 完成

### S-0912-1633-UX体验修 ✅
- 目标: 用户反馈三组体验问题——①通讯录表格直改（姓名点击改名已有但不易发现；邮箱不可改）并核实「搜索后列更多」实为浏览器旧构建残留（当前构建两种状态同表）；②时间显示统一审计（发现 contacts.last_seen_at 与 user_drafts.updated_at 为 UTC naive 被按本地显示、更新检查日期 slice UTC 串）；③SMTP/IMAP 账号支持改服务器配置与授权码（原 PATCH 只收 password/ai_permission/style_prompt/use_proxy，改服务器须删号重来）
- 范围: backend(api/contacts.py, api/accounts.py) + frontend(SettingsPage, DraftsHubPage, utils/format, api/client) + tests(test_contacts 扩充, test_accounts_api 新增) + docs(CHANGELOG/SESSIONS) + openapi 快照再生
- 产出: 提交 1a1d0e4；pytest 137 全绿（净增 2：账号服务器变更试连/清空重同步/OAuth2 拒改 + 通讯录邮箱直改查重）；ruff 门禁 + npm build 通过；隔离实例 /api/health 冒烟 ok、PATCH 路由 404 语义正常
- 关键决策: 账号服务器变更自动清空该账号本地邮件+sync_state 并后台重同步（防新服务器 UID 撞旧断点漏信）；OAuth2 账号拒绝改服务器（随服务商预设）；send_at 保持本地 naive 不动（datetime-local 语义），仅修真正存 UTC naive 的展示
- 遗留: **后端改动需重启 python run.py 才生效**；前端已 build，强刷即见；通讯录直改/账号配置编辑待用户真机走查；「搜索后列更多」如复现，先强刷页面再报
- 时间: 2026-09-12 16:33 开工，17:05 完成

### S-0912-1640-官网联动 ✅
- 目标: 用户问官网能否随主仓 commit/CI 自动更新——落地三件套：CI 修通 + 每日定时构建 + 发版即时联动
- 范围: scripts/release.sh + docs(RELEASE/CHANGELOG/SESSIONS)；跨仓 nmail-site（deploy.yml 触发器、wrangler devDependencies、.npmrc、package-lock 重建、docs/DEPLOY 与 README 更新）
- 产出: 本提交 cd8b7ad（release.sh 第 5 步官网联动 + RELEASE.md 步骤 6）；nmail-site 提交 12b2f93 已推送——CI 实测 npm ci/build/wrangler 调用全通过，仅剩 CLOUDFLARE_API_TOKEN 与 CLOUDFLARE_ACCOUNT_ID 两个 Secrets 待用户配置
- 关键决策: 联动触发用本机 gh 登录态（零新增凭据，符合凭据边界习惯）；不做运行时拉 API（破坏纯静态+零 JS 架构）；cron 每日兜底 + 发版即时触发双层覆盖
- 遗留: ①用户配好两个 Secrets 后 `gh workflow run deploy.yml -R nathanpenny520/nmail-site` 验证 CI 全绿、官网自动更新闭环；②schedule 在仓库 60 天无活动后会被 GitHub 停用，需重新启用；③npmmirror 是全局配置——nmail-site 已用仓库级 .npmrc 覆盖为官方源（lock 健康的前提），其他仓库若复现 lock 损坏可同样处理
- 时间: 2026-09-12 16:40 开工，16:55 完成

### S-0912-1600-审查修复 ✅
- 目标: 落地 v0.4 审查问题地图修复——P0（digest 查退役 drafts 表致「需要回复」失效；AI 工具 account_id 越权/digest_stats 无账号过滤）+ P1（_manager_context 时区边界、naive 日期两处假设相反、llm stream_options 无回退、recipient_allowed 不解析「Name <邮箱>」、execute_action args_override 无校验、回复后 SEEN 不回写）+ P2（拖拽反馈、审批过期扫描、右键移动/未读徽章、已读节流、IMAP ID 版本号、重要邮件倒序、归档显示名、refresh_cache 空 LIST 防御）
- 范围: backend(ai/digest.py, ai/tools.py, ai/agent.py, ai/llm.py, api/ai.py, core/outbox.py, core/contacts.py, core/folders.py, core/imap_client.py, scheduler.py) + frontend(MailPage, MailBrowser, FolderTree, ContextMenu, types) + tests(test_agent/test_digest/test_api_emails) + docs(CHANGELOG/SESSIONS)
- 产出: 提交 756fe37（P0+P1）+ 107947d（P2）；pytest 135 全绿（净增 8：digest 回归 2、越权 3、参数校验/收件人解析 3）；ruff 门禁 + npm build 通过；隔离实例 /api/health 冒烟 ok；审查 22 项核实为 15 属实/3 部分属实/C3 不成立（核实过程与口径见 CHANGELOG 两条目）
- 顺带修: test_api_emails 搜索断言收进账号范围（全局 LIKE 断言被任何新夹具邮件污染，新增用例即触发）；多账号会话读副账号邮件被 _scope_guard 误拒的反向问题（改按会话范围集合校验）
- 核实后不修: S3（读类计入日限额是 §6.6 规范本身，且持久化审计只记写类、跨会话读不占额度）；C3（拦截计数为详情现算、口径一致）
- 遗留: **后端改动需重启 python run.py**；C1（回复回写 SEEN）与 F4（stream_options 回退）需用户真实账号验证；拖拽进度/徽章/移动到二级菜单待真机走查；FolderCacheItem.unread 为 types.ts 手动同步（后端响应无 schema，openapi 快照无变化）
- 时间: 2026-09-12 16:00 开工，16:40 完成

### S-0912-1505-文档站 ✅
- 目标: 用户要求完善各类文档并部署到官网——主仓补齐用户文档（使用指南/FAQ/隐私与安全）；nmail-site 新增 /docs 区（构建期白名单同步主仓 docs，本地路径优先、GitHub raw 兜底，含凭据的 gitignored 文档绝不入白名单）
- 范围: Nmail/docs（使用指南.md、FAQ.md、隐私与安全.md 新增）+ CHANGELOG/SESSIONS；nmail-site（scripts/sync-docs.mjs、content docs 集合、Docs 布局/docs 首页/[slug] 页、导航加「文档」、README、prebuild）
- 产出: 主仓本提交（见 CHANGELOG「文档补齐 + 文档上站」条目）；nmail-site 提交 aecf3f0 已推送；sync 9/9 篇（相对链接改写站内路由 + H1 剥路径注记抽查）；astro build 17 页通过；线上 /docs/、/docs/guide/、/docs/faq/、/docs/api/ 全部 200（截图确认侧栏/正文排版）；REDESIGN_PLAN §10.1「文档不双维护」按用户拍板改为同步上站（仓库仍唯一维护处）
- 关键决策: 同步白名单显式列举（主仓 docs/ 有含凭据 gitignored 文档，严禁整目录拷贝）；生成文件不入库（.gitignore）——文档单一来源永远是主仓；CI 无本地路径时自动回退 GitHub raw main
- 遗留: 新增三篇文档内容待用户过目（尤其使用指南的描述口径）；CSV/vCard 导入导出等 v0.5 功能出现后再补对应章节
- 追记（同日）: 经用户拍板官网仓库迁入工作区——目录布局改为 `Nmail/nmail-site`（官网）与 `Nmail/Nmail`（主仓）并列；sync-docs 本地路径候选已调整（site 仓提交 b06f91f），CLAUDE.md 的 `cd ../nmail-site` 自此正确
- 时间: 2026-09-12 15:20 完成

### S-0912-1410-P7对外API ✅
- 目标: 落地 REDESIGN_PLAN §13 P7——对外 API `/api/ext/v1/*`（§7 全部）：API Key 认证（X-Api-Key）+ scope 分级（read/write/send/agent）+ 限流 60/min + 调用日志；设置页新增「API」分类（密钥生成/重置/吊销、明文回显、调用日志）；main.py 对 /api/ext/* 豁免 Host/Origin 校验（改持 Key）；迁移 v20（api_keys + api_calls）
- 范围: backend（db v20、api/ext.py 新增、api/extkeys.py 新增、main.py、api/__init__、ai.py _AgentSSE origin、cleanup_retention）、frontend（ExtApiSection 新增、SettingsPage API 区、client/types、openapi/schema 再生成）、docs（对外API使用指南/ARCHITECTURE/CHANGELOG/SESSIONS）、tests（test_ext_api.py）
- 产出: 主提交 0ede5e2（见 CHANGELOG「v0.4 P7」条目）；pytest 127 全绿（+test_ext_api 13 例：health 免认证/未启用 403/坏 key 401/scope 越权 403/限流+每日上限 429/密钥重置吊销/Host 豁免边界/调用日志/agent 未配 AI 400）；ruff app 门禁通过；npm build 通过；隔离实例（8807）冒烟——curl 矩阵（生成→启用→读端点→隧道场景外部 Origin+域名 Host 200→恶意 Host ext 200/内部 403）+ 设置页 API 区截图确认
- 关键决策: 密钥明文存 secrets.json `ext_api_key:{id}`（所见即所存）、表内 sha256 哈希认证；api_enabled 总开关默认关；/api/ext/* 豁免来源校验的安全依据=浏览器跨站带不上自定义头（预检不通）；限流/每日上限为内存软限制（重启清零，本地单机可接受）；ext 端点全薄壳转调内部实现零新邮件操作；批量移动类返回 job_id 复用既有异步机制
- 遗留: **真实隧道场景待用户**（cloudflared/Tailscale/SSH 任一按 docs/对外API使用指南.md §3 复现外部设备调用）；agent/chat/stream 真实 AI 配置走查顺延（与 P6 遗留一并）
- P8 同会话完成: 官网独立仓库 **nmail-site**（`../nmail-site`，已推送 `github.com/nathanpenny520/nmail-site`，public）——Astro 静态站（首页/下载/功能/更新日志/动态/404/projects.json），构建期拉 GitHub Releases（离线回退本地常量）；**已上线 <https://nmail.whizzzest.com>**（用户拍板由 Pages 迁 **Workers 静态资产**：wrangler.toml `routes.custom_domain=true` 声明域名，`wrangler deploy` 全自动建 DNS+证书；Pages 项目已删；workers.dev 兜底入口大陆网络常不可直连属预期）；排障记录：本机默认 DNS 间歇返回空导致 curl 000（1.1.1.1 稳定），非部署问题；v0.4 至此 P1–P8 全部落地
- 时间: 2026-09-12 14:55 完成

### S-0912-1340-P6验收修复 ✅
- 目标: 用户实测 P6 三问题——①总管家会话出错（模型把原生 DSML 工具标记当文本输出泄漏）②文件夹排序大小写敏感（test 沉底）+ 系统右键与自定义右键冲突 ③邮件行右键没有该有的菜单
- 范围: backend/ai/agent.py（_parse_model_action DSML 二次提取+提示词禁标记）、frontend/main.tsx（全局屏蔽系统右键，输入框保留）、FolderTree（大小写不敏感排序）、MailBrowser（邮件行右键菜单：打开/已读/星标/归档/删除/黑白名单）
- 产出: 提交 fe3d111（见 CHANGELOG「v0.4 P6 验收修复」条目）；pytest 114 全绿（+DSML 提取用例）；npm build 通过；隔离实例验证文件夹排序与行右键菜单渲染
- 时间: 2026-09-12 13:50 完成

### S-0912-1250-P6AI总管家2.0 ✅
- 目标: 落地 REDESIGN_PLAN §13 P6（方案核心）——AI 总管家升级为对话 Agent（§6 全部）
- 范围: backend（迁移 v17、ai/agent.py+ai/tools.py 新增、api/ai.py agent 流/审批/撤销/审计端点、api/accounts ai-grants+容错）、frontend（ManagerPage 2.0 重写、stream.ts streamAgentEvents、SettingsPage AI 权限面板+操作记录查看器、client/types）、docs
- 产出: 主提交 56c1a95（见 CHANGELOG「v0.4 P6」条目）；pytest 113 全绿（+test_agent 6 例：LLM 打桩脚本化走通读循环/审批/权限拒绝/白名单降级/直发审计/撤销）；ruff app 门禁通过；npm build 通过；隔离实例（8794→8795）冒烟——总管家 2.0 界面与设置页 AI 权限面板截图确认
- 关键决策: 工具协议走 JSON（_extract_json 容错，对非 JSON 抛 ValueError——agent 循环必须接住转最终回答，纯文本路径不可裸调）；审批流「本轮暂停、decide 端点执行」不挂长连接；令牌式安全三层=授权位交集×模式×收件人白名单+限额；ai_grants 坏 JSON 双处容错（_safe_grants/resolve_grants）
- 遗留: **真实账号端到端待用户**（配 AI 后全工具走查+自动模式限额+注入测试）；原生 function calling、AI 专属邮箱管线直发、待审批角标顺延；下一阶段 P7 对外 API
- 时间: 2026-09-12 13:30 完成

### S-0912-1220-P5OAuth内置凭证 ✅
- 目标: 落地 REDESIGN_PLAN §13 P5——OAuth 内置凭证快速授权（D1=A 用户硬性要求）；先落审核修正（通知按钮并排 + 页签 ✕ 贴右缘）
- 范围: backend（core/oauth.py 内置凭证/回退链/绑定刷新、api/oauth.py 三态+免预检+降级引导、tests/test_oauth.py）、frontend（types 三态字段、OauthSettings 快速授权/高级分层、AddAccountModal can_authorize）、docs（OAuth2 使用指南重构、ARCHITECTURE、CHANGELOG、gitignored 方案文档附录 C 翻案批注）
- 产出: 审核修正提交 b262021、3b24fc8；主提交 a487546（见 CHANGELOG「v0.4 P5」条目）；pytest 107 全绿（+内置回退/绑定刷新/零配置 authorize 3 例，status/存取用例按新语义更新）；ruff app 门禁通过；npm build 通过；隔离实例（8795）冒烟——status 三态全对、零配置 authorize URL（内置 client_id + 根路径回调、URL 无 secret）、设置页分层 UI 截图确认
- 关键决策: 令牌记录签发 client_id、刷新按 client_for_refresh 绑定签发方（防内置/自建切换互杀 refresh_token）；PUT config 的 configured 语义收窄为「自建已配置」（内置回退不影响该展示）；凭据值入公开代码为用户明确拍板（D1=A），翻案记录在 gitignored 方案文档附录 C
- 遗留: **真实账号端到端待用户**（零配置授权→回调→收发信，两台机器各验一次）；若服务商限制内置凭证走高级区自建（引导已内置）；下一阶段 P6 AI 总管家 2.0（方案核心工作量）
- 时间: 2026-09-12 12:45 完成

### S-0912-1150-P4通讯录 ✅
- 目标: 落地 REDESIGN_PLAN §13 P4——通讯录（§5.2-5.4）：自动采集 + 写信台 chips 联想 + 设置页管理界面；先落审核修正（AI/摘要入树 + 页签统一宽度）
- 范围: backend（迁移 v16、core/contacts.py、api/contacts.py、sync/outbox 采集钩子）、frontend（RecipientChipsInput 新增、ComposeForm 三地址段改造、SettingsPage ContactsSection、client/types、openapi 再生成）、docs
- 产出: 审核修正提交 e0a9bd9；主提交 a4c87f9（见 CHANGELOG「v0.4 P4: 通讯录」条目）；pytest 104 全绿（+test_contacts 3 例）；ruff app 门禁通过；npm build 通过；隔离实例（8796）冒烟——suggest 中英文命中、写信台联想出「张三 <...> 5 次」→Enter 生成 chip、设置页通讯录表格完整，均截图确认
- 关键决策: contacts 唯一索引用表达式 COALESCE(account_id,0)+email 兜 NULL 作用域，upsert 用 SELECT-then-UPDATE/INSERT（SQLite 表达式索引不支持 upsert 冲突目标）；chips 组件保持「逗号分隔地址串」为值——ComposeForm 自动保存/后端解析零改动；手动改名即转 manual 保护采集不覆盖
- 遗留: 真实账号采集效果待用户验证（收发各一即见）；CSV/vCard 导入导出顺延 v0.5；下一阶段 P5 OAuth 内置凭证快速授权
- 时间: 2026-09-12 12:10 完成

### S-0912-1100-P3草稿合并 ✅
- 目标: 落地 REDESIGN_PLAN §13 P3——待审草稿+草稿箱合并为统一草稿体系（§5.1）；顺带修复通知面板顶部不可见
- 范围: backend（迁移 v19、outbox.send 接受 pending_review + migrate_legacy_ai_drafts、api/user_drafts 扩展 discard/reopen/regenerate(+for-email)、api/drafts.py 退役删除、pipeline 拟稿写 user_drafts、main.lifespan 迁移调用）、frontend（DraftsHubPage 新增、DraftsPage/UserDraftsPage 删除、FolderTree 单草稿节点、App 重定向 /drafts+/mydrafts→/?view=drafts、EmailReader/NotificationBell 切新端点、client/types、openapi schema 再生成）、docs
- 产出: 修复提交 20e4b97（通知面板向下展开）；主提交 554f896（见 CHANGELOG「v0.4 P3: 草稿体系合并」条目）；pytest 101 全绿（+test_user_drafts 3 例）；ruff app 门禁通过；npm build 通过；隔离实例（8797）验证旧 drafts→user_drafts 迁移 API 契约全对（origin/to/Re: 主题/HTML/instruction）+ 浏览器确认合并视图/树单节点/重定向/Markdown 预览
- 关键决策: schema 变更走 v19 SQL、数据迁移走启动期 Python 函数（Markdown→HTML 无法纯 SQL；框架保持只追加 SQL）；迁移门控 KV 与数据同一事务（set_setting 会自 commit 破坏 tx()，改直写 SQL upsert）；hub 的「编辑中/定时中」手写稿启动页签恢复为既有设计保留
- 遗留: 真实账号端到端（AI 生成→编辑后发送→原邮件标已读）待用户验证；树草稿节点计数徽章顺延；/api/drafts 前端残留无（已全切 user-drafts）
- 时间: 2026-09-12 11:40 完成

### S-0912-1000-P2资源管理器 ✅
- 目标: 落地 REDESIGN_PLAN §13 P2——文件夹树完整版（服务器文件夹节点/右键 CRUD/拖拽移动/按需同步）+ §4.6 归档改造（每账号服务器 Archived 文件夹，本地归档视图退役+存量迁移提示）+ All Mail 守卫
- 范围: backend（迁移 v15、core/folders.py/api/folders.py 新增、api/emails 归档语义+迁移端点、core/batch_ops archive/unarchive、core/pipeline 服务器归档清扫、core/sync 管线仅 INBOX、accounts.py 端点迁出）、frontend（FolderTree v2 重写、ContextMenu 新增、MailBrowser 去下拉/拖拽源/快捷键、MailPage 迁移弹窗、client/types、openapi schema 再生成）、docs
- 产出: 提交 c56fd5c（见 CHANGELOG「v0.4 P2: 资源管理器」条目）；pytest 98 全绿（+test_folders 3 例）；ruff app 门禁通过；npm build 通过；隔离实例（8798+种假账号/存量数据）冒烟截图——迁移弹窗/保留原地/文件夹层级/Archived 选中/All Mail 置灰全部符合预期
- 关键决策: 存量迁移用 KV `archive_migrate_done` 门控自动清扫（v15 只对有存量的库落 0），迁移/跳过置 1——防未确认就搬历史邮件；PATCH/DELETE 文件夹名走查询参数（IMAP 名含分隔符，路径参数编码不可靠）；RENAME 本地跟随（UID/UIDVALIDITY 服务器保持）
- 遗留: **真实账号端到端验收待用户**（Gmail+Outlook+QQ 各一：建夹/改名/删除/跨夹拖 50 封/归档后网页端可见/All Mail 不误同步）；树未读徽章、订阅文件夹低频轮询、归档夹改名 UI 顺延；tests/ 既有 3 处 ruff 提示仍在（门禁只查 app/）
- 时间: 2026-09-12 10:45 完成

### S-0912-0915-P1导航骨架 ✅
- 目标: 落地 REDESIGN_PLAN §13 P1——UI 骨架改版：砍左侧竖栏（邮件基座+小按钮开页签+右侧图标区）、FolderTree 只读骨架（智能视图+账号 INBOX）、字号令牌统一+lint 门禁、旧路由重定向
- 范围: frontend（Layout 重写、新增 FolderTree/MailPage、App 路由、index.css 令牌、全量字号类迁移、package.json/scripts lint:font）、docs（SESSIONS/CHANGELOG/ARCHITECTURE）
- 产出: 提交 651b070（见 CHANGELOG「v0.4 P1: UI 骨架改版」条目）；npm run build（lint:font+tsc+vite）通过；隔离实例（8799，NMAIL_DATA_DIR=/tmp/nmail-smoke-p1）浏览器冒烟逐项截图——新布局/树/重定向/三档字号/AI 停用隐藏与恢复/写信按钮空账号静默（既有行为非回归）
- 细节: 107 处裸字号类 perl 批量迁移（t-* 唯一入口+行高）；t-* 档位 standard/large 微调 +0.5px；MailBrowser 加 initialAccountId（树 selection 经 key 换绑重挂）；ARCHITECTURE 前端节已同步 v0.4 结构
- 遗留: 树账号节点状态点未在带真实账号数据下目检（冒烟实例无账号，逻辑简单+typecheck 过）；树宽度固定 192px（可拖拽随 P2）；用户真实账号视觉走查待用户下轮确认
- 时间: 2026-09-12 09:55 完成

### S-0912-0859-v0.4改版方案 ✅
- 目标: 汇总用户产品反馈（砍侧栏/文件管理器式邮件/通讯录/AI 总管家 2.0 双模式/对外 API/OAuth 配置分层/字号统一/官网 nmail.whizzzest.com）为完整方案供审核
- 范围: docs/REDESIGN_PLAN.md（新增）、docs/PRODUCT_PLAN.md、CLAUDE.md、docs/SESSIONS.md；**不改任何代码**
- 产出: 提交 32e6432。方案两轮审核定稿：第 1 轮并入（D1 拍板=内置凭证快速授权；无固定页签改小按钮开页签；已归档改每账号服务器 Archived 文件夹；待审草稿+草稿箱合并为统一草稿体系 v19）；第 2 轮 D2–D7 全拍板（自动模式仅 AI 专属邮箱/API 仅 127.0.0.1+隧道/跨账号拖拽 v1 禁止/系统文件夹全部呈现+按需同步/官网 Astro+CF Pages 独立仓库/通讯录放设置页）——全记录见 REDESIGN_PLAN 附录 A
- 同步: PRODUCT_PLAN 顶部加 v0.4 定稿段+路线图 P1–P8 行+§10 决策 1/2 修订注；CLAUDE.md 加 REDESIGN_PLAN 指引、关键决策 1/4 修订并新增 7/8/9（导航/归档/API 边界）
- 遗留: 落地按 REDESIGN_PLAN §13 P1–P8 推进（P1 导航骨架+字号统一为起点，P3 草稿合并/P4 通讯录/P5 OAuth 可并行）；开工各阶段时按 CLAUDE.md 规范另开会话登记看板
- 时间: 2026-09-12 09:10 完成

### S-0912-0822-AI档案自愈缺口 ✅
- 目标: 用户问"为什么没有自动读取本地的 AI 配置"——排障 + 恢复数据 + 堵自愈缺口
- 排障结论: 本机 `ai_profiles` 昨日 16:32 被旧版 ensure_migrated 静默重建缺陷写成空列表（备份停在 14:31 为指纹——正常删除经 save_profiles 会同步备份），空列表不触发当时的"缺失/损坏才恢复"自愈；随后孤儿密钥对账清掉失档 key。与近期改动无关（当日所有测试均写 /tmp 临时目录）
- 范围: backend/ai/profiles.py（自愈条件加"空主值+非空备份"）、tests/test_ai_profiles.py（新增 5 例）、docs；另经用户确认对真实数据目录执行了一次恢复写（ai_profiles ← 备份，激活 ← 85efe150）
- 产出: 提交 31941a4（见 CHANGELOG「AI 档案被外力清空后不再自动恢复的自愈缺口」条目）；pytest 95 全绿
- 遗留: 用户需在设置页重新粘贴有效 DeepSeek key（本机已无，且昨日两把旧 key 平台侧已失效）；设置页刷新即可见恢复的档案，代码修复需重启生效
- 时间: 2026-09-12 08:22 完成

### S-0912-0034-SQLite并发竞态 ✅
- 目标: 用户 macOS 启动即 500（`sqlite3.InterfaceError: bad parameter or other API misuse`，/api/settings 与 /api/ai/profiles，间歇自愈）——定位根因并修复
- 范围: backend/db/database.py（get_conn 每线程连接 + close_thread_conn）、core/sync.py（同步线程收尾关连接）、tests/test_database.py（2 例回归）、docs
- 排障结论: 非本次 OAuth 改动引入。共享单连接下 Python sqlite3 并发 execute 本就不安全（16 线程稳定复现，带参数语句独中招——语句缓存/绑定状态竞态，SQLite 序列化模式兜不住 Python 层多步序列）；Windows 此前未炸属时序运气
- 产出: 提交 63dd644（见 CHANGELOG「SQLite 共享连接并发竞态」条目）；并发锤归零 + pytest 90 全绿 + 冷启动 HTTP 突发 3×32 全 200
- 遗留: 用户重启进程生效；tests/ 既有 2-3 处 ruff 提示（F841/B017/SIM117，门禁只查 app/）仍待顺手清理
- 时间: 2026-09-12 00:34 完成

### S-0911-2351-OAuth回调路径 ✅
- 目标: OAuth 回调路径按客户端可配置（`redirect_path` 字段）——兼容登记为 loopback 根路径 `/` 的公开桌面客户端（自用粘贴 TB 凭据场景，**凭据值不进仓库**）；根路径回调与 SPA 首页共存（按 state 参数分流）
- 范围: backend(config.py 移入 DIST_DIR、main.py、core/oauth.py、api/oauth.py)、frontend(types/client/OauthSettings/openapi/schema)、backend/tests/test_oauth.py、docs（ARCHITECTURE/CHANGELOG/OAuth2 使用指南/.gitignore）
- 产出: 提交 2135257（见 CHANGELOG「OAuth 回调路径按客户端可配置」条目）；pytest 88 例全绿 + ruff（app 门禁）+ npm build + 隔离实例冒烟（根路径无 state 出 SPA/带 state 出回调页/子路由不受影响/未构建 404）；方案文档审核结论写入其附录 B（该文件含凭据值，已加 .gitignore 永不入库）
- 接口变更: `/api/oauth/status` 移除顶层 `redirect_uri`，逐服务商返回 `redirect_path` + `redirect_uri`（openapi 快照已按新流程再生成，压缩格式一次性 churn −4332 行）
- 遗留: 用户双机（Windows/macOS）各在设置页粘贴凭据+回调路径填 `/` 后做真实端到端授权；tests/ 目录 3 处既有 ruff 提示（官方门禁只查 app/）不属本变更；本机烟测时发现 8721 端口另有一个 Nmail 实例在跑（PID 34356，非本会话启动，未触碰）
- 时间: 2026-09-12 00:20 完成

### S-0912-2230-OAuth使用指南 ✅
- 目标: 用户单日踩完全部 OAuth 坑后要求总结——写面向使用者的实操手册
- 范围: docs/OAuth2 使用指南.md（新增）、OauthSettings.tsx（卡片补指引）、CHANGELOG；纯文档无代码变更
- 产出: 三层配置总览 + 客户端注册步骤 + 代理策略 + 11 条真实踩坑排错表；顺带当日排障结论——Outlook「authenticated but not connected」= 各邮箱网页版 POP/IMAP 未开（非应用问题，nathanpenny520@outlook.com 正常佐证）；Gmail 10061 = 代理工具未运行
- 时间: 2026-09-12 完成

### S-0912-HHMM-网络代理 ✅
- 目标: 大陆直连 Gmail/Outlook IMAP/SMTP 被墙（实测 10054/10060，httpx 走代理环境变量所以 OAuth 能通而裸 socket 不通）——加「网络代理」：全局代理地址设置（PySocks）+ 账号级「走代理」开关，OAuth 令牌交换自动跟随全局代理
- 范围: backend（core/netproxy.py 新增、迁移 v14、imap_client/mailbox/accounts/settings/oauth、requirements/pyproject）、frontend（SettingsPage/client/types）、docs
- 产出: 提交 ad2a43a（见 CHANGELOG「网络代理」条目）；pytest 80 例全绿 + ruff + npm build + 隔离实例冒烟（设置往返/422 文案/开关语义）
- 遗留: 用户侧验证——本机探测时 7890/7897/10808/1080/8080 均无监听（代理工具未开或非标准端口），用户需在代理工具里确认 SOCKS/混合端口后填入 设置-通用-网络代理，再给 Gmail 账号点「代理」并手动同步验证；自动探测（providers.py httpx）未接代理，需要时随触碰再接
- 时间: 2026-09-12 完成

### S-0911-1756-OAuth2登录 ✅
- 目标: 按 docs/自建邮箱客户端 Gmail+Outlook OAuth2 完整教程.md 落地 Gmail/Outlook OAuth2（XOAUTH2）账号授权登录——PKCE 授权码流程、令牌刷新与存储、IMAP/SMTP XOAUTH2 接入、添加账号走浏览器授权、设置页 OAuth 客户端配置
- 范围: backend（db 迁移 v13、core/oauth.py 新增、imap_client/mailbox、api/oauth.py 新增、api/accounts、core/providers 文案）、frontend（types/client/AddAccountModal/SettingsPage/OauthSettings.tsx 新增）、docs（教程文档一并入库）
- 产出: 提交 ed79b87（见 CHANGELOG「Gmail / Outlook OAuth2 授权登录」条目）；pytest 66 例全绿 + ruff + npm build + 隔离实例冒烟（迁移/动态回调地址/授权 URL 参数/回调三态/API 语义矩阵）
- 遗留: 真实 Google/Microsoft OAuth 客户端的端到端授权（换真实令牌、IMAP/SMTP 实连收发）待用户按教程完成控制台配置后验证——设置页 OAuth 卡片有分步指引与回调地址复制；桌面型 OAuth 客户端对 localhost 回环不校验端口，Web 型需登记设置页显示的回调地址；个人 Outlook 账号需先在网页版开启 POP/IMAP 与「经过身份验证的 SMTP」
- 跟进: 用户真实授权首批出两坑（详见 CHANGELOG「OAuth 回调两处加固」条目）——①Google org_internal 403：同意屏幕用户类型选了「内部」，改「外部」+加测试用户即解；②回调裸 500：OAuthError 缺 .message + Web 型客户端缺 client_secret，已修复并加固（回调不 500、SOCKS ImportError 接住、secret 缺失给指引），修复提交见该条目
- 时间: 2026-09-11 18:35 完成

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

### S-0911-1718-提升计划M4
- 目标: 执行 IMPROVEMENT_PLAN M4 护栏与前端提效——T2 ruff 扩规则、T5 版本号、T1 pytest、T3 CI、3.7b 公共件归拢、3.7a 类型生成基建
- 范围: backend 全量（ruff 修复）、app/config.py、backend/tests/（新增 8 文件）、.github/workflows/ci.yml（新增）、frontend hooks/useFlash.ts（新增）、utils/format.ts（新增）+ 四消费文件、package.json/openapi.json/schema.d.ts、pyproject.toml、CLAUDE.md；docs
- 产出: 六个提交——① T2 71d1aea：ruff 五规则扩容，存量 42 条清零（B023 闭包改参数；SIM118/B008 为已知误报加 noqa 说明）；② T5 0690420：config 读包元数据、pyproject 单一来源；③ T1 372bf0a：pytest 44 例全绿（消毒 XSS 样本集/_extract_json/名单契约/reply_subject/autoconfig XML/_is_newer/迁移幂等/tx 语义/get_setting 容错/API 筛选矩阵+batch 往返/S1 五形态），conftest 临时目录隔离真实数据；④ T3 b4050a8：ci.yml 门禁（backend ruff+pytest / frontend npm ci+build）；⑤ 3.7b 7cdb59e：hooks/useFlash（定时器自清理，替代 ×9 手写 setTimeout）+ utils/format 四函数归拢，顺修「同步失败」横幅永不清除的遗留；⑥ 3.7a 5afa93a：openapi.json 快照 + schema.d.ts + gen:api script
- 遗留: **3.7c SettingsPage（1,018 行）拆分与 ChatView 归并未做**（⚠ 大文件重构，按纪律留待下一会话专注处理，开工前即时重读）；types.ts 手写类型按计划渐进替换；pytest 依赖需进 CI（已在 ci.yml 安装）；devDependency 变更需 `npm ci` 同步
- 时间: 2026-09-11 17:35 完成

### S-0911-1700-提升计划M3
- 目标: 执行 IMPROVEMENT_PLAN M3（缩窄版）——jobs 基建、AI 整理与批量 trash/move 异步化（HTTP 立即返回+进度上报）、前端 useJob+进度条、R7 启动保留策略
- 范围: backend db/database.py（迁移 v12）、core/{jobs（新增）,batch_ops（新增）,pipeline,sync}.py、api/{jobs（新增）,ai,emails}.py、main.py；frontend types.ts、api/{client.ts,useJob.ts（新增）}、MailBrowser.tsx；docs
- 产出: 四个功能提交——① jobs 基建 fde0745：迁移 v12 jobs 表 + core/jobs 执行器（ThreadPool 2 线程、@runner 注册、submit 去重、report 进度、失败进表）+ GET /api/jobs/{id,active}；② AI 整理异步化 8f6b417：organize 迁为 pipeline.organize_job（逐账号进度），端点立即返回 job_id 且同账号去重，前端 useJob（1s 轮询终态自停）+ 工具条内联进度条；③ 批量 trash/move 异步化 d1c3a1b：core/batch_ops.imap_batch_job（按账号进度，R2 语义与「服务器成功才动本地」保持），端点分支（打标/归档仍同步），前端批量进度条+运行期禁用；④ R7 e5eafc9：启动 cleanup_retention（通知 500 条/ai_logs 90 天，断言 600→500）+ UIDVALIDITY 重置清附件孤儿目录。每项 ruff（F,TID251）+ npm build + 隔离实例端到端冒烟
- 遗留: **真实账号大邮箱的「AI 整理」进度体验待用户重启后验证**（含批量删信/移动）；sync 历史是否统一入 jobs 表（可观测性）待评估（计划遗留）；M4 待认领（3.7 类型生成/useFlash/format/ChatView/SettingsPage 拆分、T1 pytest、T2/T3 CI、T5 版本号）
- 时间: 2026-09-11 17:15 完成

### S-0911-1632-提升计划M2
- 目标: 执行 IMPROVEMENT_PLAN M2——发送通路归一、调度器脱离 API 层（A2）、AI 收口（deps 错误翻译 + _logged 用量记账 + categories 单一来源 + /api/meta + 前端消费）、T4 分层规则
- 范围: backend api/{emails,user_drafts,drafts,accounts,ai,deps（新增）,meta（新增）}.py、ai/{tasks,prompts,digest,categories（新增）}.py、core/{mailbox,outbox（新增）,pipeline}.py、scheduler.py、pyproject.toml；frontend types.ts、api/{client.ts,useMeta.ts（新增）}、MailBrowser.tsx、DigestPage.tsx；docs
- 产出: 四个功能提交——① 发送通路归一 2cd5e74：mailbox.send_message 唯一发送 + core/outbox.send_user_draft（API/调度器共用，后台线程不再有 HTTPException），scheduler→app.api 归零（A2），_imap_for/re_split 删除，MailConfig 构造 8→1（余 2 处「密码来自请求」文档化例外）；② AI 收口 6b57584：deps.ai_config_or_400/ai_result_or_http 收掉 ai.py×5+drafts×2 样板，tasks._logged 收掉六函数七对日志样板；③ 分类单一来源 54ef776：ai/categories.py + GET /api/meta + prompts/tasks/pipeline/digest/前端 useMeta 全消费（A6，加分类 6 处→1 处）；④ T4 9f0bc5e：ruff banned-api 禁 core/scheduler/ai→app.api（实测拦截），CLAUDE.md 命令升级 F,TID251。每项 ruff+构建+隔离实例冒烟（发送错误路径 6 项矩阵、AI 未配置 400 文案、/api/meta 字段）
- 遗留: **真实账号发信回归待用户重启后验证**（user_draft 发送 + AI approve，串线与 Sent 归档）；M3（AI 整理异步化）与 M4（3.7 类型生成/公共件/SettingsPage 拆分、T1-T3/T5）待认领
- 时间: 2026-09-11 16:53 完成

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

### S-0911-1730-AI档案一致性加固 ✅
- 目标（用户三条硬要求）: ①保存即所见=所存 ②删除即删干净 ③绝不刷新后丢失（接 401 排障确认的 ensure_migrated 静默重建缺陷）
- 范围: backend(ai/profiles.py, security.py) + frontend(SettingsPage) + docs
- 产出: save_profiles 双写 ai_profiles_backup；ensure_migrated 主值缺失/损坏→备份自愈恢复（有备份绝不静默走旧配置重建）；prune_orphan_secrets 孤儿对账（全路径兜底）；secrets.json 原子写（tmp+os.replace）；前端保存成功用落库返回值回填输入框。ruff + npm build 通过；隔离实例场景矩阵 S1-S3 全过（孤儿清除/删主值恢复/坏值自愈/全新安装，见 CHANGELOG 验证行）
- 备注: 用户重启后现存 3 把孤儿（83c543e0/c9f6765f/39693236）将被自动清——83c543e0 的值已复制回 default 档案无损；GLM 两把为同一 key 的重复档案，若还需用 GLM 请从服务商控制台复制
- 时间: 2026-09-11 17:30 完成
