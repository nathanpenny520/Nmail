# Nmail 变更记录（docs/CHANGELOG.md）

> 规范：每次功能变更在同一提交内在此追加一条。格式：`## 提交短hash — 标题` + 要点。
> 与 git 提交一一对应；本文件是"发生了什么"，ARCHITECTURE 是"现在是什么样"。

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
