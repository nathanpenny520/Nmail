# Nmail 变更记录（docs/CHANGELOG.md）

> 规范：每次功能变更在同一提交内在此追加一条。格式：`## 提交短hash — 标题` + 要点。
> 与 git 提交一一对应；本文件是"发生了什么"，ARCHITECTURE 是"现在是什么样"。

## f26fe2f — feat: 新构建自动感知——后端更新前端后页面提示一键刷新
- 用户反馈缓存问题「还在」：缓存策略只保证刷新一次即最新，但已打开的页面跑在内存里，后端更新前端后不刷新就永远是旧界面（如新按钮要手动刷新才出现）——缺「有新版本」的感知
- 机制：vite 构建收尾写 dist/build-id.json（每次 build 唯一）+ define 注入前端 __BUILD_ID__；/api/meta 现读该文件下发 frontend_build；前端 NewBuildBar 每 30s 轮询比对，不一致弹底部浮条「Nmail 已更新，刷新启用新界面」（一键 reload）。dev 模式热更新自带不启用；后端无指纹（旧 dist）不提示；不重启只重新 build 也能被感知（每请求现读）
- 验证：build 产物含 build-id.json 且 __BUILD_ID__ 内联；/api/meta 返回指纹与缓存头实测正确；pytest 302 绿；ruff 通过
- 会话：S-0921-1200（续）

## 597239f — fix: Ctrl+C 退出不再打印 KeyboardInterrupt 堆栈
- 用户反馈终端 Ctrl+C 停服务后打出一整段 CancelledError/KeyboardInterrupt 堆栈——实为正常退出路径（uvicorn 已优雅关停、数据无损），但 Python 默认把 KeyboardInterrupt 当未捕获异常打印，观感像出错
- 修复：cli `_launch` 捕获 KeyboardInterrupt，打一行「Nmail 已退出。」收尾；服务行为零变化
- 会话：S-0921-1200（续）

## e27e36b — feat: AI 审查全程可见——按钮分阶段文案 + AI 不可用必确认
- 用户反馈 77 号草稿 14:44 发出但 ai_logs 零 send_review 记录（76 号 13:40 发送前有成功审查记录）——AI 审查是否真的跑了对用户不可见，静默降级让人误以为「AI 审过了」
- 修复：①发送按钮分阶段文案——「检查中…」（规则层毫秒）→「AI 审查中…」（LLM 秒级），AI 审查从始至终可见 ②AI 审查未能运行（失败/未配置，ai_error 非空）时**必须弹卡确认**（列出原因 + 仍要发送/返回修改），不再静默直发；用户主动关掉 AI 开关（ai_error 为空）则不打扰 ③AI 审查确实运行且无问题 → 不弹卡直接发送（保持流畅）
- 草稿待审列表「批准并发送」同步；npm build 通过
- 会话：S-0921-1200（续）

## 8637844 — fix: SPA 缓存策略——发新版后浏览器不再停留在旧界面
- 用户重启后端后界面仍是旧版（模板主题/附件、发送前检查都不出现）：StaticFiles 默认只发 ETag 不发 Cache-Control，浏览器按「文件年龄 10%」启发式自行决定新鲜期、期间不回源；旧 index.html（壳）配缓存的旧 JS = 完整旧界面
- 修复：`_local_source_guard` 中间件出口统一加缓存头——index.html（dist 唯一 text/html）`no-cache` 每次回源验证（ETag 命中即 304，开销可忽略）；/assets/*（Vite 哈希文件名）`public, max-age=31536000, immutable`。按响应类型判定而非路径形态：`/` 的响应在 Starlette Mount 内部生成、`get_path` 把路径归一成 `.`（静态文件路径判断曾三改仍漏），中间件层无死角
- 验证：ASGI 全栈探针五路径（/、/index.html、/mail、/assets/*、/api/*）头全对；pytest 302 绿；ruff 通过
- 会话：S-0921-1200（续）

## 8637844 — feat: 发送前检查两阶段渐进——规则问题秒出、AI 深审追加展示（修「条目跳变/像卡住」）
- 用户实测反馈：①审查卡条目过一会突然消失 1-2 条 ②点发送要等几秒才有 AI 结果、像卡住了。根因：点发送到弹卡期间按钮可重复点击/回车，两次并发 precheck 各自请求 LLM（结果非确定），后返回的整卡覆盖前一张 → 条目跳变；而等待期无任何进行中反馈 → 用户重试
- 修复（纯前端，后端不动）：发送流程改**两阶段渐进**——第一波规则层（毫秒）有问题立即弹卡，卡内显示「AI 深审进行中」spinner；第二波 AI 深审（几秒）回来后**只增不删**地合并进卡（AI 条目以 ai_ 前缀与规则条目天然不重叠）；规则+AI 全过则不弹卡直接发送。全程 `checkingRef` 单飞防重入（按钮转「审查中…」禁用，重复点击/回车无效）；用户「仍要发送/返回修改」后迟到的 AI 结果由 `skipAiRef` 丢弃不弹卡
- 「批准并发送」（草稿待审列表）同样两阶段化，体验一致
- 澄清：规则检查**无开关、默认必开**（毫秒级零成本）；AI 深审开关在 设置→写信→「发送前 AI 审查」（默认开，未配 AI 自动降级仅规则层）。执行顺序：规则层先行 → AI 层叠加，两层独立不互相推翻
- 验证：npm run build（tsc）通过；pytest 302 绿
- 会话：S-0921-1200（续）

## e02c0fe — feat: 发送前检查（规则层+AI 深审）+ 模板带主题与附件
- 用户痛点三连：模板信改漏（占位符残留）、说有附件实际没带、空主题照发。方案经用户确认（拦截策略两条：人工可强制越过；定时/AI 自动发送 blocker 不发出、退回写信台并通知）
- **发送前检查规则层**（core/precheck.py 新模块，零成本零 AI 依赖，三个发送入口共用）：空主题 blocker；占位符残留 blocker（`{x}`/`[x]`/`___`/X 序列/中文占位词，方括号内纯数字时间编号白名单，X 占位避开邮箱/网址）；附件意图核对——正文提到附件但没带=blocker、带了但正文全未提=warn。人工发送：REST `POST /api/user-drafts/{id}/precheck` → 前端 PrecheckModal 弹卡（问题分组 + 仍要发送可越过，precheck 不可用不挡发送）；定时发送（scheduler.send_due_drafts）：blocker 不发出、退回 editing、写通知（复用既有失败退回模式）；AI 总管家 send_draft：拒发并把问题回给 agent 修正后重试
- **AI 深审**（ai/tasks.review_send_draft，一次 LLM 调用 JSON 输出 blockers/warns，正文截断 4000 字，ai_logs 记账 send_review）：附件意图与实际清单、模板痕迹、主题与正文匹配、称呼/日期硬伤、明显错别字。开关 `ai_send_review`（默认开，设置页「写信」新开关；未配置/失败自动降级仅规则层不挡发送）；precheck 端点与 scheduler、AI 发送路径均叠加
- **模板升级带主题与附件**（S-0921）：`compose_templates` 条目加可选 `subject`/`attachments` 元数据（KV 整存整取，老模板无字段行为不变）；附件二进制落盘 `data_dir/compose_template_files/<template_id>/`（目录函数在 core/outbox.template_files_dir——ai 层禁 import api 层），KV 只存元数据，上传/删除走条目级端点（上传要求模板已保存；单模板总量 50MB 上限）；update_extras 整存时 diff 清理被删模板/清空附件的落盘文件。前端：模板编辑弹窗加主题框+附件管理（上传/删除即时生效，同步回编辑表单），模板菜单应用时正文插光标处（不变）+空主题自动填模板主题（不覆盖已填）+附件复制进草稿（`POST /api/user-drafts/{id}/copy-template-attachments`，同名跳过、源缺失跳过）；列表/菜单条目显示主题与附件数徽标。AI `apply_template` 同步：参数主题优先，缺省用模板主题，附件复制进 AI 草稿并回 hint
- 前端：DraftsHubPage「批准并发送」同样先 precheck 弹卡；openapi.json + schema.d.ts 重新生成；SettingsPage「写信」区加「发送前 AI 审查」开关（设置模型 ai_send_review 四处齐）
- 测试：test_precheck.py 新 7 例（规则层全模式含方括号白名单/X 边界/附件三态 + precheck 端点 + 模板整链路 KV/落盘/复制/删除清理 + scheduler 定时拦截退回 + 通知）；test_ai_tools_b6.py 扩 apply_template 主题附件 2 例；全量 302 绿；ruff 通过；隔离实例冒烟：precheck 三 blocker 直出、模板未保存上传 404 语义、上传→KV 元数据→复制进草稿、加附件后 attachment_missing 消失、设置开关读写，全对
- 会话：S-0921-1200-发送前检查与模板升级

## 41bab39 — release: v0.4.5 + tag
- 收录：uvx 体验优先三件套（b64aa62——图标指向 uvx 命令 §2.1、空闲 90s 自动退出 §7、首跑横幅 §7.2）；winget PR microsoft/winget-pkgs#436892
- 验证：PyPI `nmail-app`/`nmail-cli` 0.4.5 ✅；Release 六资产齐 ✅；**Release body「Full Changelog」恰好 1 行**——上一条 4b86cd7 的 create-release 前置 job 在真实发版中生效（对比 0.4.3 的 5 行）✅；tap Formula/Cask 0.4.5 ✅；官网联动重建 ✅
- macOS 真机全链路实测：`uvx --from nmail-app nmail install-shortcut` 装图标（server 脚本=uvx 绝对路径 + `--idle-exit`）→ `open -a Nmail` 点图标 → 浏览器开标签 → 0.4.5 服务就绪；顺带把本机常驻的 0.4.3 旧实例经 `/api/quit` 优雅升级。Windows 真机（.vbs 无窗口/多击多开/空闲退出）待用户双机验证
- 会话：S-0918-1335-idle退出与图标重构（续）

## b64aa62 — feat: uvx 体验优先——图标指向 uvx 命令 + 空闲自动退出 + 首跑横幅
- 用户拍板（WIND_DOWN_PLAN 决策 7）：**点图标=开标签页，关标签页=后台自己退，图标永远最新版**；冻结 Windows 图标旧路径疑难等桌面集成投入
- 图标启动器重构（desktop.py，UPDATE_AND_DESKTOP.md §2.1）：uvx 渠道图标指向 `uvx --from nmail-app nmail --idle-exit` 命令（uvx 绝对路径安装时 `shutil.which`+常见位置定死）——不再指向 uv 缓存环境，升级/`uv cache prune` 不死链（**Windows「点击无反应」的根因**），每次双击自动最新版。Windows 形态 .lnk→wscript 跑 UTF-16 带 BOM 的 .vbs（`Run …, 0, False` 全程无窗口）；macOS 存根 .app 的 server 脚本与 Linux wrapper 改跑 uvx 命令，reopen/单实例探测（多击多开标签）机制不变；pip/binary 渠道维持原方案仅补 `--idle-exit`
- 空闲自动退出（core/idle_exit.py 新模块 + cli `--idle-exit` + main.py 中间件/看门狗，§7）：活动信号=HTTP 请求（前端常驻轮询即心跳，无需长连接）；ASGI 中间件请求全程计数（AI 长流式在途不误杀）；lifespan watchdog 每 tick 重读 `idle_exit_enabled` 设置项（设置页开关即时生效），无在途请求且空闲超阈值 → 注入钩子置 uvicorn `should_exit` 优雅退出（cli 改 `uvicorn.Server` 对象形态，等价）。阈值 90s 非 60s——浏览器后台标签定时器节流最低 1 次/分钟，恰好 60s 会误杀还开着的标签；关标签后约 1.5 分钟退出。**终端裸跑 `nmail` 无 flag 恒不退**（总管家/CLI/自动化零影响）。推翻 §6「关标签不退服」旧决策（仅图标启动范围）；「退出 Nmail」卡片保留
- 首跑横幅（§7.2，用户拍板弹出一次即可）：未装图标首次打开页面底部浮出「把 Nmail 放到桌面」引导（立即安装/关闭），**显示即记**（KV `desktop_banner_seen`，POST `/api/desktop-shortcut/banner-seen`）——错过不纠缠；GET desktop-shortcut 附 `banner` 布尔
- 设置页：桌面图标卡片加「空闲自动退出」开关；DesktopBanner 组件挂 App 级
- 测试：test_idle_exit.py 新 4 例（模式折算/活动记账/watchdog 触发/provider 门控）+ test_channel_desktop 扩 3 例（uvx 启动目标/缺 uvx 回退/VBS 引号转义）；全量 291 绿；ruff 通过；隔离实例三轮冒烟（裸 flag 短阈值 ×2 + uvx 真环境 wheel）：看门狗武装→优雅退出→日志留痕全对
- 文档四处同步：INSTALL.md（图标一条命令/空闲退出/升级口径改实测紧跟新版+`--refresh` 兜底）｜ README 双语 ｜ 官网 download.astro ｜ 代码文案；另更 UPDATE_AND_DESKTOP §1/§2/§2.1/§6/§7、ARCHITECTURE（core/api 行 + 收尾注记）、WIND_DOWN_PLAN 决策 7
- 会话：S-0918-1335-idle退出与图标重构

## 4b86cd7 — fix: GitHub Release 说明「Full Changelog」重复——发版工作流只生成一次
- 用户截图官网更新日志页：v0.4.3 说明区连排 5 行 `**Full Changelog**: compare 链接`。根因不在站点——Release body 本身就重复：release.yml 三个 matrix 上传步骤各自带 `generate_release_notes: true`，对已存在的 Release 每更新一次 GitHub 就把新生成说明追加进 body（0.4.3 期间失败重跑又追加，共 5 遍；0.4.4 两遍）；官网 changelog.astro 以 `<pre>` 原样展示
- 修复两层：①release.yml 新增 create-release 前置 job（`gh release create --generate-notes`，幂等——已存在即跳过），binaries `needs` 它且上传步骤一律去掉 generate_release_notes；②官网 lib/releases.ts 构建期 `cleanBody` 整行剔除 `**Full Changelog**` 并压掉多余空行（卡片头部本就有「在 GitHub 查看」链接，信息不丢）
- 存量修复：v0.4.3 / v0.4.4 的 release body 已按保留一行去重（gh api PATCH），GitHub 页与官网重建后同步干净
- 会话：S-0918-1150-更新日志去重

## a3ece50 — release: v0.4.4 + tag
- 收录：Windows 启动崩溃修复（4c282b8，`raise_nofile_limit` 平台保护）——**本版恢复 Windows 全渠道可用**（0.4.3 带病、0.4.2 及更早正常）
- CI 波折同 0.4.3：macOS 资产「附加到 GitHub Release」撞 GitHub 瞬时 Unicorn HTML 错误页 → `gh run rerun --failed` 重跑即绿；脚本中断的 winget/官网两步手工补做
- 验证：PyPI `nmail-app`/`nmail-cli` 0.4.4 ✅；Release 六资产齐 ✅；tap Formula/Cask 0.4.4 ✅；winget PR microsoft/winget-pkgs#436770（fork master 同步照旧 422=gh token 缺 workflow scope，容忍）；带病的 0.4.3 PR #436602 已关闭并留评指向 #436770；官网联动重建已触发
- 会话：S-0918-0007-Windows-resource（续）

## 4c282b8 — fix: Windows 启动即崩——raise_nofile_limit 平台保护（resource 模块 POSIX 专属）
- 用户 Windows 机 `uvx --from nmail-app nmail` 装包成功但启动即 `ModuleNotFoundError: No module named 'resource'`——43e959f 的 fd 抬限修复在 cli.py 无条件 `import resource`，该模块 POSIX 专属，Windows 全渠道（uvx/pip/冻结 exe）启动即崩，v0.4.3 带病发布
- 修复：`raise_nofile_limit` 开头 `sys.platform == "win32"` 直接返回 None（Windows 无 fd 软上限概念、无 Errno 24 风险，抬限本就不适用），调用处按 None 跳过 fd 日志回显；macOS/Linux 行为不变
- v0.4.2 及更早无此代码不受影响；应急口径 `uvx --from nmail-app==0.4.2 nmail`。PyPI/资产恢复待下一补丁版发布
- 会话：S-0918-0007-Windows-resource

## f3eca4f — release: v0.4.3 + tag
- 收录：后端 fd 水位治理（43e959f）、macOS .app Dock reopen（099f355）、Windows uv 命令补齐（302bf07）与官网口径对齐
- ⚠️ **本版 Windows 全渠道启动即崩**（43e959f 的 `import resource` POSIX 专属，见 4c282b8）——用户真机实测撞上，修复已入库、待 0.4.4 补丁版发布；macOS/Linux 不受影响。winget PR #436602 暂不可用，0.4.4 发出后对 PR 分支追加提交或重开
- release.sh 盯 CI 中断，后续步骤手工补做。CI 两处波折：①「附加到 GitHub Release」macOS/Windows 两腿撞 GitHub 瞬时 HTML 错误页（softprops 收到非 JSON 响应）→ `gh run rerun --failed` 重跑即绿；②homebrew-tap 新增的 cask 步骤引用仓库模板 `scripts/cask_template.rb`，但该 job 设计上无 checkout → 必挂 `sed: No such file`（根因修复 db4ee8b 补 checkout），本轮手工经 GitHub API 渲染创建 `Casks/nmail.rb`（0.4.3 + dmg SHA256）兜底
- 验证：PyPI `nmail-app`/`nmail-cli` 0.4.3 ✅；Release 六资产齐（exe/Windows zip/dmg/app.zip/macos/linux）✅；tap Formula 0.4.3 ✅ + Cask 0.4.3 ✅；winget PR microsoft/winget-pkgs#436602（fork master 同步 422=gh token 缺 workflow scope，上游新增 workflow 文件所致，与 v0.4.2 同、按脚本口径容忍）；官网联动重建已触发
- 会话：S-0917-2352-发版0.4.3

## 099f355 — fix: macOS .app 运行中再点 Dock 图标重开页面（补 reopen 处理）
- 用户反馈：关掉浏览器标签后（服务按设计驻留后台），再点 Dock 图标亮白点却无响应——根因是 macOS 对已运行应用不二次启动进程、只发 reopen 事件，而存根（scripts/nmail_stub.m）只实现了退出，未实现 `applicationShouldHandleReopen`，点击落空
- 修复：存根补 reopen 处理，用默认浏览器重开页面；实际绑定地址由 cli 写入——bundle server 脚本经 `NMAIL_URL_FILE` 环境变量告知约定文件（`Contents/MacOS/url`），cli 起服时写入（8720 被占顺延也正确），存根读取后 `/usr/bin/open <url>`，文件缺失兜底 8720。Win/Linux 图标再点即起新进程走既有单实例探测，无需改动
- 存根重编译通用二进制（cc arm64+x86_64）；ruff 通过；重装 wheel + 重新生成 /Applications/Nmail.app 实测：冷启动写 url 文件、运行中 `open -a Nmail` 触发重开
- 会话：S-0917-2314-dock-reopen

## 302bf07 — docs: Windows uv 安装命令补 powershell 前缀
- 各文档 Windows 口径原为裸 `irm https://astral.sh/uv/install.ps1 | iex`，仅在已打开的 PowerShell 会话内可运行（cmd / Win+R 直接执行会报错，且可能被 ExecutionPolicy 拦截）；补齐官方完整写法 `powershell -ExecutionPolicy ByPass -c "irm … | iex"`。四处同步：README 双语、docs/INSTALL.md 方式④、官网 download.astro（正文与复制按钮 data-copy 一并改，引号转 `&quot;`）；/docs/install 走构建期同步
- 会话：S-0917-2257-Windows uv 命令补前缀

## 1a02a35 — docs: README 双语与 INSTALL.md 补 uv 官方一键安装命令
- 此前仅给 docs.astral.sh 安装文档外链，用户需自行跳转找命令；现补官方安装器命令——macOS/Linux `curl -LsSf https://astral.sh/uv/install.sh | sh`、Windows（PowerShell）`irm https://astral.sh/uv/install.ps1 | iex`，并注明装完重开终端生效
- 四处口径核对：README 双语（「一分钟上手 / Up and running」节）+ docs/INSTALL.md 方式④ 补命令；官网下载页 download.astro 本就有两条命令未动；官网 /docs/install 构建时从主仓同步（本地构建已验证含命令），随下次官网部署上线
- 会话：S-0917-2230-uv安装命令补齐

## 4706904 — fix: 换行语义全局统一——单换行=分段（Enter），行尾两空格=紧贴（Shift+Enter）
- 用户拍板：模板/签名/AI 起草的文本源与编辑器键位语义全面对齐——单个换行一律=分段 <p>（与编辑器 Enter 一致）；紧贴换行（Shift+Enter 语义）用 Markdown 硬换行表达（行尾 ≥2 空格或反斜杠）。取代 B2 的 nl2br（单换行=<br> 曾致「模板插入后 Enter 变 Shift+Enter」的观感，实测确认）
- 实现：`mail_html._enter_to_paragraph` 预处理器——单换行改双换行走 Markdown 分段；行尾 ≥2 空格/反斜杠保留硬换行；围栏代码块内逐字保留；列表/引用/标题/表格行相邻换行不拆（块结构依赖行相邻）；非结构行 ≥4 空格缩进转私有区占位符（防分段后落入缩进代码块 + markdown 吞行首 nbsp），转出 HTML 后还原为 nbsp（缩进收发两端一致显示）；`_normalize_md_html` 保留（硬换行 br 后字面 \n 删除）
- 前端仅模板编辑框占位文案更新（写明新约定）；编辑器打字/粘贴路径本就段落语义，零改动
- 数据迁移：用户签名行尾单空格→双空格（保留签名紧贴排版意图，API 一次性完成）
- 测试：test_mail_html 更新 4 例+新增硬换行 1 例，全套 282 绿；ruff+build 通过；e2e 实测：真实模板插入=逐行段落+缩进保留、签名插入=紧贴行+中英文间分段
- 会话：S-0917-2210-fd泄漏排查（续篇：换行语义统一）

## 43e959f — fix: 后端 fd 水位治理——启动抬 fd 软上限 + 调度 tick 回收死线程连接
- 排查（playwright 驱动+隔离实例+真库副本压测+get_conn 创建点追踪）：泄漏实例 20:44→21:30 fd 打满 **256**（launchd GUI 会话 maxfiles soft=256）→ accept Errno 24 + sqlite 打不开，整机瘫痪只能重启。机制＝anyio 工作线程按负载起停（闲置 10s 退役），每个碰库工作线程持有 sqlite 连接（db+wal 句柄各 1），请求爆发期（写信台压测 16 分钟+前端 30s/60s 轮询+同步/总管家高频操作）连接水位堆高、GC 兜底回收滞后数分钟；连接最终会自愈（live 实测 40→6 回落），非单调泄漏，但 256 低上限下水位触顶即瘫痪
- 修复三件：①`cli.raise_nofile_limit()` 启动即把软上限抬到 min(hard, 10240)（hard unlimited），启动日志回显便于核验 ②`database.reap_dead_thread_conns()` 连接登记表+调度 tick（60s）显式关闭已死线程遗留连接，把 fd 水位钉在活跃线程数 ③原 `close_thread_conn` 语义不变；IMAP/SMTP/LLM 客户端生命周期逐一核对均为 with/finally，无泄漏
- 测试：test_database +3（死线程回收/活线程保留/软上限抬升），全套 281 绿；ruff 通过；.app 重装重启后日志回显 `fd soft limit: 10240 (hard …)`，前端 / 正常服务（重装前须先 `cp -r frontend/dist backend/app/static`——wheel 前端来源，缺了即「前端未构建」，本会话踩坑一次）
- 排查工具留档 /tmp/nmail-fdleak（workload 分组压测、dbgserver get_conn 追踪、monitor.sh fd 监控）；e2e playwright 直连后端+Origin 头改写可绕 vite 代理 ECONNRESET（见记忆 nmail-macos-env）
- 会话：S-0917-2210-fd泄漏排查

## 7f40bac — fix: 写信所见即所发——Markdown 转换产物空白规范化（删 br 后字面换行 + 缩进转 nbsp）
- 用户反馈两个症状实机复现并根因定位：①模板/签名/AI 内容插入编辑器后「单换行变空行」②发送后「换行和空格被吞」。总根因是**两套空白口径不一致**：编辑器（ProseMirror）以 `break-spaces` 渲染（字面 `\n` 显示为换行、空格全保留），收件端 HTML 恒为 `normal`（`\n` 与连续空格折叠）；而 python-markdown 的 nl2br 输出 `<br />\n` 携带字面换行进编辑器文档——同一段内容编辑器显示空行+缩进、收件人看到紧凑无缩进（B2 修复前则是无 br 时字面 `\n` 被编辑器显示、收件端折叠成「换行被吞」）
- 修复（单一收口）：`mail_html._normalize_md_html` 在 `markdown_body_html`/`markdown_to_email_html` 两路统一规范化——①删 `<br>` 后字面 `\n`（收件端永远折叠，编辑器不该显示）②`<br>`/`<p>` 后行首空格串转 U+00A0（任何客户端不折叠，中文书信缩进收发两端一致显示）；`<pre>` 代码块内换行缩进是语义，不受影响；`html_to_plain_text` 把 U+00A0 还原为普通空格（text/plain 同步保真，原 f561783 的 br-换行吞除逻辑保留作防御）
- 测试：test_mail_html 新增 4 例（br 后无字面换行/缩进转 nbsp/pre 不受影响/纯文本 nbsp 还原），全套 278 绿；ruff 通过
- 端到端验证（真实用户模板「关于咨询课题组组会旁听…」注入编辑器实测）：插入后文档无字面 `\n`、缩进以 nbsp 存活于 ProseMirror 文档（getHTML 带 `&nbsp;`）；编辑器渲染与真实发送管线（消毒→内联化→wrap）输出并排对比完全一致
- 附带发现（未修，另开跟进）：后端进程 fd 泄漏——运行约 46 分钟后 `accept: [Errno 24] Too many open files` + sqlite 打不开（nmail.log 21:30 起 138 条），重启恢复；泄漏源需挂 fd 计数排查（疑 IMAP/同步连接未关）
- 会话：S-0917-2145-写信所见即所发

## ec5a85d — docs: README 中英主次对调——中文成为主 README，顶部补语言切换行
- 用户指出重写时漏了语言切换行、且文档以中文为主：README.md ↔ README.zh-CN.md 内容对调——**中文版成为主 README**（GitHub/PyPI 默认展示中文），英文版移至 README.zh-CN.md；两份顶部补「中文 ｜ English」互链
- docs/INSTALL.md（方式⑤、源码开发两处）与 docs/README.md 索引的 `../README.zh-CN.md` 引用跟改为 `../README.md`；官网 sync-docs 的 EXTRA_LINKS 本就同时映射两文件名，构建自动跟上
- 注意：PyPI 项目页自下次发布起长描述展示中文 README（pyproject `readme = "README.md"`），无需改打包
- 会话：S-0917-1620-文档补齐与README重写（补记）

## 644a694 — docs: 对外文档补齐——README 重写（uvx 唯一安装入口）+ docs 索引 + 演示截图入库
- README 双语重写为「产品门面」（用户要求第一眼吸引）：居中 hero（logo + Release/PyPI/License/平台徽章 + 主截图）、六卖点清单、「眼见为实」双截图（总管家/每日摘要）、GIF 折叠演示块、文档索引表、隐私摘要、开发折叠块；安装章节只保留 uvx 一条命令 + uv 官方安装器，单文件/winget/Homebrew/pip/源码改为指向 docs/INSTALL.md——**命令与渠道说明本身零改动**（INSTALL.md / 官网下载页 / 代码内文案三处不动，四处口径一致）
- docs/README.md 新增：docs/ 目录对外索引（上手/了解/进阶/开发者四组；自建 OAuth 教程等此前无入口的文档纳入）；内部工作文档（REDESIGN_PLAN/SESSIONS 等）文末注明不面向用户
- assets/promo/ 入库三张脱敏演示截图（收件箱/总管家/每日摘要，取自 promo/pictures 素材池；设置页截图因含「AI 晨报」旧文案弃用）+ nmail-logo-160.png（icon-master 缩 160px，README 用）
- 官网 nmail-site 同步（独立仓提交）：首页新增主截图与双截图区、功能页修「与自动化」残缺标题并补三图速览、全站「AI 晨报」→「AI 摘要」更名跟上（首页特性卡/功能页/projects 卡；历史动态帖按惯例不改写）、功能页文档入口改站内 /docs/
- 会话：S-0917-1620-文档补齐与README重写
- 补记（be1da79）：用户反馈首屏大图应为 GIF 动图而非静态截图——两份 README 首屏改用 assets/Nmail-demo.gif，静态收件箱截图挪至「眼见为实」区；顺带修复 INSTALL.md 方式⑤/源码开发两处指向旧 README 锚点（#快速开始/#开发模式）的失效链接

## d6311cc — feat: 晨报合一——「AI 摘要」更名 + 综述废除 + 生成三路径（用户拍板）
- 用户指出 AI 晨报与每日摘要概念冗余，拍板三合一：①「AI 晨报」更名**「AI 摘要」**全量同步（界面/设置/文档/通知文案；KV 键与 `agent_brief` 存储键不动，零迁移；CHANGELOG 历史条目与各 PLAN 落地记录不改写，REDESIGN_PLAN §18.6 以带日期增补记录）②**AI 综述废除**——内容贫乏（只看统计数字写 3-5 句）且信息量被统计卡/列表覆盖：`build_digest` 变纯统计零 LLM、`tasks.digest_overview` 删除，每天省一次 LLM 调用；调查确认的两个覆盖 bug（综述/晨报互相抹掉）随综述废除+统计重建保留同日正文而根除
- **生成三路径**（产出同一份 AI 摘要）：定时（原样，开关开启时 digest_time 触发）＋ 摘要页「生成 AI 摘要/重新生成」——`POST /api/digest/generate` 改异步触发（180s 预算不占 HTTP），GET /api/digest 增 `brief_running` 供前端轮询+按钮态，未配置 AI 400、运行中 409 ＋ 总管家对话新工具 `save_brief`（write/organize 级本地写，巡箱后正文落库、不发通知——对话场景用户在场）
- 调度收敛：定时/手动共用 `scheduler.start_daily_brief(origin)` 入口（进程内互斥锁+运行标志，重启自清无 KV 残留）；触发即盖 `agent_brief_last_run`——手动跑过当天定时不再重跑（手动不受限）；统计重建保留同日已存正文与✕清除记录（晚间重跑崩溃回退不抹晨间正文）
- 前端：摘要页综述区块删除、晨报区块更名「AI 摘要」，按钮异步化（生成中轮询/禁用/提示条），导出 Markdown 单正文段；设置项文案改「AI 摘要：到点由总管家巡箱总结并拟稿…关闭则仅统计摘要」
- 测试：test_digest 跟改+新增统计重建保留正文用例；全套 276 绿；ruff 通过；npm build（tsc）通过；openapi.json/schema.d.ts 同提交
- 真实实例 e2e：8720 重启后 POST /generate 实跑两轮——首轮模型端点第 6 步挂起超时→按设计干净失败回退统计摘要+正确通知；二轮 done（7 步/86.6s），767 字正文（含真实账号 np25 概况）落库、GET 返回 agent_brief、brief_running 全程正确翻转
- 会话：S-0917-1458-晨报合一改名AI摘要

## 4fcc533 — refactor: 移除 A2 完成断言门，改为写类失败事实回执（相信模型拍板）
- 用户拍板「不需要正则匹配、相信模型智力」：A2 用 9 组断言正则猜最终回答里的完成声称再比对执行记录，语义猜测结构性误伤（Sent 文件夹中文名「已发送」撞断言词，纯查询被误拦、纠正回灌还引出模型防御性澄清；此前 9d8c217 只修了名词性一种）——整体移除断言正则、纠正回灌、系统注记与 `_attempted_tools`
- 替代为**确定性失败回执**：写类工具真实执行失败（含审批批准后执行失败）时，由代码在最终回答末尾附「（注：本轮有 N 项操作未成功，详情见「设置-AI 用量-操作历史」。）」——零语义猜测、零误伤、无失败零附加；模型怎么转述都盖不住这行事实。`_RUN_FAILED_WRITES` 按 run 计数（审批经 `_ACTION_RUN` 归属），run 终态即回收；权限/参数被拒与用户拒绝审批不算失败（未执行或有意改道）
- 测试：删 4 个 A2 断言门用例，新增失败回执（auto 模式写失败→回执附加+终态回收）与只读 run 零回执 2 例；全套 274 绿
- 文档：ARCHITECTURE agent 行、REDESIGN_PLAN §20.2 A2 条目改记移除与替代
- 会话：S-0917-1520-A2移除与失败回执

## 964886b — fix: AI 用量「操作记录」清理三处问题——失败卡死/静默无反馈/下拉语义
- 失败卡死：清理请求失败时下拉不复位，重选同一项不再触发 onChange，该清理项从此点不动——改为选择即复位，失败/取消后可立即重试
- 静默无反馈：成功与失败均无提示——补「已删 N 条记录」/「清理失败：…」内联反馈，请求进行中禁用下拉
- 下拉语义：占位项「清理…」可被选中且勾标停在占位上（用户误以为菜单坏了）——占位项 disabled+hidden，弹层只见三个清理动作
- 会话：S-0917-1505-操作记录清理修复

## 0af93e9 — UI: 设置页文案瘦身——长说明挪进使用指南，界面回归简约
- 设置页遵循「界面简约、细节进文档」：AI 配置区总开关与多套配置说明各压成一行（多套配置举例、「对话界面可临时切换」等细节挪文档）；AI 晨报、外部图片、网络代理、本机数据四处长句同步精简
- 使用指南新增「AI 配置档案」节：多套端点组合示例（DeepSeek 快速/强模型写草稿/本地 Ollama）、「使用中」全局默认 + 对话界面临时切换（2 套以上配置时显示下拉）、云端/本地端点隐私边界、AI 总开关关闭后的完整行为
- 会话：S-0917-1453-设置页文案瘦身

## 9d8c217 — fix: A2 完成断言门对名词性「已发送」的误报——纯查询回答不再附系统注记
- 用户实测：总管家列文件夹清单/查已发送邮件后，回答末尾出现「系统注记：…没有对应的执行记录」且模型防御性补充「我没有执行修改操作」——Sent 文件夹中文名即「已发送」，与 A2 断言词撞车：误判 → 回灌纠正 → 模型防御性澄清 → 二次仍命中 → 注记，纯查询回合全程被误伤
- 修复：`_completion_mismatch` 比对前经 `_NOUN_SENT_RE` 摘除名词性用法（「已发送文件夹/箱/夹/里/中/列表/记录/的」前缀短语与「（已发送）」括注），真断言（「邮件已发送」「已发送给/邮件给…」）不受影响；取舍：不摘「已发送邮件」连写以防「已发送邮件给某人」断言漏拦，列表句式用「已发送的邮件」即不误伤
- 测试：新增 test_completion_mismatch_sent_folder_noun_not_flagged（四种名词句式不拦 + 两种真断言仍拦），全套 269 绿
- 会话：S-0917-1448-A2完成断言误报

## f5bd1d9 — fix: 总管家空响应兜底 + agent 单步生成上限 2000→8192
- 会话 36 实测 400「Invalid 'messages[50].tool_calls': empty array」（run 52）：deepseek 思考 token 单独耗尽 agent 单步 max_tokens=2000（ai_logs completion_tokens 恰为 2000），流结束时无文本无调用分片，`_append_assistant_calls` 照常落库 `{"role":"assistant","content":"","tool_calls":[]}`，下一步请求被 OpenAI 兼容端点校验（tool_calls minItems 1）拒绝，run 标记 failed
- 修复三层：① `AGENT_MAX_TOKENS=8192` 覆盖 agent 全部模型调用（主步/JSON 降级/触顶收尾）——思考 token 同样计入额度，2000 对推理模型必触顶 ② `_loop` 空响应兜底：无文本无调用时回灌「（系统提示：上一次响应为空…请继续任务）」重试（限 2 次），仍空则友好报错终止，绝不落空 tool_calls 消息 ③ `_append_assistant_calls` native 分支 calls 为空时不写 `tool_calls` 键（防御）
- 测试：test_agent_loop.py 新增 2 例（空响应重试→报错全链路、空 calls 不落键）；test_agent.py 打桩签名补 max_tokens 透传适配
- 会话：S-0917-1446-总管家空响应修复

## 54fe4ec — fix: 「AI 整理」中间进度上报 + 僵尸任务启动清理 + 跨年日期显示修复
- 用户两反馈：①「AI 整理」进度全程显示 0%（单账号场景 `organize_job` 只在整账号跑完后报一次进度，LLM 批次与归档移动期间恒 0）②跨年邮件日期渲染成「2025年 (日: 22日)」
- 进度：`classify_missing` 加 `on_progress` 回调（每个 LLM 批次报「分类 n/N」、归档阶段报「归档移动中」），`organize_job` 折算总进度 =（已完成账号 + 当前账号批次占比）/账号数，运行中 0.99 封顶防假 100%；多账号明细带「账号 i/n · 」前缀
- 僵尸任务：jobs 线程只活在本进程内，重启后遗留 running 行必为孤儿——启动时 `jobs.reap_orphans()` 统一标记 failed（「进程重启，任务中断」）；不清理则 dedupe 会静默复用僵尸行，「AI 整理」点了没反应、进度永挂
- 前端：`JobProgressBar` 进度为 0 时文本显示「AI 整理…」而非「AI 整理 0%」；`shortDate` 跨年分支恒传 month（zh-CN 对「年+日无月」字段组合走 CLDR 特殊格式「y年 (日: d日)」），跨年显示为「2025/9/22」
- 会话：S-0917-1432-进度与日期显示修复

## 6c11f17 — fix: 通知中心时间改按系统时区显示（原为裸 UTC 串）
- 用户反馈通知时间比系统慢 8 小时；根因：`notifications.created_at` 由 SQLite `datetime('now')` 默认值落库（恒为 UTC），API 原样透传、前端原样渲染字符串，全程无时区转换（邮件列表走了 formatDate 所以一直正确，仅通知中心漏了这层）
- 架构保持「存 UTC、显示本地」：`/api/notifications` 出口 `_to_local_iso()` 把 UTC 裸串转系统时区带偏移 ISO（存量行同样覆盖，无需迁移）；前端 NotificationBell 改用共用 `formatDate` 渲染；依赖 UTC 存储做边界比较的 scheduler 定时逻辑不动
- 未来自定义时区：`_to_local_iso()` 单点把系统时区换成设置项即可
- 验证：ruff 通过；npm build（tsc）通过；隔离实例 curl 实测 created_at 输出本地时区 ISO；8720 重启后 /api/health 通过
- 会话：S-0917-1401-通知时区（暂存窗口被并行 docs 提交扫入，随 6c11f17 入库）

## fe808f1 — B1 修正: v27 迁移为存量账号初始化回补锚点 + 运行态兜底（EXPERIENCE_PLAN）
- 真机验证发现：v26 只给存量 sync_state 行加列（backfill_uid=NULL），回补线程把「锚点 NULL」误判为无需回补直接标 done——老账号 30 天之前的历史永不回补
- v27 迁移：存量行锚点初始化为本地该文件夹 MIN(uid)（从真正缺口开始补，重叠段 INSERT OR IGNORE 去重）；无本地邮件的行回退 last_uid；回补线程 `_backfill_folder_pass` 加同场景运行态兜底（锚点缺失从 last_uid 起步，绝不静默标完成）
- 测试：新增 test_backfill_migration.py 2 例（直接执行 MIGRATIONS v27 原句 SQL 验证锚点语义与已完成行不回退）
- 真机验证：清华账号升级后 INBOX 从 30 天扩到整年（2025-09-14 起 307 封）、Sent 103 封、Trash/Archived 全部补齐，断点/进度/完成态全部符合预期
- 会话：S-0917-1252-体验优化

## 79d1988 — B1: 全量同步——首翻最新一页立即可用 + 后台回补全部文件夹全部历史（EXPERIENCE_PLAN）
- 用户反馈清华邮箱只见最近 30 天；根因为 `FIRST_SYNC_DAYS=30` 首同步窗口且全项目无历史回补（客户端设计限制，非服务器限制）
- 去掉 30 天窗口：首同步只拉最新一页（25 封）立即可用；新迁移 v26 给 `sync_state` 加 `backfill_uid`（回补断点）+ `backfill_done` 列
- 新增独立回补线程（`maybe_start_backfill` → `_backfill_worker` → `_backfill_folder_pass`）：LIST 枚举全部服务器文件夹（排除 Gmail All Mail）+ 为每个文件夹确保 sync_state 行，从新到旧分页（25 封/页 × 80 页/趟，趟间重连换气）补齐全部历史；断点逐页落库，中断/重启/断连自动续传；INBOX 优先
- 回补邮件**不进 AI 流水线、不发通知、不采通讯录**（防上万封跑 AI 与通知轰炸）；存量账号迁移后下次轮询自动开始回补
- `iter_new_mail` 收敛为纯增量（`UID last_uid+1:*`）；抽出 `fetch_uids_parsed` 共用稠密区间/稀疏逐 UID 拉取逻辑；`folders.upsert_listing` 从 refresh_cache 抽出共用
- 修复隐患：首同步分支补 `mb.folder.set(folder)`（原逻辑藏在 iter_new_mail 内，拆分时显式化）
- 测试：新增 test_backfill.py 6 例（首翻页/小文件夹即齐/一趟补完/断点续传两趟/INBOX 优先/增量不受影响）；v26 迁移幂等断言更新
- 验证：ruff 通过；pytest 256 全绿；临时数据目录启动冒烟 /api/health 通过；真机全量回补待用户实例升级后观察
- 会话：S-0917-1252-体验优化

## f120525 — B3: 附件预览——图片/PDF/文本弹层预览，其余类型保持下载（EXPERIENCE_PLAN）
- 用户拍板范围：图片、PDF、文本预览；其余下载。PRODUCT_PLAN 既定项（「图片和 PDF 预览」）落地
- 后端 `/api/attachments/{id}/download` 加 `?inline=1`：mime 白名单（image/* 非 svg、application/pdf、text/*）才返回 inline disposition，其余强制 attachment；统一加 `X-Content-Type-Options: nosniff`；HTML/SVG 附件可携带同源脚本，永不 inline
- 前端新增 AttachmentPreview 弹层：图片 `<img>` 直接渲染；PDF `<iframe>` 浏览器内置 viewer；文本 fetch 后 `<pre>`（>1MB 提示下载）；EmailReader 附件片可预览类型改为按钮打开弹层（带「预览」角标），不可预览类型保持原下载链接；弹层内仍可一键下载
- 验证：npm build（tsc）通过；后端 ruff 通过
- 会话：S-0917-1252-体验优化

## 1e37818 — B2: Markdown 转换开启 nl2br——模板/签名/AI 起草的单换行不再丢失（EXPERIENCE_PLAN）
- 用户反馈「换行发出去就没了」，场景确认为模板/签名插入后；根因：`markdown_body_html`/`markdown_to_email_html` 未开 nl2br 扩展，单个换行被折叠为空格（编辑器直接打字不受影响，Enter 本就生成段落）
- 两处转换函数 extensions 加 `nl2br`：波及模板插入、签名插入（含自动签名）、AI 起草（create_draft/update_draft）、编辑器 markdown 粘贴——单换行一律保留为 `<br>`，空行分段不变
- 前端 Markdown 组件（AI 聊天气泡/晨报渲染）加 remark-breaks，站内渲染口径一致
- 测试：test_mail_html.py 新增 nl2br 用例（单换行→`<br />`、空行仍分段）
- 验证：pytest 27/27（mail_html）通过；ruff 通过；npm build 通过；运行实例 `/compose-extras/markdown` 实测往返
- 会话：S-0917-1252-体验优化

## 237b677 — B6: AI 总管家人人对等扩充——模板/签名/联系组/受限设置/立即收信（EXPERIENCE_PLAN）
- 用户拍板「评估开放的所有都给 AI，不直接开放的出审批卡」。新增 8 工具（tools.py 注册 + 参数表 + 结果摘要 + 前端 TOOL_LABELS 中文名）：
  - 读类：`list_templates`（模板名+内容）、`list_signatures`（各账号签名）、`list_contact_groups`（联系组）
  - 写类 organize（自动模式可执行）：`apply_signature`（幂等补签名）、`manage_contact_group`（create/rename/delete/add_members/remove_members，成员须先在通讯录）、`set_settings`（白名单键：desktop_notifications_enabled / auto_insert_signature / contacts_auto_collect / poll_interval_minutes(1..120) / notify_types 子键合并）、`trigger_sync`（后台增量同步）
  - 写类 draft：`apply_template`（模板内容+可选补充段 → create_draft 同一落地路径 → 待审）
- 高风险设置键强制审批（自动模式也降审批，`_approval_reason` 硬规则）：`agent_brief_enabled` / `digest_time` / `allow_remote_images` / `read_email_max_chars`（读信截断改为可调设置，默认 3000，上限 20000）
- AI 信补签名：`outbox.send_user_draft` 对 origin='ai' 草稿在用户开启 auto_insert_signature 时自动追加该账号默认签名（幂等，正文已含同款跳过）；修 prompts.py「结尾不签名（系统会自动处理）」失真说明
- 白名单外设置键一律拒绝（§17.3 豁免不动摇：secrets/授权位/账号凭据/API key/HTTP·命令执行依旧不提供）
- 测试：新增 test_ai_tools_b6.py 9 例（模板套用落待审/签名幂等/联系组全生命周期/设置白名单与校验/高风险强制审批/trigger_sync 派发/outbox 签名幂等）
- 验证：pytest 265 全绿；ruff/npm build 通过
- 会话：S-0917-1252-体验优化

## d23ba30 — B4: Tab keep-alive——五个页面常驻挂载，切页签只显隐（EXPERIENCE_PLAN）
- 用户反馈切 tab 后滚动/筛选/打开的邮件/聊天记录全回初始态。根因：路由切换=页面组件整体卸载，状态全在组件内 useState（唯一 keep-alive 是写信台）
- Layout 改为五个页面（邮件/草稿/每日摘要/AI 总管家/设置）常驻挂载：首次到访才挂载，切页签只 `visibility` 显隐（布局与滚动位置保留、不进焦点序与无障碍树）；`?focus=` 深链在常驻化后验证可达；/mydrafts、/archived、未知路径重定向兜底迁入 Layout
- 新增 `usePageActive` 上下文：隐藏页签门控列表轮询（MailBrowser 20s/2s、待审草稿 20s、设置代理状态 3s）与全局键盘监听（MailBrowser 两处 window keydown）——隐藏页签不拉取不响应按键
- AI 总管家切走再回：聊天记录/流式输出保留（组件不再卸载，SSE 流继续在后台跑）
- 验证：npm build 通过；隔离实例 Chrome 实测——切走再切回滚动位置精确保留（292.41px 不变）、五页签 DOM 常驻、`?focus=` 消费正常、控制台无错误
- 会话：S-0917-1252-体验优化

## 086fb29 — B5: 通知修复——只报 INBOX 新邮件/点击直达/晨报纯文本化（EXPERIENCE_PLAN）
- Trash 误报：`sync_account` 汇总通知只统计 INBOX 新邮件（原为本次同步全部文件夹加总，点开树/按需同步垃圾文件夹也弹「新邮件」）；ref_id 从账号 id 改为首封新邮件 email id
- 点击跳转：桌面通知 `onclick` 补 navigate（复用通知面板同款 `targetFor` 类型映射）；新增 new_mail/ai_archive → `/?focus=<email_id>` 直达邮件、compose → /drafts、ai_proposal → /settings；存量「账号 id」ref_id 行点击回落邮件页顶部（可接受）
- 晨报通知纯文本化：Notification API body 平台限制纯文本——scheduler 晨报原文 md→plain 清理（新 `markdown_to_plain_text`）+ 截短 500 字；完整 markdown 排版站内看；通知中心 digest 类型展开时用 Markdown 组件渲染
- ai_archive 通知带清单：`_apply_classification` 返回被归档邮件 {id, subject}，通知正文列前 3 个主题 + 总数，ref_id 改为首个被归档邮件 id（移动后行 id 保留，focus 可达）
- 验证：pytest 265 全绿；ruff/npm build 通过
- 会话：S-0917-1252-体验优化

## 待提交 — fix: 账号删除残留清理补全 + 删光账号序列归零（用户残留审计拍板落地）
- 用户问「删邮箱账号有什么残留 / 为什么 accountID 一直递增」——审计结论：FK 级联（邮件/附件/断点/文件夹/草稿）与密钥/磁盘账号目录已清干净，但无 FK 从属数据全留：ai_logs、ai_actions（动作审计）、jobs、rule_observations、chat_sessions、悬空 notifications（表无 account 字段，ref_id 指向已删账号/邮件）、compose_signatures KV 幽灵签名、磁盘孤儿草稿附件目录
- 账号 id 递增 = SQLite AUTOINCREMENT 永不复用（保护性设计：通知 ref_id/审计/会话引用旧 id，复用会错位）；部分删除维持递增
- 落地（用户三项拍板：审计一并删 / 通讯录保留 / 存量孤儿清）：①delete_account 收尾统一调 cleanup_orphans ②新增启动 GC cleanup_orphans（幂等）：无 FK 从属表按存活账号清理、agent_runs 账号范围全失效才删、notifications 悬空引用清理（ai_draft ref=来源邮件 id、ai_draft_summary ref=账号 id 的映射经代码核实）、KV 幽灵签名剔除、磁盘孤儿 drafts/<id> 目录清理 ③reset_account_sequences_if_empty：删光全部账号后账号域自增序列归零，下次添加从 id=1 起；对仍有行的表重置无害（AUTOINCREMENT 取 max(seq,rowid)+1）④contacts 按拍板保留（删邮箱≠删人脉）
- 测试：新增 test_account_cleanup.py 4 例（全量残留清理+通讯录保留/双账号互不波及/删光归零后新账号 id=1/GC 幂等+磁盘目录清理）
- 真机生效：随下次重启自动清掉存量孤儿（280 条 ai_logs、25 条 ai_actions 等）
- 会话：S-0917-1420-CLI技能同步（追加残留审计轮）

## f561783 — fix: 纯文本派生吃掉 br 后字面换行——修复 text/plain 单换行叠成双换行（skill 真机测试发现）
- nmail skill 全链路真机测试（自发自收回环）暴露：nl2br 产出 `<br />\n`，`html_to_plain_text` 把 br 换成 `\n` 后与标签后字面换行叠加 → 发出邮件的 text/plain alternative（及 AI 读信 body_text）单换行处全变空行；body_html 渲染不受影响
- 修复：br 替换时吃掉紧跟的一个字面换行（bs4 NavigableString）；单换行语义在纯文本侧保住
- 测试：test_mail_html 补回归（md→html→plain 全链恒等校验）；28/28 过
- 真机验证：重装重启后二次自发自收，收到的 text/plain 单换行/分段与原文一致（CRLF 为 SMTP 标准行尾）
- 会话：S-0917-1420-CLI技能同步（skill 全链路测试轮）

## ca2f657 — docs: B6 能力同步进 skill 与指南——总管家通道工具面描述更新
- skills/SKILL.md：「内置总管家通道」补 2026-09 人人对等工具面（邮件/写信含模板签名/通讯录含联系组/受限设置白名单/触发收信），高风险设置项（晨报开关/时间、远程图片、读信截断）**一律返回审批卡、绝不代批**的硬规则写进 agent 决策流程；frontmatter description 补模板/签名/联系组/受限设置触发词
- docs/对外API使用指南.md：agent scope 行同步工具面与高风险键审批约束
- docs/使用指南.md：「AI 能做什么」表补模板与签名/联系组/设置/立即收信四行（B6 遗漏的用户侧文档）
- CLI（nmail-cli）为纯透传：总管家工具由服务端注入，ask/decide/resume 无需改码
- 已安装 skill 副本（~/.claude/skills/nmail）同步为仓库版（此前停在 0.4.1 版本行）
- 会话：S-0917-1420-CLI技能同步

## 76967b1 — UI: 设置页接入文档站入口——侧边栏「使用文档」+ 关于「帮助与文档」卡片，文档链接常量化
- 设置侧边栏底部（nav 分隔线下）新增「使用文档」常驻外链（BookOpen 图标，新标签打开 nmail.whizzzest.com/docs/），所有分区可见；应用此前唯一文档入口散在 API/OAuth 两处深链
- 「关于」新增「帮助与文档」卡片：文档首页 / 使用指南 / 常见问题 / 安装与更新 四入口（与「本机数据」卡同款样式）
- 文档链接去硬编码：新增 frontend/src/utils/links.ts（DOCS_URL + docsUrl(slug) 唯一出口）与 frontend/src/components/DocsLink.tsx（新标签 + indigo 下划线统一样式），ExtApiSection / OauthSettings 两处写死 URL 改走常量
- docs/使用指南.md「设置速览」表补「写信」「关于」两行（此前缺 2/8 分区），通用行更正：更新检查开关实属「关于」，补 AI 晨报/桌面通知/白黑名单；不加更多分区深链（用户拍板：现有 API/OAuth 深链已够）
- 验证：npm run build（含 tsc/字号门禁/vitest）通过；会话：S-0917-1300-设置文档入口

## 7262f5d — feat: 快捷键补齐读信与批量键位（参考用户截图样例）+ 说明只留文档跳转
- 新增键位（Gmail 语义）：`Ctrl/⌘+A` 全选/清空当前列表（修饰键放行前拦截，输入框内不劫持系统全选）；`Del`/`Backspace` 删除（与 `#` 同义）；`Shift+M` 检查新邮件（与工具条刷新同一条同步链路）；读信时 `r` 回复 / `a` 全部回复 / `f` 转发（EmailReader 键盘监听，code||key 双通道，受总开关与 keep-alive 前台态约束）
- 设置页「快捷键」说明只剩文档跳转一句（用户拍板：细节以使用指南为准）；shortcuts.ts 加「读信界面」组（r/a/f）共五组卡片，`?` 帮助面板自动跟随
- 使用指南表格补 `Ctrl/⌘+A`/`Del`/`Shift+M` 与读信 r/a/f
- 验证：npm build（含 tsc）通过
- 会话：S-0917-1255-快捷键设置页（第四轮，用户反馈）

## ff64458 — docs: 快捷键设置页文案精简 + 使用指南跳转（用户反馈）
- 设置页「快捷键」说明压到一句（去掉写信键位枚举/输入框细节——具体行为以文档为准），删底部脚注；补 DocsLink 跳官网使用指南（复用 S-0917-1300 的 utils/links.ts + components/DocsLink.tsx 现有模式）
- 卡片上的生效范围标注（仅「邮件」页签/写信时）与物理键位备注（即 Shift+3/Shift+/）保留
- 验证：npm build（含 tsc）通过
- 会话：S-0917-1255-快捷键设置页（第三轮，用户反馈）

## 7f8dec7 — ci: 主仓 docs 变更自动 dispatch 官网部署
- 原状：官网 Deploy workflow 只挂在官网仓，主仓 docs push 触发不到——最长延迟 24h 等官网每日 cron 兜底，发版靠手动 `gh workflow run`
- 新增主仓 `.github/workflows/docs-deploy.yml`：push main 且 `docs/**` 变更 → 自动 `gh workflow run` 官网 deploy.yml（workflow_dispatch 既有入口，官网侧零改动）；未配 secret 时空转跳过不报错
- 一次性配置：fine-grained PAT（仅 nmail-site 仓、Actions RW）→ 主仓 secret `SITE_DEPLOY_PAT`；dispatch 链路已实测——主仓 run（9s）→ 官网 deploy 被踢动（38s success）→ 线上 200
- 会话：S-0917-1255-快捷键设置页（追加）

## 73b8fa8 — fix: 快捷键总开关改全量开关 + 生效范围/物理键位标注（用户反馈）
- 总开关语义改全量：关闭=清单内全部键位停用，不再保留例外——写信 Ctrl/⌘+S（ComposeForm 容器守卫）、Ctrl/⌘+Enter（RichEditor 经 ref 跟随，编辑器实例只建一次）、邮件页 `?` 帮助与 `Esc`（含读信返回）同样受控；界面按钮不受影响
- 生效范围显式化：shortcuts.ts 分组加 scope（仅「邮件」页签 ×3 / 写信时），设置卡片与 `?` 帮助面板组标题同步标注；说明行注明焦点在输入框时暂不触发
- 物理键位备注：`?`（即 Shift+/）、`#`（即 Shift+3）展示在说明后；使用指南表格 `?` 行补 Shift+/、正文补范围声明
- 验证：npm build（含 tsc）通过
- 会话：S-0917-1255-快捷键设置页（第二轮，用户反馈）

## 83aafdb — feat: 设置页新增「快捷键」分类——总开关 + 分组清单，键位清单数据源单一化
- 设置页侧栏新增「快捷键」（通用之后）：总开关「启用键盘快捷键」选择即保存；四组键位卡片（列表导航/邮件操作/搜索与帮助/写信）
- 键位清单抽为共享数据源 frontend/src/shortcuts.ts：设置页与邮件页 `?` 帮助面板同源（帮助面板同步改分组渲染，顺带补上写信 Ctrl/⌘+S、Ctrl/⌘+Enter 两键的展示——此前仅文档有）
- 总开关生效逻辑（MailBrowser keydown 守卫）：关闭时仅屏蔽动作键；Esc（输入框脱困/关浮层）与 ?（帮助入口）保留——关了也能按 ? 找到设置在哪；写信 Ctrl/⌘+S、Ctrl/⌘+Enter 不受控
- 后端 shortcuts_enabled 设置项（api/settings.py：DEFAULT_SETTINGS/SettingsIn/GET/PUT 四处）；openapi.json + schema.d.ts 再生
- 验证：ruff 通过；npm build（含 tsc）通过；隔离实例（8931）curl 往返——默认 True、PUT false 落库回读 False
- 会话：S-0917-1255-快捷键设置

## 051f4c9 — ci: 发版产物补齐——DMG / Windows zip / Release Notes 自动化 / tap cask（WIND_DOWN_PLAN P1）
- release.yml binaries job：macOS 分支新增 DMG 两栏拖装（Nmail.app + /Applications 软链，hdiutil UDZO）→ 新资产 `nmail-macos-arm64.dmg`；Windows 分支新增 portable zip（Compress-Archive 打包 exe）→ 新资产 `nmail-windows-x64.zip`
- homebrew-tap job 新增「更新 tap cask」步骤：从 `scripts/cask_template.rb` 渲染版本号与 SHA256 后 create-or-update `Casks/nmail.rb`（首版自动创建，后续自动 bump；指 dmg 资产、`depends_on arch: :arm64`、livecheck github_latest）
- 本机验证：release.yml YAML 校验过；cask 模板 sed 渲染 + `ruby -c` 语法过；DMG 两栏布局本机 hdiutil 实测（挂载后 Applications 软链 + Nmail.app 就位）
- 留发版轮验证：cask 全链路 `brew install --cask`、dmg 拖装实测、Release Notes 渲染效果
- 会话：S-0916-1258-收尾计划

## 0f9f065 — fix: 快捷键失灵四连根因修复 + `?` 帮助面板（WIND_DOWN_PLAN P3）
- 用户报障「上一封/下一封、删除、聚焦搜索用不了」，真机排查为四个叠加根因：①键盘游标（cursorId）在渲染层零引用——j/k 实际在动但毫无视觉反馈，等同失灵；②焦点陷阱——用过 `/` 或点过输入框后焦点困在输入框，守卫让全部快捷键静默失效且无任何提示（主因）；③中文输入法全角标点下 `＃`/`／` 与 `e.key` 不匹配，删除/搜索变死键；④阅读态 j/k 只动不可见游标、不切换邮件
- 修复（MailBrowser.tsx）：①游标行灰底高亮（bg-gray-100，与选中态 indigo-50 区分）；②Esc 全局优先——焦点在 INPUT/TEXTAREA/SELECT 先 blur 脱困（isComposing 不劫持输入法取消），帮助浮层开着则先关浮层；③键位匹配改「e.code || e.key」双通道——e.code 物理键位免疫全角标点，e.key 兜底合成事件（实测 CDP 把 `/` 合成为 NumpadDivide，纯 code 匹配会漏）；④阅读态 j/k 直接切换上/下一封（Gmail 语义，经 selectEmail 带已读标记）
- 新增 `?`（Shift+/）快捷键帮助浮层 + 工具栏键盘图标入口；10 键位清单为模块级 SHORTCUTS 常量，与使用指南表格同源
- 使用指南快捷键表补全：↑/↓ 方向键、# 标注 Shift+3、`?` 与 Esc 语义、阅读态切换说明、写信 Ctrl/⌘+S 存草稿与 Ctrl/⌘+Enter 发送
- 验证：npm build（含 tsc/字号门禁/vitest）通过；真机实例（Chrome DevTools MCP）回归——初始游标可见、搜索框内 j 被吞→Esc 脱困→j 恢复、帮助面板开关、阅读态 j/k 双向切换全过
- 会话：S-0916-1258-收尾计划

## daf08f6 — docs: 收官阶段定稿（docs/WIND_DOWN_PLAN.md）
- 用户拍板六项决策：①Homebrew 只做自家 tap cask（`brew install --cask nathanpenny520/nmail/nmail`），不提交官方 homebrew-cask ②macOS dmg 首选、`.app.zip` 保留，官网/Release 默认下载即 App ③Intel macOS 放弃（仅 Apple Silicon）④不迁 Tauri（无 Electron 前提：Python 后端 + 浏览器 GUI）⑤Linux 维持单文件不做 AppImage/deb ⑥Windows 不上代码签名（zip 仅打包体验，SmartScreen 警告依旧）
- 任务清单 P1–P4：release.yml 补 dmg/zip/`generate_release_notes`/tap cask 同步；文档四处同步（INSTALL/README 双语/官网 download.astro/代码文案）；键盘收尾（`?` 帮助面板 + 使用指南表补 `↑↓` 与写信 `Ctrl/Cmd+S`/`Ctrl/Cmd+Enter`）；决策落档
- CLAUDE.md 头部加收官主线指针；键盘现状盘点：MailBrowser 全局 9 键已在（j/k/↑↓、Enter/o、e、#、x、c、/、Esc），文档仅使用指南一张 8 键表且缺 ↑↓ 与写信快捷键

## 472dfb3 — feat: Windows 无窗口化（双击不再弹黑窗）+ 显式退出 + 日志落盘
- 用户反馈：Windows 双击 exe 弹命令行黑窗，误点 X 即杀后端。nmail.spec `console=(sys.platform != "win32")`——仅 Windows 改窗口子系统，双击即纯后台运行，无窗可误关；macOS/Linux/源码 `run.py` 控制台行为不变，重复双击仍走单实例探测
- 配套：①cli.py 日志落盘——root logger 挂 RotatingFileHandler（`<DATA_DIR>/nmail.log` 1MB×3 滚动），uvicorn 经 `log_config` 注入同一文件（dictConfig 会整体覆盖其 handlers，必须改配置而非事后挂）；②启动失败兜底——main 薄壳捕获未捕获异常，traceback 落盘 + Windows 冻结包弹原生 MessageBoxW，绝不静默消失；③`POST /api/quit`（延迟 0.8s `os._exit(0)`，与 restart_app 同款节奏）+ 设置-关于「退出 Nmail」卡片两段确认——关浏览器标签不退服（后台轮询/每日摘要常驻，与 macOS Dock 语义一致）
- 顺带清同类闪窗隐患：`_git_commit` 冻结包短路；desktop.py 两处 PowerShell spawn 补 `CREATE_NO_WINDOW`；pip/uvx 渠道 Windows 图标改指 `pythonw -m app.cli`（console script/.cmd 都闪黑框），pythonw 缺失退回 .cmd
- 文档四处同步：INSTALL（单文件渠道「运行后/退出/日志」三条）、FAQ（端口占用）、ARCHITECTURE（system 表 + 分发注意点）、UPDATE_AND_DESKTOP 新增 §6 决策记录
- 验证：ruff 通过；pytest 249 全绿；npm build（含 tsc/字号门禁/vitest）通过；隔离实例实测 `/api/quit` 响应后 1.5s 内进程退出、nmail.log 正常落 uvicorn/access 日志；openapi 快照 + schema.d.ts 同步
- Windows 真机（黑窗消失/退出/崩溃弹窗）待用户双机实测
- 会话：S-0916-0020-Windows无窗口化

## 07edc29 — fix: 更新就绪态自愈，「重启即更新」提示应用后不再悬挂
- 用户实测：更新到 0.4.2 并重启后，设置-关于 仍显示「新版本 v0.4.2 已就绪，重启即更新」——根因：就绪态（`phase=ready`）设计上跨重启保留、靠前端版本对比隐藏，但关于页 UpdateApplyRow 漏了对比，就绪态本身又永不清除 → 永久悬挂
- 修复（update_apply.py）：新增 `_heal_applied_ready` 自愈——`phase=ready` 且 `staged_version` 已不比当前新 → 归位 `idle` 并清理过期更新通知；挂启动收尾 `finish_pending_swap` 与 `GET /api/update-apply` 两处（已中招机器读一次即愈）；`staged_version` 三个写入点统一存不含 v 前缀的裸版本号（此前 binary 渠道存 `v0.4.2`，关于页会渲染成「vv0.4.2」、浮条的版本对比也永不匹配）
- 验证：ruff 通过；pytest 249 全绿（+1 就绪态自愈回归测试）；npm build 通过；本机 8720 实例走应用内重启端点载入新代码，KV 就绪态归位 idle、接口不再报 ready
- 会话：S-0916-0007-更新提示悬挂

## d9eae83 — release: v0.4.2 + tag
- **首个全渠道真实可用的版本**：冻结入口 `__main__` 修复（873ce06）随版生效——此前所有发布（v0.1.0–v0.4.1）的单文件/winget/brew 二进制均静默退出，本版起才真正可运行
- release.sh 全流程：PyPI nmail-app 0.4.2 ✅、Release 四资产（三平台 + 首个 `nmail-macos-arm64.app.zip`）✅、tap 自动 bump 0.4.2 ✅（本机 brew 全链路实测 `nmail --version` → `Nmail 0.4.2`）、winget PR microsoft/winget-pkgs#435195、官网联动重建
- 配套文档：INSTALL.md 补 macOS .app 压缩包推荐；官网下载页 brew 命令改全名+trust、新增 .app 压缩包推荐卡（nmail-site ba1b2b6，资产名实测为小写 `nmail-macos-arm64.app.zip`，勿按提交信息想当然）
- 会话：S-0915-2305-brew安装排查（发版执行，等 S-0915-2225 收官后启动）

## 31fd015 — fix: Nmail.app 装标准 /Applications + Dock 图标常驻（编译型存根）+ 重启端口不再顺延
- 用户实测反馈两问题——①.app 装到了用户目录 Applications 而非标准位置 ②点击打开后 Dock 图标不保留
- 安装位置：macOS 改首选 `/Applications`（用户期望标准位置；无写权限的普通用户自动回退 `~/Applications`）；CLAUDE.md 决策#2「只写用户目录」同步修订
- **Dock 图标根因**：LaunchServices 不为纯脚本 bundle 注册应用（`lsappinfo`/System Events 均不可见，进程活着也无 ASN 记录）——新增编译型 ObjC 存根 `scripts/nmail_stub.m`（通用二进制 arm64+x86_64 入库 `backend/app/assets/nmail-stub`，86KB）：以 NSApplication 身份注册应用（图标=AppIcon.icns、名称=CFBundleName、⌘Q 可用、Dock 右键 Quit），服务作为其子进程跑 `Contents/MacOS/server` 脚本；应用终止向子进程 SIGTERM（3s 升级 SIGKILL）→ server 脚本 trap 链式停 Python；服务子进程退出则应用随退（「已在运行」探测场景开完浏览器即退，不留僵尸图标）；无存根资产时回退纯脚本形态
- **端口顺延根治**：find_free_port 占用判定分层——有监听必跳过（connect_ex 探测），裸 bind 失败但 SO_REUSEADDR 下可绑=TIME_WAIT 残留照常使用；此前每次重启都从 8720 顺延（8721/8722 漂移、浏览器页面地址丢失）的根因与 wait_for_port 同源
- 实测：`open` 装在 /Applications 的 Nmail.app → LS 注册 ASN 出现、health 正常、进程树 stub→bash→python；osascript quit → LS 注销、服务停净、零残留进程；quit 后立刻重启实例收敛回 8720 不再漂移
- 会话：S-0915-2225-更新与桌面图标

## 0d2aace — docs: 对外 brew/winget 命令全名同步（README 双语/官网/代码文案）
- README 双语、官网 posts×2、UPDATE_AND_DESKTOP、RELEASE 的 brew 命令统一改 tap 全名 `brew upgrade nathanpenny520/nmail/nmail`，安装命令补 `brew trust` 步骤与 core 撞名警告；CLAUDE.md 新增工作流规范 #11：对外命令/渠道说明改动同一轮同步 INSTALL/README 双语/官网/代码文案四处
- 会话：S-0915-2305-brew安装排查

## 4615db7 — feat: 自动更新（后台静默安装、重启生效）+ 全局就绪浮条
- settings 新键 `auto_update_enabled`（默认开，设置-关于 紧挨「自动检查更新」；检查关闭时该开关置灰）
- 自动触发链：main lifespan 启动 8s 后静默检查一次（复用 24h 缓存）+ scheduler 每小时 `update_tick` 兜底——检查开启+自动安装开启+渠道可自更新+确有新版本四重门控全过才后台启动更新任务，全程不打扰当前使用
- 就绪提示（文案按用户定稿从简）：通知中心该版本通知在就位时改写为「新版本 X 已就绪，重启即更新；下次打开自动生效。可在 设置-关于 调整自动更新」；前端全局浮条 UpdateReadyBar（每分钟轮询，仅「就绪且未重启」出现，叉掉按版本记忆不再打扰），「立即重启」与设置页共用抽出的 `restartForUpdateThenReload`
- **冻结包真机核验**（本地 PyInstaller 6.22 构建 + 隔离数据目录实测）发现并修复：全新数据目录首次启动时 `finish_pending_swap` 读 KV 表（迁移尚未跑）崩溃致 exe 启动失败——启动收尾改为全函数零抛错；binary 渠道识别、从冻结 exe 生成 Nmail.app、`--wait-port` 端口接管在冻结形态下实测全部可用（与 S-0915-2305 从用户侧发现的入口保护问题互为印证）
- 自动心跳门控 5 分支单测；openapi/schema 快照再生（settings 新键）
- 会话：S-0915-2225-更新与桌面图标

## 873ce06 — fix: 冻结单文件缺 `__main__` 入口保护，静默退出（brew 渠道不可用根因）
- cli.py 补 `if __name__ == "__main__": main()`——PyInstaller 冻结单文件以本文件为入口脚本执行，此前无任何调用点，二进制加载完 stdlib 即 exit 0（无输出无报错），Homebrew/Release 分发的 macOS/Linux 二进制自发布以来从未真正运行过；源码（run.py）与 PyPI console script 入口不受影响
- 排障记录：用户 brew 安装后 `nmail --version` 静默无输出；逐步排除法——同机构建 hello-world 冻结二进制正常（排除 PyInstaller 与 macOS 27 兼容性）→ 分步导入诊断二进制正常（排除依赖）→ 唯差异为入口脚本本身 → 发现缺 `__main__` 保护
- 验证：重打包实测 `--version` 输出 `Nmail 0.4.1`（Homebrew formula 测试断言同样通过）；ruff 通过、pytest 247 全绿
- 会话：S-0915-2305-brew安装排查

## 待提交4 — docs: Homebrew 安装命令改 tap 全名 + 补 `brew trust` 步骤
- 实测发现两处安装坑：①homebrew/core 早已收录 **同名但完全无关** 的 nmail（d99kris 的 C++ 终端邮箱客户端，当前 5.15.8）——裸 `brew install nmail` 经 API 命中 core 公式，装上的是别人的软件（用户本机已实际误装）②Homebrew 7.0 起第三方 tap 默认不信任，须先 `brew trust nathanpenny520/nmail`，否则公式拒载（tap 还会被判 invalid 自动删库，报错误导性极强）
- docs/INSTALL.md：安装表与 ③ Homebrew 节命令改为 `brew tap … && brew trust nathanpenny520/nmail && brew install nathanpenny520/nmail/nmail`（tap 全名限定，避开 core 撞名）；升级命令同步改全名
- 后续建议（未实施，待拍板）：tap 公式可改名 `nmail-app`（与 PyPI 包名一致）彻底规避撞名心智负担，涉及 release.sh tap 同步与 CI，下轮处理
- 会话：S-0915-2305-brew安装排查

## 029b0e4 — feat: 应用内「立即更新」与一键重启（binary/pip 渠道自更新）
- core/update_apply.py 更新执行层：Release 资产流式下载（进度节流落 KV）→ SHA256 校验（GitHub 资产 digest）→ **换身**（运行中的可执行文件可 rename 不可覆写：当前二进制 rename 为 *.old 后原路径原子落位新文件，旧进程跑旧 inode 不受影响，失败自动回滚还原）→ `ready`；pip 渠道走 `{sys.executable} -m pip install --upgrade nmail-app` 原地升级
- `POST /api/update-apply` 启动后台更新（进行中幂等）、`GET /api/update-apply` 渠道能力+进度状态、`POST /api/update-apply/restart?port=` 一键重启：新进程 `--wait-port` 接管同一端口后旧进程退出，浏览器页面地址不变
- cli `wait_for_port` 两段式回绑：先探活确认旧进程退净，再带 SO_REUSEADDR 试绑——实测发现旧进程退出后的 TIME_WAIT 残留会让裸 bind 在 macOS 上报 EADDRINUSE 等满 30s 超时、错误顺延到 8721（浏览器页面就此丢失）
- 设置页更新区块升级：发现新版本时出「立即更新」（下载进度条/校验中/pip 升级中/失败重试全状态），就绪后「立即重启更新」（前端轮询 /api/health 待版本变化自动刷新）；brew/winget/uvx 渠道显示对应升级命令 + 一键复制
- 换身舞步/回滚/启动收尾（finish_pending_swap 处理下载中途退出的残局）补 4 项单元测试；重启链路 8720 真实实例 e2e（旧进程退净、单实例回绑同端口、health 恢复）
- 会话：S-0915-2225-更新与桌面图标

## 597d0f0 — feat: 桌面图标一键安装（各安装方式）+ 渠道识别 + CLI 单实例探测
- 新增 `core/channel.py`：启动时识别安装渠道（binary/brew/winget/pip/uvx）——自更新与桌面集成都按渠道分流；uvx 经 uv 缓存路径特征识别，brew/winget 冻结二进制按安装路径识别
- 新增 `core/desktop.py`：一键生成桌面图标——Windows 桌面+开始菜单 .lnk（PowerShell COM）、macOS `~/Applications/Nmail.app` 包（Info.plist+icns）、Linux .desktop+hicolor 图标；状态检测/移除/重装；binary 渠道直接包装自身，pip/uvx 先落启动命令包装器再包装
- 图标资产随包分发：`backend/app/assets/`（ico/icns/512png 入库入 wheel package-data，nmail.spec datas 打入冻结包），gen_icons.py 产出时同步写入
- cli.py：`install-shortcut`/`uninstall-shortcut` 子命令；单实例探测（8720 已有健康 Nmail 直接开浏览器退出，不再端口顺延多开）；`--wait-port N` 启动参数（等端口释放精确回绑，供更新重启使用，下一条提交消费）
- API `GET/POST/DELETE /api/desktop-shortcut`；设置页「关于」新增「桌面图标」卡片（未安装→一键安装，已安装→显示位置+移除）
- CLAUDE.md 决策#2 修订：桌面图标集成按需生成、只写用户目录；方案与决策记录 docs/UPDATE_AND_DESKTOP.md
- 会话：S-0915-2225-更新与桌面图标

## 03c44e7 — fix: 写信页签关闭即问去留 + 页签顺序跨刷新保留
- 非 dirty 写信页签关闭不再静默——已落库草稿（含已自动保存的）一律弹「保留草稿/丢弃草稿」确认：此前非 dirty 直接关、草稿留在服务端 status=editing，启动恢复会把页签原样拉回，页签条永远关不干净（用户反馈「删了刷新又出现」的根因）；仅空白未落库标签维持直接关（随手点开零成本）；确认弹窗标题措辞改为对 dirty/非 dirty 都成立
- 确认弹窗从 ComposeWorkbench 上移到 Layout 常驻渲染——工作台仅激活态挂载，原先关 **dirty 非激活**页签时弹窗挂不上、点 × 无反应（潜伏 bug，一并修复）
- 落地 e2e 中发现并修复两处挂载期竞态：tabId 映射落盘 effect 挂载时即以空 tabs 清写 sessionStorage，恢复 fetch 完成后才读必读到空——改为恢复 effect 发起请求前同步取映射；tabOrder 死键清理同理会在恢复完成前把 compose 键误当死键剪掉——ComposeContext 增 `restored` 完成标记，恢复完成前不剪
- 写信页签拖拽顺序跨刷新保留：启动恢复此前每次生成新随机 tabId，nmail_tab_order 里的 compose: 键全部失配被过滤（顺序实际不生效）；现恢复时复用 sessionStorage 的 draftId→tabId 映射（新键 nmail_compose_tab_ids，随 tabs 变化自清理），映射缺失/冲突回退新 id
- nmail_tab_order 死键清理：页签关闭/草稿删除后失效键及时从 state 剔除，落盘不再积灰（渲染层本就过滤，纯卫生）
- skills/SKILL.md 更新检查补提议：升级 CLI 顺带 `uv cache prune` 清理 uv 缓存历史版本；uvx `@latest` 语义经官方文档核实=每次运行请求并使用最新版（裸包名才是首跑定版后沿用缓存），skill 全部命令为 @latest 形式，自动更新天然成立
- 会话：S-0915-2150-页签恢复修复

## 768d5fa — docs: README 精简改版 + 嵌入演示 GIF
- 嵌入 assets/Nmail-demo.gif（1280×720，3.7MB）；「快速开始」收敛为两渠道（单文件 / 一行命令），uvx 补「命令即启动命令：重跑同一条即再次打开，升级 --refresh」口径（对齐 INSTALL.md 与官网下载页）；「首次使用（约 5 分钟）」从源码段尾独立成节（所有渠道共用）；删「自行打包」节（并入「开发」一行指引 → docs/RELEASE.md）、删 v0.4.0 特性长枚举（指向 docs/CHANGELOG.md）；「源码开发」与「开发模式」合并为「开发」节去重；更新节各渠道升级补 uvx --refresh；README.md 与 README.zh-CN.md 同步改

## 5cd023e — docs: INSTALL 补 uvx 方式升级命令与「更新」指引
- uv 官方文档核实语义：`uvx` 首次运行取最新版、之后沿用缓存环境，新版本发布不会自动跟上，升级需 `--refresh` 刷新缓存。「更新 → 升级命令」补 uvx 条目 `uvx --refresh --from nmail-app nmail`（原仅 winget/brew/uv tool upgrade/单文件四渠道）；「启动与再次使用」注尾补「升级方式见下文更新」指引
- 动机：官网下载页要向 uvx 用户写清更新方式，主仓文档此前对 uvx 渠道升级无官方口径；本机实测 `uvx --refresh --from ruff@latest ruff` 语法通过

## d8fad4c — 修复: 归档后邮件不可见（skill 实测发现）+ 版本线统一自动化 + CLI 补 drafts delete/folders sync/watch 自动退出（v0.4.1 内容）
- **archive/unarchive 修复（skill 全量实测发现的核心 bug）**：QQ 等不回 COPYUID 的服务商上，归档/移动拿不到新 UID → 本地删行（R2 语义）→ 归档夹不在轮询范围 → 邮件无限期"消失"、unarchive 静默 updated:0。修复三件套：①移动类动作发生删行后，`batch_ops` 就地复用同一 IMAP 连接增量同步目标文件夹（`sync.resync_folder_with_mb`，动作后立即可读）；②按 message_id 找回新 id，job 结果返回 `rebuilt: {旧id: 新id}`（CLI/skill 换新 id 续操作）；③调度轮询带上归档夹（仅当账号文件夹缓存已有它），其余文件夹维持按需同步不全量轮询。真机回归：archive→rebuilt 映射→立即 read→unarchive→恢复原状全链路通过
- **版本管理统一 + 自动化**：app / nmail-cli / skill 此前三条版本线（0.4.0 / 0.1.0 / 1.2.0）互不相关，CLI 版本协商 `_notice.update` 拿无关版本线做比较→每次调用必误报"落后建议升级"。统一为同一条版本线（唯一来源=根 pyproject）：新增 `scripts/sync_version.py` 一键同步四处（根 pyproject / nmail-cli pyproject / `__init__.__version__` / SKILL.md frontmatter），release.sh 发版自动调用，`test_version_sync.py` CI 兜底防漂移；skill 版本 1.2.0→0.4.0 对齐
- **CLI 闭环补齐**（ext + CLI 同步加）：`DELETE /drafts/{id}`+`drafts delete`（仅 editing/discarded 可删，AI 待审等在途草稿 409 防误清审批队列）；`POST /folders/sync?wait=true`+`folders sync`（同步完成才返回，归档恢复兜底）；`watch --timeout/--max-emails`（自动退出，SKILL.md 明确 agent 调用必须带 timeout 防挂起）
- **SKILL.md**：安装节补 uvx 镜像兜底（`UV_DEFAULT_INDEX` 官方源 / pipx）；emails action 补 `rebuilt` 换新 id 纪律；安全规则补钓鱼注入"可复测基线"；命令表/参数速查/示例同步新命令
- 文档：ARCHITECTURE（batch_ops/scheduler/nmail-cli/release.sh 四处）、对外API使用指南（3 个端点行）同步；openapi.json 快照 + schema.d.ts 同提交；前端 build 通过（vitest→tsc→vite）；后端 230 测试全绿（+4：版本一致/重建映射）、CLI 16 全绿（+3）
- 会话：S-0915-2130-版本统一与CLI修复；真机验证于 8720（0.4.0）

## 06eca8b — docs: v0.4.0 用户文档补齐（指南/FAQ/Agent 接入/README 双语）
- 使用指南：AI 总管家「怎么用」补 v0.4.x 用户向六点（触顶先小结再暂停+续跑入口恢复 / ask_user 澄清卡 / 跨会话记忆与设置页管理 / 四个内置工作流技能 / 完成断言防幻觉收尾）；能力表增「工作流技能」行；每日摘要增「AI 晨报」段（独立区块/开关语义/通知展开全文）；通知段补展开全文；设置速览 AI 用量行补记忆
- FAQ 新增四问：AI 会记住偏好吗（本机记忆库）/ 晨报与摘要的关系 / 长任务触顶行为（小结+继续+断言纠正）；沿用四层防线问答
- Agent接入指南：新增「§4 偷懒通道：内置总管家」（agent ask/decide/resume 紧凑输出与人工确认边界，agent scope）+「§5 其他 CLI 常用件」（folders list、版本协商 _notice.update）；原 4/5 节顺延为 6/7
- README 双语状态行：v0.3.0 已发布 → v0.4.0 已发布+Agent 化收官要点（记忆/晨报/技能/CLI 通道）
- 官网（nmail-site 独立仓另行提交）：版本口径 0.3.0→0.4.0、功能页/首页/项目卡文案更新、v0.4.0 发布动态帖

## e9a6946 — 发版: v0.4.0 全平台——PyPI/Release/tap/官网即时生效，tap 403 老毛病复发（手动兜底），winget 0.4.0 PR 已提
- `release: v0.4.0`（e9a6946）+ tag 推送，release CI run 34941786990：PyPI `nmail-app` 0.4.0 ✅、**PyPI `nmail-cli` 0.1.0 首发认领包名** ✅、GitHub Release 三平台资产 ✅、homebrew-tap 首发 403（与 v0.3.0 同根因：`HOMEBREW_TAP_TOKEN` 失效）→ 用户当日续期 secret → 重跑该 job ✅，**run 整体转绿，v0.4.0 成为首个 CI 全绿版本**（手动兜底提交 5045fdf 保留，内容与 CI 结果一致）
- 手动同步 tap formula → 0.4.0（homebrew-nmail 提交 5045fdf，url/SHA256 对齐 Release 资产，`brew upgrade nmail` 即生效）；官网重建（run 34944037912，含 S-0915-1545 的 v0.4.0 官网文案提交）
- winget：fork 分支 nmail-0.4.0 提交三 manifest（ManifestVersion 1.6.0），PR microsoft/winget-pkgs#434983；存量 0.1.0（#432990）/0.3.0（#433678）两 PR 校验 8/8 全绿，仍待社区审核合并
- 本版内容（自 v0.3.0）：**v0.4 改版主线全量落地**——草稿中心（AI 待审+手写+定时发送统一收口）、AI 总管家 2.x Agent 化（对话式执行/审批卡/五授权位/内置技能层/运行观测/ask_user/同批并行）、对外 API（/api/ext/v1，scope 分级+限流+调用日志）+ **nmail-cli PyPI 首发**、安全加固（来源校验第三层：公网 CF 隧道管理面拦截）、前端测试基建（Vitest+RTL 挂入 build 门禁）

## 5638375 — 测试基建：前端 Vitest+RTL 首批用例挂入 build 门禁（审计 B1/B3）
- ExtApiSection 8 用例：密钥默认遮蔽/眼睛显隐/吊销确认与取消/重置/创建 payload（trimmed+默认 read+空上限=null）/总开关（不携带日志开关字段，后端保持原值）——对外 API 管理面交互语义固化
- `npm run build` 链路增 vitest run（字号 lint → vitest → tsc → vite build）；新增 npm test / test:watch；vite.config 增 test 段（jsdom + globals + setup）

## 7a74836 — 文档：数据目录禁入云盘同步范围警示（审计 A2/A3 收尾）
- A2 密钥面扫描零发现：无 print/logger 泄漏点；api_calls 仅存 key_id/method/path/status；ai_actions params 为邮件操作参数；AI 写信 HTML 预览后端已消毒（sanitize_outgoing_html）；前端唯一 dangerouslySetInnerHTML 消费消毒后 HTML；react-markdown 未启 rehype-raw
- A3 SQL 注入扫描零发现：8 处 f-string 拼接全为白名单列名/占位符模式，值一律参数化

## 3621831 — 安全加固：公网隧道管理面拦截（CF-* 边缘头 403，审计 A1）
- 审计背景：文档推荐的 cloudflared 公网隧道默认把转发请求的 Host 重写为 origin 地址、curl 类客户端不带 Origin——Host/Origin 两道本机校验双双失效，管理面明文回显端点（/api/accounts、/api/extkeys）经公网域名无需任何 Key 即可达（本机探针实证；方案与证据链在 personal-data/审计方案-2026-09-15.md，不入库）
- 修复（main.py 来源守卫第三层）：非 `/api/ext/*` 请求携带 CF-* 头（Cloudflare 边缘特征，cloudflared 原样转发）一律 403——SSH 隧道（无附加头）与 Tailscale serve（仅 X-Forwarded-*）不受影响；`/api/ext/*` 在守卫之前已放行，持 Key 公网调用不变
- 测试：test_source_guard.py +4（CF 头矩阵拒绝 / ext 带 CF 头放行 / X-Forwarded-* 不拦 / ext Host 豁免）；顺带清 test_agent_loop.py 一处 F841；pytest 228 全绿（+4）、ruff 通过
- 文档：隐私与安全（网络边界改三层校验 + 明确隧道分工：Web 界面走 SSH/Tailscale、公网 CF 隧道仅用于 ext）、对外API使用指南（§3.1 ingress 路径白名单 + 安全边界提示）、ARCHITECTURE（来源校验条目）

## b247eae — Agent 扩展收官 A6-A8 + B1-B3：运行观测/技能层/CLI 全量对齐（REDESIGN_PLAN §20 / AGENT_EXTEND_PLAN 全部落地）
- 用户指示「全部完成」——§20 剩余六项一次收尾；B3 按拍板 3 落地，A7 技能存放按推荐值内置层先行
- A6+A8 运行观测：`GET /api/ai/agent/runs`（列表）+ `/agent/runs/{id}`（状态/pending/步级 token——聚合 ai_logs 'run {id} step {n}' 行，零新表）；前端 openSession 查最新运行、停在触顶态时恢复「继续」横幅（刷新不再丢续跑入口）
- A7 技能层：`ai/skills_builtin.py` 四个内置工作流技能（周报摘要/跟进提醒/批量归档策略/报销发票整理——方法论提示词包，零规则匹配不违背决策 3）；系统提示词只注入索引（prompt 缓存友好），新工具 read_skill 按需取全文（工具 29→31）；SCHEDULER_ALLOWED 增 read_skill
- B1 CLI：`nmail-cli folders list --account-id`（文件夹缓存列表，move/--folder 目标名有处可查）
- B2 版本协商：ext /health 返回 version；CLI 每命令尽力探测（失败静默），落后时 envelope 附 `_notice.update`（cli/server/upgrade/skill）；SKILL.md 增「更新检查」节
- B3 CLI 总管家通道：`nmail-cli agent ask/decide/resume`（scope=agent 包装既有端点，紧凑输出 answer/approvals/paused——外部 agent 一条命令复用内置审批/审计/限额闭环）；SKILL.md 增「内置总管家通道」节
- SKILL.md v1.1.0→v1.2.0（folders 行+参数速查/总管家通道/更新检查）；ARCHITECTURE 同步（api/ai、ai/tools、ai/agent、api/ext 四行）
- 验证：pytest 224 全绿（+1）、CLI 契约 13 全绿（+4：folders/agent 未配置/decide 互斥/semver+notice）、ruff 通过、npm build（tsc+字号门禁）通过、openapi/schema 快照再生、8720 重启 /api/health ok

## e45f184 — Agent 扩展 A4-A5：同批只读并行执行 + ask_user 澄清中断（REDESIGN_PLAN §20 / AGENT_EXTEND_PLAN）
- A4 同批只读并行：`_loop` 同批全为已授权只读工具时 ThreadPoolExecutor（≤4 workers）并行执行、结果按原序回灌（保 tool_call_id 配对）；混合批/写类维持串行（顺序敏感+可遇审批暂停）；日限额按批预检，SQLite 每线程连接保证并发读安全
- A5 澄清中断：新工具 `ask_user(question, options?≤6)`（kind=meta——不入审计、不可直执行、scheduler 白名单天然排除即无人值守硬拒不挂起）；触发置 waiting_input 暂停，前端「向你确认」卡（选项按钮+自由输入）回答后带 answer 经 /agent/resume 续跑，回答以 ask_user 调用的 tool 回应回灌（兼保 tool_calls 配对）；缺 answer 续跑明确报错且 run 保持可续不卡死
- 配套：内部与 ext 的 `/agent/resume` 增可选 `answer`；`_build_segments` 增 ask_user 分段（刷新后还原一致）；前端 AskCard + 事件处理（types/ManagerPage）
- 验证：pytest 223 全绿（+5：只读并行线程断言/混合批串行/澄清暂停与回答续跑/缺回答不卡死/白名单硬拒）、ruff 通过、npm build（tsc+字号门禁）通过、openapi/schema 快照再生；8720 重启 /api/health ok；A4/A5 真实模型行为待用户日常使用观察

## fc5f763 — Agent 扩展 A1-A3：触顶强制小结收尾+完成断言校验+保头尾截断（REDESIGN_PLAN §20 / AGENT_EXTEND_PLAN）
- 用户拍板触顶行为=「小结+手动继续」（不加自动续段：纯读类循环不占每日动作限额，步数/时间是唯一成本闸，自动续跑无人踩刹车）；方案（deer-flow 2.0/smolagents 1.27 调研）见 docs/AGENT_EXTEND_PLAN.md，拍板与落地记 REDESIGN_PLAN §20
- A1 触顶强制收尾：`_wrap_up_events` 步数/时间预算耗尽先临时注入收尾指令+禁工具要一段进度小结（指令无论成败弹出；小结 assistant 落库+流式下发）再 paused——scheduler 晨报无人值守跑满步数不再零产出空悬；resume 对触顶暂停注入「用户选择继续」锚点
- A2 完成断言校验：最终回答声称已发送/已归档/已删除/已移动/已标记/已起草但本 run 无对应工具调用记录（`_attempted_tools` 从 messages 提取，native+JSON 双形态，跨续跑持久）→ 回灌纠正一次让模型改口或说明；二次不符原文放行+末尾系统注记（不静默不阻断）——防幻觉收尾，纠正消息允许「指历史记录」说明，误伤代价仅一次往返
- A3 保头尾截断：`_feedback_text` 超预算由只保头改为头 60%+尾 25%——邮件线程最新回复在尾部不再丢失
- 验证：pytest 218 全绿（+6：触顶小结/预算小结/纠正改口/二次警示/判定矩阵/头尾截断，原步数与预算暂停用例更新为 A1 形态）、ruff 通过

## 90f3ece — skills/SKILL.md v1.1.0 打磨（对齐 CLI 实际参数面）+ Agent 扩展方案落档
- SKILL.md 审计：对照 `nmail_cli/cli.py` 实际参数面逐项核对，P3 成文时文档落后实现——补 6 处缺口：①草稿附件 `--attachment`（create/reply/forward 可重复，P1 端点+CLI 均有而文档未提）②`--cc/--bcc` ③分页 `--limit/--offset` + 「翻页保持原条件只增 offset」纪律 ④`watch --since-id/--account-id/--interval` ⑤`auth status/logout` 入命令清单 ⑥scope↔命令对照表（read/write/send 分工、只读 Key 撞 exit 3 的处理）；新增「参数速查」节 + 发送带附件两阶段示例；version 1.0.0→1.1.0
- 核对无误未动：exit code 表与 CLI `EXIT_*` 全量一致、安全六条、两阶段唯一规则、正文规范；官网 /docs/agent/ 走 sync-docs 白名单同步 Agent接入指南.md（人类向简介），无需随动
- docs/AGENT_EXTEND_PLAN.md 新增（deer-flow 2.0 / smolagents 1.27 调研产出，**未执行**）：§1 两仓机制↔Nmail 现状对照（错误回灌/上下文压缩/校验/审批/白名单/流式/审计均已覆盖，勿重复建设）；方向 A 内置总管家 8 项——A1 步数耗尽强制收尾（scheduler 晨报无人值守场景零产出）、A2 final answer 确定性校验闸门、A3 工具结果保头尾截断、A4 同批只读调用并行、A5 `ask_user` 澄清中断（deer-flow 表单协议）、A6 批量任务事件持久化+断线回填、A7 邮件工作流技能包、A8 步级可观测；方向 B 对外 CLI 3 项（folders 命令/版本协商 _notice.update/包装总管家通道缓发）；待拍板 5 项 + 明确不做 4 项（代码沙箱/MCP/向量检索/LangGraph 级框架）

## 2595512 — fix: 晨报区块随开关即时显隐 + 挪至摘要页底部（用户反馈两点）
- 「关闭后 AI 晨报还显示」：GET /api/digest 按开关过滤 agent_brief（关=历史晨报一并隐藏，导出同源）——开关语义定型为「关=完全不显示」
- 「放摘要下面」：晨报区块从摘要顶部挪至最底部（各账号分布之后），页面动线=统计→图表→需回复→重要→各账号→AI 晨报
- 验证：pytest 213 全绿（+1 开关显隐）；真实实例 curl 双态实测（开=True/关=False）；npm build 过

## e1c9010 — feat: 摘要页新增独立「AI 晨报」区块（用户拍板：晨报不顶替综述）
- 用户反馈综述与晨报混同：store_agent_brief 改存独立键 agent_brief（不再覆盖 ai_overview）；摘要页新增「AI 晨报」卡片（Sunrise 图标+靛蓝配色区分于综述的紫色 Sparkles），有晨报当日不重复生成常规综述（省一次 LLM）；导出 Markdown 附「## AI 晨报」段
- 验证：pytest 212 全绿（用例改断言独立键+无 ai_overview）、npm build 过；真实实例触发晨报——GET /api/digest 返回 agent_brief 正文+无 ai_overview+新鲜统计（new_today=7），开关保持开启

## 581dde8 — fix: 通知中心支持展开全文 + 晨报通知携带正文（回应「通知无法直接阅读」反馈）
- 用户反馈：通知列表正文被 line-clamp-2 钉死、晨报通知只有指路文案，点通知跳转无法直接阅读——NotificationBell 新增「展开全文/收起」（>90 字符出现，stopPropagation 不触发跳转，展开后 whitespace-pre-wrap 保留晨报排版）；点击行仍按类型跳转（摘要→摘要页）
- scheduler：晨报通知正文改为携带晨报全文（≤2000 字符）+ 草稿待审/摘要页指引
- 顺带厘清「每日摘要没更新」：摘要是当天 digest_time 生成的一次性快照（今晨 07:00 生成时无新邮件故全 0），白天新邮件不自动进快照——已用「重新生成」刷新当日数据（new_today 0→7）；开启 AI 晨报后每晨生成即最新快照，白天看最新点「重新生成」即可

## 216d6da — fix: AI 晨报接入每日摘要页（回应「与摘要重合」反馈，两者合一定型）
- 用户指出晨报与每日摘要目的重合：原实现晨报只落通知、摘要页当天会空——现定形为「晨报=摘要的 AI 形态」：ai/digest.py 新增 store_agent_brief，晨报成功后写入当日 digest_history（结构化统计照常收集，AI 综述=晨报正文，摘要页完整渲染；agent 拟的草稿经 has_draft 自然出现在「需要回复」列表闭环）
- 运行失败/无产出自动回退旧版 build_digest，当天摘要不缺席；通知文案改为引导到「每日摘要」页
- 验证：pytest 212 全绿（+1：store_agent_brief 落库形状）；ruff 通过；真实 e2e——scheduler 触发晨报后 GET /api/digest 返回当日完整摘要（ai_overview=晨报正文+overview/trend/need_reply 结构齐全）；测试开关已还原默认关

## ecd3789 — P7-D：AI 晨报（调度定时运行+工具白名单硬边界）+ 规则提议（REDESIGN_PLAN §18.5/§18.6）
- 规则提议（§18.5 拍板落地）：core/rule_proposals 观察用户手动归档/删除（imap_batch 任务体回写，rule_observations 按 email_id 去重），同发件人 14 天 ≥3 次 → pending 提议（agent_proposals；已在名单/已有 pending/rejected 不再提、上限 5 防骚扰）；设置-AI 用量「规则提议」卡采纳/忽略；采纳转调 add_sender_list 既有黑名单管线（不入 agent 审计——用户手动决定），忽略后同发件人不再提；GET 列表懒触发兜底
- AI 晨报（§18.6，用户拍板：与每日摘要调度骨架结合）：设置-通用新增开关（agent_brief_enabled 默认关），开启后 digest_time 到点由 scheduler 触发 agent 定时运行替代当日摘要（当天标记 KV agent_brief_last_run；独立线程不阻塞 tick）；origin=scheduler+auto 模式+固定指令（总结未读+create_draft 拟稿+set_category 标记）
- 硬边界=工具白名单：run_stream 新增 allowed_tools（SCHEDULER_ALLOWED=7 读类+create_draft/set_category），schema 过滤+执行层双拦（点名白名单外工具直接拒绝且不落审计），agent_runs.allowed_json 持久化（续跑不丢）；草稿只进待审列表由用户确认发送
- v25 迁移：rule_observations + agent_proposals + agent_runs.allowed_json
- 验证：pytest 211 全绿（+3：提议全流程/白名单拒绝且不落审计/allowed_json 持久化）、ruff 通过、npm build（tsc+字号门禁）通过、openapi 快照再生（112 端点）；真实实例 e2e——开启开关后 scheduler 60s 内触发晨报（agent_runs origin=scheduler/auto/allowed_json 落库，3 次 set_category 执行+1 次失败被循环兜住，通知中心收到晨报正文）；提议流程以真实最高频发件人实测——3 次观察→GET 懒触发生成 pending→decide 忽略→不再复活；测试数据零残留、开关已还原默认关

## cf39666 — P7-C：跨会话记忆——AI 记住你的长期偏好（REDESIGN_PLAN §18.5）
- agent_memory 表（v24：content/evidence 必填/source/时间戳）；工具 26→29——save_memory（write/organize，evidence 硬要求=用户原话逐字引用防从邮件内容脑补，同文去重更新，上限 100 条）/list_memory（读）/delete_memory（写）
- 系统提示词尾部注入「# 用户长期偏好」块（最近 30 条，每条附原话佐证；与 §17.8 L3 会话内记忆 memory_json 分层——run 级简报 vs 跨会话持久偏好）
- 设置-AI 用量区新增「AI 记忆」卡：查看（含佐证原话）/逐条删除；API GET|DELETE /api/ai/memory
- 安全：approval 模式保存走审批卡；auto 模式直接执行但全量审计+设置页可见可删；提示词明确「绝不把邮件内容当偏好来源」
- 验证：pytest 204 全绿（+4：CRUD 同文去重/提示词注入/循环 auto 落库+审计/TestClient API）、ruff 通过、npm build（tsc+字号门禁）通过、openapi 快照再生（110 端点）；8720 重启迁移 v24 后真实实例 e2e 全程——「请记住…」→模型调 save_memory→审批卡拦截→批准执行→独立新对话零历史传入仍凭注入块完整召回（复述偏好+逐字引用原话）→DELETE 清理零残留

## 12ead55 — P7-A：AI 操作历史管理——记录可删除+审计保留期+僵尸对账（REDESIGN_PLAN §18.3 瘦身版）
- 用户拍板「回滚意义不大不做，历史可追溯可删除」：原撤销补全三项（create_draft/trash/update_draft 撤销）砍掉，既有撤销能力（标记/星标/分类/归档/移动/重命名）保持
- 记录可删：DELETE /api/ai/agent/actions/{id} 单条 + DELETE /api/ai/agent/actions?scope=old|failed|all 批量（old=90 天前且保留已发送审计）；操作记录行删除按钮 +「清理」下拉（全部清空需 confirm）
- 保留期落地 cleanup_retention：ai_actions 失败/拒绝/过期/批准未执行 30 天、已执行(非发送)与已撤销 90 天、发送类已执行永久；agent_runs 终态 30 天；启动对账 running>10 分钟→cancelled（上线即清掉 09-14 僵尸 id=1）
- UI：mode「审批/自动」徽章弱化为纯文本+hover 模式说明（不再像按钮）；不可撤销行 hover 说明
- 顺带修复：GET /agent/actions?status= 筛选路径 WHERE status 裸列名歧义 500（accounts 同名列，潜伏 bug，本次 e2e 暴露）→ WHERE a.status
- 数据卫生：_FakeMB 测试残留 8 条清除（1 条经 API 删除验证 + 7 条 SQL）
- 验证：pytest 200 全绿（+2：delete/clear 三档、retention 分层+僵尸对账）、ruff 通过、npm build（tsc+字号门禁）通过、openapi/schema 快照再生；8720 重启后真实实例 e2e——筛选/单删/缺失/old 零命中/bad scope 全过

## d437145 — fix: API 密钥支持彻底删除（已吊销行不再永久滞留）+ 站点 /docs/agent/ 重部署成功
- 用户反馈：已吊销密钥一直留在列表里（原设计只吊销不删——供调用日志对账）。extkeys DELETE 改两段语义：活跃行=吊销（行为不变），已吊销行再删=彻底删除记录（返回 {ok,purged}；调用日志该 key 回退显示「已删」，随 30 天保留期清走）
- 前端 ExtApiSection：已吊销行新增「彻底删除记录」按钮（确认弹窗说明日志回退显示）；client.ts revokeExtKey 返回类型带 purged
- 测试：+1 用例（吊销→列表在→再删→列表消失→404 兜底），后端 198 全绿；ruff、npm build 通过；8720 重启后实测——两把测试期残留已吊销 Key purge 成功，列表只剩一把 read
- 站点：/docs/agent/ 首次 CI 失败（时序——站点构建先于主仓新文档推送，sync 拉不到 Agent接入指南.md）；主仓推送后 gh workflow run 重跑成功，线上 200、文档中心卡片可见

## d2fd46c — 收尾遗留：CLI 发包接 CI + Agent 接入指南与官网页 + skill 本机安装实测（AGENT_SKILL_PLAN 完成）
- 8720 常驻实例重启至 64f24d8——P1 后端（搜索过滤/回复转发/ext envelope）正式生效
- release CI 接入 nmail-cli 发包：release.yml 新增 nmail-cli-package job（构建 nmail-cli/ 并发布 PyPI 包名 nmail-cli——占用已核查可用；token 缺省回退主 PYPI_API_TOKEN，若为项目级则 repo secrets 配 PYPI_CLI_API_TOKEN 优先），实际发布随下一次发版触发；docs/RELEASE.md 补 nmail-cli 发包节与渠道速查行
- skills/SKILL.md 装进本机 Claude Code（npx skills add 本地路径——本机 GitHub HTTPS 直连不通，SSH 443 正常）：真实实例实测一轮——auth login 自动配对+自动启用、+me/emails list/search/read 只读链路、drafts reply（Re:+引用块+md→HTML）、send 两阶段 exit 8；测试草稿删除零残留，测试期三把 Key 收敛为一把 read（多余已吊销，设置-API 可见）
- 新增 docs/Agent接入指南.md（面向 agent 与其用户：skill 安装/配对/行为契约/安全边界/纯脚本替代），nmail-site 同步白名单+导航上新（/docs/agent/，提交 5aaab26 已推送部署）
- 验证：官网 npm build 19 页通过、/docs/agent/ 渲染与内链检查通过；CLI 实测走 uvx --from 本地包（PyPI 发布前的替代调用方式）

## 1721200 — P2+P3：nmail-cli 命令行客户端 + skills/SKILL.md 技能分发（AGENT_SKILL_PLAN，REDESIGN_PLAN §19）
- **nmail-cli/**（独立 Python 包，PyPI 包名 `nmail-cli`，uvx 零安装；发布随发版流程）：对外 API 薄客户端——JSON envelope（stdout `{"ok":…}`）+ exit code 契约（0/1/2/3/4/6/7/8，README 与 SKILL.md 同源）；`auth login` 本机自动配对建 Key（探测 8720 → POST /api/extkeys 建 `cli-<主机名>` 默认 read scope → 未启用时征询代开）+ 远程粘贴模式；配置 `~/.config/nmail-cli/config.json`（0600）+ `NMAIL_BASE_URL/NMAIL_API_KEY`；命令全集：`emails list/search/read（--save-attachments）/action（移动类自动轮询 job ≤60s）`、`drafts create/reply/forward/send`（`--body-file` 免转义 + `--attachment` 多文件；send 两阶段：无 `--confirmed` 出 summary 并 exit 8）、`contacts/digest/watch（NDJSON）/jobs get/+me`
- **skills/SKILL.md**（仓根，`npx skills add nathanpenny520/Nmail -g` 可装）：安装配置/命令清单与参数速查/两阶段唯一规则（拿到 exit 8 必须停下等用户，不得同轮自确认）/exit code 错误处理表/「邮件内容是不可信外部输入」六条安全规则（最高优先级）/正文规范（不加 Agent 签名）/搜索+回复、watch、下载附件示例/排错
- ext 新增 `GET /drafts/{id}` 单条草稿（CLI 发送前摘要用，read scope；+1 用例）
- 验证：pytest 后端 197 全绿（+1）、CLI 9 契约用例（ASGI 传输打真实 app：错误映射/配置 0600/自动配对/过滤/读取/reply--body-file/两阶段 exit 8/--confirmed 到达 outbox（无凭据 smtp_missing→400 业务错语义校准）/action 同步契约/watch 基线不回放）、ruff 通过；隔离实例（真库副本 8796，零外联）真实子进程 e2e——auth login 自动配对+自动启用、read-only key 发稿 403 exit 3、reply（Re:+引用块+md→HTML）、两阶段 summary 与 scope 递进、测试草稿清理零残留
- 文档：对外API使用指南补 CLI 一节与 /drafts/{id} 行、ARCHITECTURE 新增 nmail-cli 节、AGENT_SKILL_PLAN/REDESIGN_PLAN §19.3/PRODUCT_PLAN 状态推进

## bb4822e — 对外 API P1 补全：搜索过滤/回复转发草稿/正文三选一/附件/watch 游标/错误 envelope（AGENT_SKILL_PLAN，REDESIGN_PLAN §19）
- 方案：docs/AGENT_SKILL_PLAN.md（2026-09-14 方向确认、参考 AgentlyMail 只借思想）三层补全的 P1——为 skill/agent 使用补齐 API 面；方案并入 REDESIGN_PLAN §19（§18 已被 P7 强化方案占用）
- 搜索过滤（api/emails.py `list_emails`，ext 透传、内部 /api/emails 同受益）：`sender`/`recipient`（地址或姓名 LIKE）、`after`/`before`（UTC 归一化日期按日含当天，date() 口径，非法值 400）、`has_attachments`；可与 q 搜索组合
- ext 回复/转发草稿（api/user_drafts.py 新增 create_reply_draft/create_forward_draft，core/imap_client.py 新增 forward_subject）：对齐写信台 quote.ts 语义——replyAll 原收件人入 cc（剔除原发件人与本账号地址）、Re:/Fwd: 前缀防重复、正文后自动追加同构引用块；转发**不设 in_reply_to**（发送管线对 in_reply_to 会带 In-Reply-To 并回标原邮件已读，转发均不适用）；`include_attachments` 复制原附件进草稿存储
- 正文三选一（ext）：body_html 原样入库（消毒统一在发送管线，与界面写信同口径）/body_md（markdown_to_email_html）/body_text（转义+换行），多选一 400；草稿附件上传 `POST /drafts/{id}/attachments`（multipart 转调内部实现）
- watch 轮询版：`GET /api/ext/v1/emails/recent?since_id=`（id 升序 + latest_id 游标，空轮询可推进；限流 429 附 `Retry-After`——分钟限 60s、每日限到午夜秒数）
- 错误统一 envelope（main.py 异常处理器）：`/api/ext/*` 失败体 `{"ok":false,"error":{code,message}}`（code：invalid_key/forbidden/not_found/bad_request/invalid_params/rate_limited/upstream/server_error），内部 API 与 /api/extkeys 管理面保持 `{"detail"}` 原样；成功体不变
- 验证：pytest 196 全绿（+8：envelope/Retry-After/过滤透传/recent 游标/回复转发/正文三选一/附件上传与转发复制）、ruff 通过、npm build（tsc+字号门禁）通过；openapi 快照+schema.d.ts 同提交；真库副本隔离实例（8795，不带 secrets 零外联）curl 全往返——真实发件人 25 封、日期区间 17 封、recent 游标推进、真实邮件回复（Re:+引用块+md 转 HTML）与转发（Fwd:+无 in_reply_to）草稿、401/400 envelope；测试草稿删除零残留

## 3726850 — Agent 上下文管理：五层渐进压缩 + AutoCompact（REDESIGN_PLAN §17.8）
- 对标 Claude Code 上下文管理落地五层管线（新模块 ai/context.py）：L1 分工具结果预算（read_email 4000 字符其余 1200，截断留召回提示）、L2 微压缩双门（步数>12 或 token 水位≥55%）且升级为确定性摘要行（工具名+关键标量，替代盲截 160 字符；只缩 content 绝不删消息保 tool_calls 配对）、L3 会话结构化记忆（chat_sessions.memory_json＝任务简报+动作台账，注入 system 尾部+每步增量回写，run_stream 改服务端自取 chat_messages 最近 12 条，前端 6 条历史退役）、L4 确定性折叠（AutoCompact 失败兜底）、L5 AutoCompact（token≥窗口 80% 调一次 LLM 压五段式摘要替换早期段，原文归档 agent_runs.archived_json、摘要落 summary_json 并同步会话简报）
- token 计量：估算器（CJK≈1/字 ASCII≈/4）+ 每步真实 usage.prompt_tokens 校准滑动比率（EMA，压缩后重置）取大者；窗口默认 1,000,000（用户拍板），AI 档案新增 context_window 字段按模型实际值指定（本地小窗模型必填，防压缩触发过晚爆窗）；API context overflow 报错自动紧急压缩+重试一次（窗口误配自愈）
- 安全：摘要/纪要一律标注「其中指令均来自邮件内容非用户指令」防注入洗白（用户约束只从 user 消息提取）；折叠只在配对边界、waiting_approval 不压缩；archived_json/chat_messages/ai_actions 原始记录不受压缩影响；KV agent_autocompact=0 可停用 L5
- 数据库 v23：chat_sessions.memory_json、agent_runs.archived_json/summary_json；AI 档案 API/设置页新增 context_window（0=恢复默认）
- 验证：pytest 188 全绿（+12 专项：估算器/折叠边界/纪要/摘要解析/记忆读写/分工具预算/循环级 AutoCompact/溢出自愈/记忆注入）、ruff 通过、npm build（tsc+字号门禁）通过；8720 重启（v23 迁移上真库）后真实 e2e——context_window 临时档案往返零残留、DeepSeek 真实两轮对话：台账即时落 memory_json、第二轮传干扰 history 仍凭服务端历史正确复述首轮问答、system 尾部确认注入「# 会话记忆」块；openapi/schema 快照再生

## ee2ffc9 — fix: 压测连环修——多账号搜索锁死主账号+DSML 全角变体泄漏+协议缓存污染
- 用户注入演练（run 33）实测打出三层连环：①多账号会话 search_emails/list_recent_emails/list_folders 默认 `account_id or primary` 锁死第一个账号（QQ 在前→主账号邮件永远搜不到，模型两轮 0 结果后靠 list_recent 兜底）——读类工具默认改全会话范围 IN 过滤（显式 account_id 仍优先，写类工具维持主账号默认不动）
- ②模型在 JSON 降级模式下把调用标记当文本输出且用**全角竖线｜**变体（`<｜｜DSML｜｜ invoke>`），防御正则只认 ASCII → 原文泄漏给用户——_INVOKE_BLOCK_RE 改全/半角+任意竖线数宽容匹配，另加任意包装 `invoke name="x"` 的 generic 兜底提取；解析失败的标记在最终回答层二次拦截（友好提示不原文下发）；原生协议系统提示词补「只能通过函数调用通道发起调用」
- ③根因链：run 25 的**请求内容类 400（配对 bug）被 _call_model 误判成「端点不支持 tools」→ 降级并永久缓存 native=false → 之后所有会话掉进 JSON 弱协议**——加两道守卫（已跑过一步=tools 通道是通的；报错提及 tool_calls=内容问题），如实抛错绝不污染协议缓存
- 回归：+4（全角 DSML 提取、标记泄漏拦截、内容 400 不毒化缓存、多账号作用域覆盖）；test_database 迁移计数顺手修正为 24（cf39666 漏更，HEAD 上即红）
- 验证：pytest 208 全绿、ruff 通过；并行会话 WIP（SCHEDULER_ALLOWED/v25/rule_proposals）按惯例外科手术避让未卷入；8720 重启 + agent_native KV 缓存重置（恢复原生协议探测）

## 76327f5 — fix: Agent 并行调用批遇审批暂停后续跑 400（压测发现）
- 用户压测任务 4 实测打出：模型并行发两个工具调用（丢弃草稿+重写草稿），第一个写类出审批卡即暂停——同批未执行的 call 没有 tool 回应；批准续跑只回灌了批准的那个，DeepSeek 严格校验 tool_calls 逐 id 回应，缺一即 400（"insufficient tool messages following tool_calls message"）
- 修复（agent.py resume_stream）：续跑前扫描暂停批（最后一个带 tool_calls 的 assistant），对未回应的 call 逐个补「因等待审批未执行已跳过，如仍需要请重新调用」的 tool 回应——模型可重新发起且仍走全部门控；预算暂停的批在追加 messages 前即被丢弃，天然无此问题
- 回归：test_parallel_calls_approval_resume_fills_siblings（并行批出卡→批准→续跑 sibling 补回应→配对完整断言）
- 验证：pytest 205 全绿、ruff 通过；8720 重启加载修复

## df9c86b — Agent 修复与简化：用户提问落库+极简过程行+提示词防猜账号
- 用户实测反馈三连修（8721 旧标签页/旧 bundle 造成的混淆一并厘清）：①「对话历史只剩 AI 的」——agent 流从 P6 起从不落库用户提问（仅 chat-manager 流落），刷新/重开后只剩 AI 内容且会话永远叫「新对话」：agent_stream 端点在流启动前 `require_session`+`ai_config_or_400` 后 `append_message(user)`（标题自动生成顺带生效）；②「审批内容不见了」——审批暂停轮的 segments 其实已落库，是旧 bundle 渲染不出（见下使用提示），另把该轮 content 兜底文案保留；③「写完草稿要有总结」——新代码批准/拒绝后自动续跑由模型收尾总结，旧实例/旧页面无此行为
- 过程展示极简化（Claude 式单行）：ProcessBlock 去边框块——运行中=「正在执行…（已 N 步）」spinner 一行、待审批=琥珀「待审批 · 已执行 N 步」、有失败=红色「N 步 · M 步失败」、全部成功=淡灰「已执行 N 步」；点击才展开步骤明细，默认不占版面
- 提示词补「不猜测或尝试其他 account_id」（用户单账号场景模型猜 id=2/3 被范围守卫拦、白耗两步——守卫行为正确，模型不应试）
- 使用提示：8721 为重复启动的顺延实例已停掉，统一用 8720；浏览器标签需强刷（Cmd+Shift+R）否则旧 bundle 渲染不出新格式
- 验证：pytest 176 全绿、ruff 通过、npm build 通过；8720 重启后 curl 实测——agent 会话用户消息落库+标题自动生成+assistant 带 segments
## 3eefdb5 — AI 总管家 Agent 化：原生工具调用+可恢复长链+人人对齐工具集+Claude Code 式过程展示（REDESIGN_PLAN §17，2026-09-14 拍板）
- 背景：P6 的 Agent 实测不可用——提示词约定 JSON 文本作工具协议（裸 JSON/DSML 标记泄漏给用户、`_extract_json` 首尾跨度被幻觉文本搅坏）、MAX_STEPS=8 且审批即断链、search_emails 锁死 INBOX 与描述不符、过程平铺无折叠
- 原生 function calling（ai/llm.py `chat_step`/`iter_chat_step` + ai/tools.py 每 tool JSON Schema）：tools 参数+tool_calls 解析，流式分片按 index 聚合；端点不认 tools（400/404/422）自动探测降级 JSON 协议并按 base_url+model 落 KV 缓存（`_parse_model_action`/DSML 兜底保留），原生模式下模型输出裸 JSON 也兜底解析；`_extract_json` 改首个平衡对象截取（止血）
- 循环 v2（ai/agent.py）：时间预算优先（180s，超限 tool_choice=none 强制文本收尾，仍调工具则 paused_budget），MAX_STEPS=25 兜底；**审批不断链**——写类出卡后 agent_runs（v22）持久化 messages/步数/预算置 waiting_approval，批准/拒绝经 decide 后 `POST /api/ai/agent/resume` 续跑（拒绝同样回灌让模型改道），步数/预算触顶前端「继续」=新的一段预算；工具结果紧凑回灌 ≤1200 字符（邮件列表转行格式），>12 步早期结果确定性截断；最终回答也回写 run messages；事件 run_started/text_delta/text/tool_call/tool_result/approval_required/paused/error/done（ext 非流式过滤 text_delta 并新增 /agent/resume）
- 工具集 15→26（ai/tools.py §17.3 人人对齐）：search_emails 增强（category/sender/unread/needs_reply/date_from/date_to/folder 过滤，修 folder=INBOX 硬编码默认全文件夹含归档，空结果带结构化 hint）+ set_category（带 undo）/rename_folder（带 undo）/delete_folder/update_draft/schedule_draft/discard_draft/upsert_contact/delete_contact/add_sender_list/remove_sender_list；豁免不给工具：账号/凭据/ai_grants/密钥/AI 总开关（防注入自我扩权）；自动模式 schedule_draft 一律降审批；undo_action 支持 set_category/rename_folder
- 前端 Claude Code 式（ManagerPage 重写 + api/stream.ts AbortSignal）：消息按 segments 渲染——流式 Markdown 文本 + 连续步骤合并的可折叠「执行过程」块（运行中自动展开当前步、完成自动收起、行点开看参数明细、中文工具名映射、ok 步撤销钮）+ 审批卡独立醒目（delete_folder/trash 显示影响邮件数与清单）+ 错误内联红条；批准/拒绝后自动续跑；「继续」按钮（步数/预算触顶）；Stop 按钮（中断保留已完成部分）；会话还原走 chat_messages.segments_json（v22），旧消息回落纯文本
- 数据库 v22：agent_runs 表 + chat_messages.segments_json 列
- 验证：pytest 176 全绿（+11 循环用例：原生流式/审批续跑/拒绝改道/步数预算暂停继续/裸 JSON 兜底/segments 构建/归档搜索/set_category undo 往返）；ruff 通过；npm run build（tsc）通过；8720 重启迁移后 curl 实测——读类问题全程流式+工具调用正常（原生 call_id）、审批 paused→reject→resume 模型改道完成、重复 resume 正确拒绝；浏览器 e2e——「有没有我漏回的邮件」单轮 5 步结构化过滤（needs_reply=true）而非同义词乱搜、过程块折叠/展开/会话还原、审批卡批准→自动续跑收尾；ext 非流式 answer/approvals 兼容
- 文档：REDESIGN_PLAN 新增 §17（方案全文+拍板记录）、ARCHITECTURE 相应条目更新

## 11f4be2 — 设置页补全：通知开关/写信分类/黑白名单管理/本机路径
- 用户确认方案：通知开关收进「通用」，新增「写信」分类，黑白名单管理做，暗色/免打扰不做，「关于」显示数据与安装目录（不硬编码、符合实际运行环境）
- 通知（api/settings.py + NotificationBell.tsx + SettingsPage 通用页）：新增 `desktop_notifications_enabled`（默认开）与 `notify_types`（new_mail/ai_draft/digest/account_error 四类，读侧与默认合并缺省视为开，未知键过滤、空 dict 不落库）；铃铛弹系统通知前按总开关+类型过滤（应用内铃铛与角标不受影响），设置页常驻浏览器权限状态行（未授权可申请/被拒绝给浏览器设置指引——替代原授权后无处可管的琥珀色一次性按钮）
- 写信分类（SettingsPage 新组件 + ComposeContext）：签名/模板管理复用写信台弹窗（同源 compose-extras，签名卡按账号显示已设/未设）；新增 `auto_insert_signature`（默认关）——开新写信标签时注入该账号签名一次（openNew 预置正文、openReply 插引用块之前 Gmail 惯例、转换失败回退空正文），草稿恢复/AI 拟稿不重复注入
- 黑白名单管理（SettingsPage `SenderListsPanel`，通用页）：白/黑/图片信任三列 chip 管理——查看/回车添加/× 移除，复用既有 sender-lists API 与邮件右键菜单同一数据源（此前误拉黑无处解除）
- 本机路径（api/system.py `/api/system/paths` + config.py `get_install_dir` + 关于页）：数据目录（get_data_dir 实时取，含 NMAIL_DATA_DIR 重定向提示）与安装目录（冻结=可执行目录/源码=仓库根与版本号同判定/wheel=app 包目录）均运行时解析零硬编码；展示「纯本地应用」说明与复制按钮
- 验证：ruff 通过、pytest 164 全绿、npm run build（tsc+字号门禁）通过；8720 重启后 curl 实测——settings 三键读写往返/部分合并/未知键过滤/空 dict 语义、paths 返回真实目录、sender-lists 增删往返；独立 headless Chrome 对真实实例 18 项 UI 断言全过（开关联动禁用、API 落库复原、名单增删复原、弹窗复用、路径与 API 一致）；真实数据自动签名——新邮件 e2e 3/3（预置签名+ephemeral 关闭零落库），回复 e2e 被并行会话 user_drafts WIP 500 阻塞（见下），拼接逻辑以真实签名数据单测 3/3（引用块前/完整/光标锚点）
- 遗留：①回复自动签名完整 UI e2e 待草稿会话修好 create_draft 响应序列化（`_get_draft` SELECT 无 JOIN 而 `_draft_dict` 读 `row["email_subject"]`，in_reply_to 非空即 IndexError 500，HEAD dd8c0a9 可复现：POST /api/user-drafts mode=reply）后补验；②桌面通知按类型细分待用户真实开一天感受粒度；③openapi 快照已随本轮再生，含写信保真会话 sanitize-html/preview（其遗留第③项一并清）
- 并行协调：client.ts/openapi/schema/CHANGELOG/SESSIONS 与草稿删除、写信保真两会话重叠——构造 patch 只暂存本会话 hunks；ARCHITECTURE 仅更新 settings/system 两行（该文件另有他人未提交改动，不卷入）

## 0e08eb5 — fix: 回复草稿单条路径 500（_get_draft 漏 JOIN）
- S-0913-1634 设置页会话发现的 dd8c0a9 回归，用户指派修复：`_draft_dict` 读 `email_subject/email_sender_name/email_sender_email/email_date/email_snippet` 五列（列表接口经 `_DRAFT_JOIN` 提供），但 `_get_draft` 是裸 `SELECT * FROM user_drafts`——凡 `in_reply_to` 非空的草稿（回复/转发），创建响应、详情、更新、定时、撤销、恢复、排队等全部单条路径一读即 IndexError 500（mode=new 因 `row["in_reply_to"]` 短路幸免，故仅回复场景暴露）
- 修复（api/user_drafts.py）：`_get_draft` 改用文件内既有 `_DRAFT_JOIN` + `WHERE d.id = ?`（LEFT JOIN 引用邮件，与列表同源；引用邮件被删时 email 上下文安全降级 null 不报错）
- 回归用例（tests/test_user_drafts.py）：回复草稿创建/详情/更新三态 200 且 email 上下文正确 + 引用邮件删除后 email=null 兜底
- 验证：pytest 165 全绿（+1）、ruff（app 口径）通过；8720 重启后以当初精确复现请求实测 200；真实数据 UI e2e——回复自动签名完整链路随之打通（编辑器打开、签名位于引用块之前、测试草稿零残留），新邮件路径 4/4
- 并行协调：验证期间主树 dist 曾被并行会话「提交前隔离构建」覆盖（bundle 缺 auto_insert_signature），已重新整体构建（现 dist 为全量 HEAD）

## 137d448 — UI: 写信表格编辑补全——列宽拖拽+右键行列增删/合并拆分/表头/底色，链接弹窗与跨平台字体栈
- 用户确认方案 P1：表格此前只能插 3×3 和整表删除（resizable:false），行列增删/合并/宽度全没有，写错只能删表重来
- 表格编辑（RichEditor.tsx）：resizable:true 列宽拖拽（TipTap 原生以 colgroup/col width 落盘，发送白名单已在 c053662 预放行，拖拽手柄 CSS 既有）；表格区域右键菜单（复用 ContextMenu 组件）——上/下插行、左/右插列、切换表头行、合并/拆分单元格（当前选区不可用时置灰）、单元格底色（6 浅色+清除，经 TableCell 扩展的 backgroundColor 属性以内联 style 落盘，收件端可见、草稿往返保真）、删除行/列/表格（红色危险项）；右键先以 posAtCoords 把光标落进所点单元格再弹菜单，表格外区域保留原生菜单（复制粘贴不受影响）
- 链接：window.prompt 升级为弹窗——地址规范化（缺协议补 https、mailto 保留）、Enter 提交、编辑态含「移除链接」
- 字体栈跨平台：苹方与微软雅黑互为回退，宋体+Songti SC、黑体+Heiti SC、楷体+Kaiti SC——macOS 侧写作不再整体回退默认字体，收件端同理
- 验证：主树 npm build 因并行会话 SettingsPage/NotificationBell WIP 暂不可用（非本会话文件）——隔离 worktree（HEAD dd8c0a9 + 本改动）lint:font + tsc --noEmit + vite 全绿；后端零改动
- 遗留：用户真机走查右键菜单与列宽拖拽；主树待并行 WIP 完成后补一次整体构建

## 61af1e2 — feat: 写信输入增强——粘贴 Markdown/截图自动处理、HTML 源码视图、收件人视角预览
- 用户确认方案 P2 收尾段
- 粘贴增强（RichEditor.tsx）：①剪贴板截图→内嵌 base64 图（超 1.5MB 提示改附件，与图片按钮同参）②无富文本版的纯文本若命中 Markdown 结构特征（标题/列表/引用/围栏/表格/加粗/分隔线，≥2 处且占非空行多数——单行与普通段落不误转）→ 走既有 /markdown 接口转换插入，失败回退普通文本；富文本 HTML 粘贴不受影响
- HTML 源码视图：工具栏 FileCode 按钮，查看/贴入源码，应用前经新端点 POST /api/compose-extras/sanitize-html 白名单消毒（与发送消毒同口径，脚本/事件属性/javascript: 进不来）
- 收件人视角预览：写信台底部「预览」按钮 → 新端点 POST /api/compose-extras/preview（sanitize → decorate → wrap，与 outbox.send_user_draft 发送管线完全同参）→ 沙箱 iframe 渲染——发送前即见收件人所见，是 c053662 内联化的长期保险
- client.ts 增 sanitizeComposeHtml / composePreview 两方法（手写 REST，无 schema 类型依赖）
- 验证：pytest 164 全绿、ruff 通过；隔离实例（8794）curl 往返——preview 输出含内联化表格样式、sanitize-html 剥 script/onclick；主树 npm build 因并行会话 SettingsPage/NotificationBell WIP 暂不可用（非本会话文件）——隔离 worktree（HEAD e7283ef + 本改动）lint:font + tsc + vite 全绿
- 遗留：openapi.json/schema.d.ts 快照未再生（并行会话 settings/system API WIP 在途，避免卷入其端点）——随下一轮 API 快照再生统一补；后端需重启进程生效；真实账号发信目检预览一致性待用户

## c680a72 — fix: 取色 popover 点外/Esc 关闭
- 用户反馈：取色浮层点空白处无法取消，不是基本 UX
- 修复（SettingsPage）：打开期间 document 级 mousedown 监听——点击 popover 容器外即关（先于其他元素的 click 生效，不影响他处交互）；另加 Escape 关闭；触发按钮在容器内不受影响
- 验证：npm run build 通过；headless Chrome 断言 开=1 → 点外=0 → 重开 → Esc=0

## c053662 — fix: 写信发送保真——高亮/表格/段距等样式内联化到收件端
- 用户反馈与实证：写信编辑器的高亮发出去即变裸文本（`mark` 不在发件消毒白名单，nh3 剥标签留文本，后端消毒函数实测复现）；表格边框/表头灰底只存在于编辑器本地 CSS（.ProseMirror），收件人收到的是无边框裸表格；段距/引用/代码块/标题观感全依赖收件方客户端默认样式，与编辑器所见不一致（Gmail 段落默认 1em vs 编辑器 0.35em 等）
- 后端（mail_html.py）：① `mark` 入 `_ALLOWED_TAGS`（收发双向同套白名单，高亮保真），顺带放行 col/colgroup+width（表格列宽预放行）② 新增 `decorate_outgoing_html`——发送前把与编辑器同参数的样式写进内联 style（p margin:0 0 1em、h1–h3 字号字重边距、blockquote 竖线、pre/code 等宽字体与底色、table border-collapse + td/th 边框内边距 + th 灰底加粗、img max-width、hr），li 内段落 margin:0 不撑行距；用户已有内联样式在后追加、同名声明后者生效（兜底不覆盖显式设置）③ `html_to_plain_text` 表格单元格补空格分隔（原"表头A表头B"粘连不可读）
- 发送管线（outbox.py）：sanitize → decorate → wrap 三步；纯文本 alternative 由装饰后 HTML 派生
- 前端（index.css）：编辑器与 AI 预览段距 0.35em 0 → 0 0 1em，与发送内联样式同参（所见即所发）；mail_html.py 内注释标注三处同参需同步
- 测试：pytest 164 全绿（+7：mark 保真回归/表格段落内联化/既有样式保留/引用代码块/发送管线端到端/纯文本表格分隔等）；ruff + npm run build 通过
- 遗留：后端改动需重启 python run.py 生效；Outlook 桌面版（Word 引擎）不渲染 data: URI 内嵌图的 cid 化改造随 P2 预览一起评估

## dd8c0a9 — feat: 草稿页全页签可删 + 撤销浮条 + 已发送/已丢弃一键清空
- 用户反馈：草稿页「已发送」没有删除入口，历史只增不减（列表 LIMIT 200 之外的旧记录不可见也删不掉）。排查：后端 `DELETE /api/user-drafts/{id}` 本就支持任意状态，纯前端条件把 sent 排除在外
- 前端（DraftsHubPage）：已发送补行尾+详情删除入口（行尾提示「删除记录（不影响已发出的邮件）」——真实邮件在服务器 Sent 文件夹，删的只是本地发送历史）；所有删除改 Gmail 式乐观删除 + 5 秒撤销浮条（替代确认弹窗；待审保持两步：丢弃→已丢弃→删，人在回路）；已发送/已丢弃页签底部加「清空」按钮（两击确认，首击变红 3 秒内再击执行）
- 后端（user_drafts.py）：新增 `DELETE /api/user-drafts?status=sent|discarded` 批量清空（仅两个终态开放，在途状态 400；附件磁盘目录随清同步删除），解掉 LIMIT 200 隐形堆积
- 测试：后端 pytest 全绿（含新增批量清空用例）；ruff + tsc/vite build 通过；8720 重启后 chrome-devtools 真实实例实测——已发送行尾/详情删除、撤销浮条出现与行恢复、超时落定、清空两击全链路断言通过；批量清空另在隔离数据目录实例验证（只动自建记录，用户 3 条真实已发送全程无恙）

## f426d7b — UI: 树内账号状态指示改 Outlook 式红!角标
- 用户反馈两轮：先嫌展开树「标识色点+绿色状态点」两颗球扎眼（正常态绿色零信息量），再明确要求异常直接冒感叹号（Outlook 式），不要再出现多个色球
- 定稿语义（FolderTree 展开行+折叠头像统一）：正常=无任何状态标记（只剩标识色一颗球）；同步中=琥珀脉动小点；未同步=灰点；授权过期/连接异常=红底白!角标（展开行右端 ml-auto、折叠头像右上角标，title 带状态详情）——「有感叹号=有事」一眼可辨
- 验证：npm run build 通过；sqlite 临时置一账号 auth_error 截图实证红!角标（展开行右端+折叠头像角标）后复原 ok；正常态五账号单球无标记

## 2ac650d — UI: 账号标识色自定义（12 色板）+ 折叠头像与树行染色
- 用户反馈：颜色是区分邮件/账号的重要手段，但设置页不允许自定义颜色，且折叠侧栏首字母头像不上色——排查：颜色本就是 accounts 表字段（创建时按 COLOR_PALETTE 轮转赋初值），只是 PATCH 接口与设置页从未开放；折叠头像在 FolderTree 写死灰底/靛底，没读 a.color
- 后端（accounts.py）：AccountPatchIn 新增 color（限定调色板内取值，否则 400）；色板 8→12 色（+blue/orange/lime/fuchsia 500 系，OAuth 建号轮转同源）；改色不触发试连直接落库（颜色不影响连通性）
- 前端：新增 utils/accountColor.ts——色板常量（色相序展示）+ Tailwind 浅底深字映射（100/700，激活档 200/800，对比度全过；调色板外取值回退灰兜底）；设置页账号卡标识色点变可点按钮，弹出 4×3 取色 popover（当前色描边+打勾，被其他账号占用的色减淡提示「仍可选用」——账号数超色板数时必然重复，不做禁用；即点即存）
- 染色联动：折叠侧栏首字母头像按账号色浅底深字（激活加深一档，右上状态角标语义不变）；展开态账号行在状态点旁加标识色点；邮件列表/读信/摘要的账号色点均为查询时 join，改色后自动跟随
- 测试：pytest 账号 API 4 全绿（+1：色板内落库且不触发试连、色板外 400 且不改值）；ruff + npm run build 通过
- 验证：8720 重启后 curl 实测 PATCH 往返与非法值 400（np25 真实账号，改后复原）；chrome-devtools 实测取色 popover 交互、点色即存即变、折叠头像五账号五色染色、激活档加深

## 36583ad — UI: 固定分栏全部可拖拽 + 页签拖拽排序（浏览器式）
- 用户反馈：树|列表、阅读区|AI 助手、草稿分类列三条竖线都不能拖，要求「浏览器的思想」——竖线可拖、页签也可拖
- 分栏基建（新增）：`hooks/usePanelWidth`（localStorage 记忆 + clamp + persist/reset；widthRef 在 setWidth 内同步更新——React 18 连续事件下 mousemove 紧跟 mouseup 时渲染可能未提交，persist 不丢最后一步）+ `components/SplitDivider`（bar=1px 视觉线±6px 热区 / edge=浮层边缘透明热区两形态，hover/拖拽中靛蓝高亮，双击复位，全局光标与禁选中沿用 body.dragging-col）；列表|阅读区原分隔条重构到同一组件（行为不变，热区更明显）
- 四处固定分栏接线：文件夹树 160–360px（默认 192=原 w-48；折叠图标栏不参与；展开态根元素改 fragment、child0 仍为 aside 保 DOM 复用与折叠过渡动画）、AI 助手浮层 320–640（默认 384=原 w-96，edge 热区拖左缘）、草稿分类列 240–440（默认 320=原 w-80）、AI 总管家会话栏 180–360（默认 224=原 w-56）
- 页签拖拽排序（落地 §3.2 既有增强项）：统一顺序源 `sessionStorage.nmail_tab_order`（`page:<路由>`/`compose:<tabId>`；缺失剔除、新开按打开序追加尾部），「邮件」基座钉死首位不在序列；HTML5 dnd（dragover 目标页签前/后半段→插入点）+ 左缘 2px 插入指示线 + 拖拽中源页签半透明 + 页签条空白处放置=追加尾部；中键点击页签=关闭（浏览器习惯）
- 验证：npm run build（tsc+字号门禁）通过；隔离 headless Chrome（独立 profile）对 8720 真实实例 15 项断言全过——五处分隔条拖宽/落盘无最后一步丢失/双击复位/刷新记忆、页签换位（页面页签置前+写信页签跨组插入）/中键关闭/顺序落 sessionStorage/刷新保留；AI 面板以已读邮件打开验证（零服务器变更）；headless CDP 不合成原生 dblclick，双击复位经合成事件验证 onDoubleClick 路径（与原列表分隔条同机制）

## 12fa0b2 — fix: 邮件显示三修——正文基础字体、追踪像素隐形、放行 style 标签
- 用户反馈：邮件显示「怪怪的」且底部有裂图——排查：无样式 HTML 邮件正文落在浏览器默认衬线字体（宋体观感，仅页脚有自带字体正常）；裂图实为阿里云 1×1 追踪像素（ac.mmstat.com）被浏览器反追踪拦截的残留图标，图片本身加载正常（关闭拦截生效，remote_blocked=0）
- ①正文基础样式（HtmlMail.tsx）：srcdoc 注入 `body{font-family:sans 栈;line-height:1.65}`——仅兜底继承，邮件自带 font-family/line-height 不受影响；与发信方向 wrap_email_body_html 同栈，收发观感一致
- ②追踪像素优雅降级（mail_html.py）：放行远程图时声明尺寸≤2px（width/height 属性或内联样式）置 display:none；缺 alt 的远程图补空 alt——被浏览器反追踪拦截时不再显裂图（headless Chrome 实测：alt="" 失败图零渲染、无 alt 显裂图、1×1 声明不可见）
- ③放行 `<style>` 标签（mail_html.py）：nh3 默认把 style 连内容整体剥离且不支持白名单放行（tag 与 clean_content_tags 同现即 panic），改为先摘出 CSS、按远程图片口径清洗后注回（bs4 对 style 内容原样输出不转义，`</style>` 逃逸已防）；拦截口径同步剥 style 属性里的远程 url()（nh3 本不清洗属性内容，属既有追踪通道）与 @import，data: 内联保留
- 测试：pytest 156 全绿（+8：style 保留含子选择器/拦截剥 CSS url 与 @import/style 属性 url/像素隐形/alt 补齐/逃逸守卫/无 style 零影响等）；ruff + npm build 通过
- 验证：8720 重启后真实邮件（阿里云云盾 id 210）chrome-devtools 实测——邮件自带 `<style>` 链接色生效、正文黑体 16px×1.65、追踪像素 alt="" 加载后 1×1 不可见（被拦截亦不显裂图）、二维码/logo 照常；拦截态占位符与合成 CSS 剥离用例全过

## 5622630 — fix: AI 回复长链接溢出气泡——Markdown wrap-anywhere 任意断行 + 三处容器 min-w-0
- 用户反馈：邮件内点开 AI 助手，回复里的长 URL/邮箱地址戳出灰色气泡——根因：渲染链路无任何 overflow-wrap/word-break（全局 break-word 只覆盖写信编辑器），浏览器默认仅在空格/连字符处断行，URL 的 / . ? 均非断点，不可断词溢出气泡右缘（8721 实测 ~36px）
- 前端：Markdown.tsx 输出包一层 wrap-anywhere（overflow-wrap:anywhere，可继承全后代，URL/长词任意断行兼收缩 min-content）；AiPanel 助手/用户气泡、ManagerPage 总管家用户气泡/消息容器补 min-w-0 防御（实测 flex item 未突破 max-w，防御无副作用）
- 影响面：Markdown 三个使用方（邮件 AI 助手 / AI 总管家 / 每日摘要 AI 综述）一并治好
- 验证：npm run build（tsc+字号门禁）通过；8721 真实 AI 回复端到端——长邮箱地址气泡内正常断行、文字零溢出（修复前 +36px）、气泡 316px 恰为 max-w-[90%] 上限、面板无横向滚动

## 4b1f38b — fix: HTML 邮件正文只剩上半截——iframe 测高链路不再依赖 onLoad
- 用户反馈：Google 安全提醒邮件只显示到按钮上半截（8721 实测复现：iframe 内联 style 卡在初始 320px 而内容实际需 869px；屏显 358 = 320×1.12 界面缩放）——库里 HTML 完整、消毒后完整，纯前端渲染问题
- 根因：React 18 对 srcdoc iframe 的 onLoad 竞态——load 先于监听挂接被触发而错过（srcdoc 解析极快；实测 style 卡死 320px 超 9s、handleLoad 从未运行，即 remeasure/ResizeObserver/兜底定时器全部未注册）。高度自适应整个失效，是否自愈全凭后续 srcDoc 变更（设置加载改 zoom 触发重载）碰巧再触发一次 load 的时序运气
- 前端（HtmlMail.tsx）：测高注册与 onLoad 解耦——挂载后独立轮询（100ms×50）至 contentDocument.body 就绪即完成测量+ResizeObserver+定时兜底注册；onLoad 仅作提前触发；换邮件/字号档位会整文档重载，effect 依赖 html/zoom 随之重跑
- 验证：npm run build（tsc）通过；8721 强刷实测——修复前 style 卡 320px 无任何更新，修复后 0.5s 内 893px（=内容 869+24）到位且稳定；切换微软邮件复测 919/943 同样正常


## f209575 — UI: 设置页内部文档路径改为官网文档链接
- 用户反馈：设置页出现内部仓库路径（API 区「隧道配置示例见 docs/对外API使用指南.md」、OAuth 区「见项目仓库 docs/OAuth2 使用指南.md」）——对普通用户无意义且暴露内部结构
- 前端（ExtApiSection.tsx / OauthSettings.tsx）：两处内部 .md 路径全部改为官网文档链接（nmail.whizzzest.com/docs/api/、/docs/oauth/），新标签打开，样式沿用站内链接惯例
- 文档：docs 站 slug 映射（nmail-site/scripts/sync-docs.mjs）确认对应关系 api/oauth
- 验证：npm run build（tsc+字号门禁）通过

## 213eb49 — UX: 新用户初始化定版——页签会话级归零 + 默认设置 + 正文字号与界面字号解耦
- 用户定版新用户初始化三件事：①页签栏初始化只见「邮件」——页面页签记忆 localStorage 改 sessionStorage（浏览器行为：应用内刷新保留，关闭浏览器标签页/退出应用后归零重见基座；写信页签本为内存态，行为不变）②默认设置对齐——轮询 5→1 分钟、每日摘要 08:30→07:00、界面字号 compact→large、通讯录自动采集开启→关闭（DEFAULT_SETTINGS 仅 get_setting 回退用，老用户已存值不受影响）③正文字号三档与界面字号解耦——HtmlMail 注入沙箱的 zoom 原先与全局缩放相乘（紧凑 0.85 × 小 0.85 = 0.72，「都调小」时邮件正文仅原大 72%，且紧凑界面下正文档选「标准」也到不了原始大小）；改为除以界面档位后，小/标准/大 = 邮件原始字号的 0.85/1/1.15，与界面档位无关
- 后端（api/settings.py）：DEFAULT_SETTINGS 四项对齐新用户默认
- 前端（Layout.tsx / HtmlMail.tsx / SettingsPage.tsx）：页签存储换 sessionStorage；BODY_ZOOM 除以 UI_ZOOM 镜像表（与 index.css 三档 --app-zoom 对应）；设置页 useState 初始档位同步新默认（防加载前闪旧值）、通讯录开关回退值改 false
- 文档：REDESIGN_PLAN §3.2 页签记忆改会话级并写入新用户初始化规定
- 验证：pytest 149 全绿、ruff + npm build 通过；隔离 NMAIL_DATA_DIR 实测新库四项默认值；8720 重启后 chrome-devtools 走查——新会话页签栏仅「邮件」、开设置后刷新页签保留、关浏览器标签页重开归零；字号解耦实测 large×standard 注入 zoom=1/1.12（视觉缩放恰为 1，正文恒原大；紧凑档同代码路径）


## 6d45487 — fix: OAuth 令牌丢失致标已读静默失败——secrets 写入加锁 + 失败出声 + 丢凭据可见
- 用户反馈：点开一封邮件查看后依然亮着未读——排查定案：4 个 Outlook OAuth 账号的 `oauth_token:*` 已从 secrets.json 物理丢失（`set_secret` 无锁读改写整文件，并发写互相覆盖丢键，secrets.json 停在昨天 17:45 只剩 `account_pwd:1`）；调度器对这四个号以 no_credentials 静默跳过 24 小时（账号状态仍 "ok"）、批量已读在 `load_account` 处失败返回 HTTP 200 `{ok:false, failed:1}`（本地按「服务器成功才动本地」不动，20s 轮询把行翻回未读），前端对 ok:false 无任何提示——用户全程无感。清华账号（密码型）不受影响，昨日的 FLAGS 对账验证即在该账号
- 后端①（security.py）：`set_secret` 读改写加模块级 `threading.Lock`——同步线程刷新 OAuth 令牌 × API 线程存设置的现实并发不再互相覆盖（原子替换只保「文件不损坏」，不保「键不丢」）
- 后端②（sync.py）：`start_sync` 对缺凭据的 OAuth 账号置 `auth_error`（"OAuth 授权丢失，请重新授权"）并发一次通知中心消息（沿用状态迁移去重）——不再静默跳过；授权恢复后首次成功同步自动回 `ok`
- 前端（MailBrowser）：批量已读返回 `ok:false/failed>0` 时提示「已读标记失败：账号连接异常，稍后恢复真实状态」，成功才失效 folder-cache 徽章
- 文档：ARCHITECTURE 安全模型 secrets 行与 core/sync 行同步
- 验证：pytest 149 全绿（+2：OAuth 缺令牌置 auth_error 且通知只发一次 / 密码账号缺凭据维持静默）、ruff + npm build 通过；用户当轮完成 4 个 Outlook 账号重新授权，四账号恢复同步；对此前失败的账号 3 邮件 241 实测 batch-action 已读 `{ok:true, failed:0}` → 本地翻正、Inbox 徽章归零（服务器 \Seen 已推）；auth_error 置错路径由用例覆盖


## 3f9c898 — UI: 标签条品牌区 + 汉堡折叠文件夹树（Gmail 式）
- 用户反馈：左上角 N 图标不醒目且不在中心位置——原是塞在页签条开头的 16px favicon（`mb-1.5 self-center` 对齐 hack 夹在窗口边缘与页签之间）
- 品牌区：标签条最左改为「汉堡按钮 + 24px N logo + Nmail 字标」，整区垂直居中（撤销对齐 hack）；点标识回邮件基座；品牌区与页签间加竖分隔线
- 汉堡折叠（Gmail 主菜单心智，导航模型不变——决策 7 仍成立，折叠的是基座内文件夹树非应用侧栏）：w-48 完整树 ⇄ w-14 图标栏——收起态智能视图/页面入口变纯图标（tooltip 带名称、未读/待审徽章缩角标圆点、AI 入口 Sparkles 保留紫调），账号变首字母圆形头像（状态色角标，点直达该账号收件箱），分组标题隐藏；文件夹层级与拖拽落点仅展开态可用（预期取舍，Gmail 同）
- 状态与联动：`hooks/useSidebar.ts` 新增——localStorage（`nmail_tree_collapsed`）记忆 + useSyncExternalStore/自定义事件，汉堡（Layout）与树（MailPage）免 Provider 联动，跨页签/刷新保留；其他页签点汉堡先跳回邮件基座再切换；两分支根元素同为 `<aside>`，React 原地复用 DOM，`transition-[width]` 平滑过渡
- 文档：REDESIGN_PLAN §3.2 示意图 +「品牌区与折叠侧栏」条目 + 涉及文件追记
- 验证：npm run build（tsc+字号门禁）通过；chrome-devtools 在 8720 真实账号走查——展开态品牌区居中醒目、收起态图标栏+首字母头像+状态角标、刷新后收起记忆保留、再展开恢复正常（devtools profile 起初被并行会话占用，释放后走查）

## c6127db — fix: 未读/星标与服务器 FLAGS 对账——外部客户端的已读变化不再丢失
- 用户反馈：邮箱里邮件都看完了，INBOX 徽章仍显示 22——根因是已读状态「只出不进」：增量同步按 UID 水位只拉新邮件、从不回读服务器 FLAGS，新邮件入库（INSERT OR IGNORE）也不记录 FLAGS，Thunderbird/网页/手机上的已读变化永远到不了本地；徽章取自本地 `is_read=0` 计数（folders.cached_list），故与真实状态脱节。次因：在 Nmail 内读信后，合并的批量已读成功时不刷新 folder-cache，树徽章要等下次同步等事件才动
- 后端（core/sync.py + core/imap_client.py）：①`_sync_folder` 增量拉取完成后加 FLAGS 对账——`UID SEARCH UNSEEN/FLAGGED` 各一条命令，与本地该文件夹全部行比对，只翻 is_read/starred 有差异的行；SEARCH 失败整段跳过，不影响同步主干 ②`ParsedMessage` 携带 flags，新邮件入库即按服务器 \Seen/\Flagged 初始化 is_read/starred（堵「别处已读后才同步到的新邮件仍显示未读」）
- 前端（MailBrowser）：800ms 合并的批量已读成功后 invalidate `['folder-cache']`——在 Nmail 里读完徽章即时归零
- 文档：ARCHITECTURE 同步管线与 core/sync 行同步新机制
- 验证：pytest 147 全绿、ruff + npm build 通过；真实账号（清华邮箱）端到端——最新一封在 Nmail 标未读（徽章 1）→ 仅服务器侧 IMAP 标回已读（模拟 TB/网页读信）→ 触发同步后本地 is_read 翻正、徽章即时归零；8720 常驻进程已重启加载新代码


## c6127db/e4ea306 — UX: 写信每次必新开一封，新邮件按钮 ＋ 改笔形
- 用户反馈：点标签条 ＋ 只能写一封新邮件——根因是 `openNew` 对「未落库空白标签」做防连点复用（再点只激活不新开）；该顾虑已被懒持久化化解（空白页签不落库，连点零成本），删除复用逻辑，**每次点击必新开一封**（Gmail 心智）；键盘 C、通讯录「写信」等全部入口一致
- 前端：标签条新邮件按钮 ＋ 改 SquarePen 笔形（纸上一支笔，写邮件标准隐喻；与写信页签的 Pencil 区分「新建动作」），title/aria 仍为「新邮件」
- 回归修复：多开后每次切标签都会卸载前一个表单，其卸载兜底保存会把**从未编辑**的空白页签落成空草稿（多开前复用逻辑掩盖了该路径）——ComposeForm 卸载兜底改为仅在有未同步编辑时保存；显式「保留草稿」路径不变
- 文档：REDESIGN_PLAN §3.2 示意图与「写信页签」条目同步
- 验证：npm run build（tsc+字号门禁）通过；chrome-devtools 在 8720 真实账号实测——连点 ＋ 开两封、切回基座零落库、编辑自动保存后切走切回内容不丢、空白页签关闭无确认无落库；中间版本曾按旧卸载兜底落了 5 封空草稿，已确认全空并删除；dev server 代理下 POST 被 Origin 校验拦（9ab675a 预期行为，非本次回归）
- 备注：本会话（S-0913-1420）改动经并行会话提交卷入 c6127db（compose 两文件）与 e4ea306（Layout/文档）入库，条目哈希按实际入库提交标注

## 5c58628 — fix: 代理状态行实时化 + 彻底删除手动代理地址
- 用户反馈：状态行「当前直连」疑似写死，要求开了代理能实时看到；「手动指定代理地址」折叠项仍会困惑人，彻底删除
- 状态行实况：数据本就每次 GET 实时探测（urllib.getproxies），但页面不自动刷新——设置页加独立 3s 轮询查询（与主设置查询隔离，不重置表单），系统代理开关一变，状态行几秒内自动显示「当前经 … 连接 / 直连」
- 删手动地址：netproxy 移除 `PROXY_SETTING_KEY/proxy_url_setting`，`effective_proxy_url()`=纯系统探测；settings API 移除 `network_proxy` 字段与校验（GET 只读 `detected_proxy/effective_proxy` 不变）；前端删折叠项与 proxyUrl 状态；types/openapi 同步
- 文档：使用指南/FAQ/OAuth2 指南统一为「跟随系统代理，工具须开系统代理模式」口径；ARCHITECTURE 两行同步
- 验证：pytest 147 全绿（test_netproxy 全面改探测打桩：resolve/httpx/OAuth 回退/设置只读字段）、ruff + npm build 通过、openapi 快照再生
- 遗留：代理工具不开「系统代理」模式时 Nmail 感知不到（与浏览器一致），文档已写明；真实 Gmail 端到端待用户验证


## 7797bf6 — UX: 树「草稿」升级为页面页签 + 页签缩窄
- 用户反馈：①点树「智能视图 ▸ 草稿」不出独立页签，不合理——同列的 AI 总管家/每日摘要都会开页签；②页签太宽（w-44=176px），一排放不下几个
- 前端（页签化）：`/drafts` 从重定向改为真实路由渲染 DraftsHubPage，纳入 PAGE_TABS 机制（点开即留、去重、可关、localStorage 记忆；AI 停用时手写稿仍可用，不属 AI-only）；树「草稿」改走 openPage，页签激活时树隐藏（与其他页面一致）；`TreeSelection` 删 drafts 分支；旧深链 `/?view=drafts` 在 MailPage 就地重定向兜底，`/mydrafts` 改指 `/drafts`；通知铃「草稿汇总」与阅读器「拟稿完成跳转」两处深链同步改
- 前端（缩窄）：页签统一宽度 w-44→w-36（144px）、px-3→px-2.5、gap-1.5→gap-1——文字区约 86px，「每日摘要」「AI 总管家」等固定标签完整显示，写信页签长标题照常 truncate 不溢出；「所有页签统一宽度」原则不变
- 文档：REDESIGN_PLAN §3.2/§3.3/§3.4/§5.1 同步修订
- 验证：npm run build（tsc+字号门禁）通过；curl 实测 /drafts SPA 兜底 200；浏览器走查因 chrome-devtools 被并行会话占用未跑，待用户强刷 8720 走查

## 3c64111 — fix: 代理改「跟随系统、零开关」——撤掉内部总开关按钮
- 用户反馈（对 182f934 的纠正）：设置页仍有「已关闭」代理开关——「浏览器难道会有这样的代理开关按钮吗？」正常软件是系统有代理就自动走、没有就直连，内部零开关；上一轮把实现细节（Python 不会自动认系统代理）漏成了一颗要用户理解的开关，本质还是内部设置
- 后端：netproxy 撤总开关——`effective_proxy_url()` = 手动地址（`network_proxy`）→ 系统探测（urllib.getproxies），没有即直连，无任何门控；settings API 移除 `network_proxy_enabled`，GET 增只读 `effective_proxy`（实际生效通道，与 `detected_proxy` 一起供状态行展示）
- 前端：设置页代理区改为纯状态行（「自动跟随系统代理，无需设置——当前经 X 连接 / 直连，未检测到系统代理」），零控件；手动地址退到 `<details>` 折叠的「手动指定代理地址（一般不用）」，仅代理工具未开系统代理等例外场景使用；types/openapi schema 同步
- 文档：使用指南/FAQ/OAuth2 指南/ARCHITECTURE（含上轮漏改的 netproxy 行）统一为「跟随系统」口径
- 验证：pytest 147 全绿（test_netproxy 撤开关契约，新增手动地址优先于系统探测断言）、ruff + npm build 通过、openapi 快照再生
- 遗留：语义变化——系统代理开启时所有账号自动走代理（用户拍板的浏览器语义）；真实 Gmail 账号端到端待用户验证


## 6484ae9 — fix: 右键菜单弹出位置偏移、贴边不保证可见（全局 zoom 坐标换算）
- 用户反馈：右键（通讯录/邮件列表/文件夹树）菜单弹出位置明显偏离鼠标；贴近视口底边/右边时不自动收进来，菜单被窗口裁掉
- 根因：界面全局缩放 `body>#root { zoom: var(--app-zoom) }`（0.85/1/1.12 档）——`e.clientX/Y` 是视觉 px，而 zoom 子树内的 fixed 定位坐标按本地 px 解析、浏览器渲染时再乘回 zoom，`ContextMenu` 直接拿视觉 px 当本地 px 用 → 偏移量 = 坐标 × |zoom−1|，离原点越远偏得越多；视口夹紧公式又混用两种空间（`getBoundingClientRect` 是视觉值、赋给 left/top 的却是本地值），贴边时 `(innerHeight − rect.height − 8) × zoom` 超出视口 → 裁切
- 修：ContextMenu 内部统一坐标空间——x/Y 先除以 `--app-zoom` 换算成本地 px 再定位/夹紧（视口尺寸同样除以 zoom），夹紧改用 `offsetWidth/Height`（本身就是本地值）并补 `max(0,…)` 下限；定位改 `useLayoutEffect` 消除首帧闪位。二级菜单（「移动到…」等）超出视口时自动向上对齐/向左展开
- 关联：MailBrowser 列宽拖拽已有同款换算（clientX/zoom），本次为 ContextMenu 补齐
- 验证：npm run build（tsc+字号门禁）通过（HEAD+本修复的隔离 worktree 亦单独构建通过）；chrome-devtools 挂 dev server 用真实账号数据实测——zoom 1.12/0.85 两档弹出位置均精确贴鼠标（右键 (600,300) → 菜单左上角即 (600,300)），底边/右边右键自动收进视口（菜单底 677.5 ≤ 视口 687−8、右 1111 ≤ 1120−8），「移动到…」二级菜单贴底自动上翻、贴右自动左翻，全程无裁切

## 182f934 — UX: 代理改全局总开关——开=一律走代理，删账号级开关
- 用户反馈：代理「全局地址×账号开关」两层模型太技术化——设置页文案像说明书、账号行多一个按钮；期望和正常软件一样，开了代理一律走代理
- 后端：netproxy 改总开关语义——`network_proxy_enabled`（开=所有账号 IMAP/SMTP 收发与 OAuth 令牌交换一律走代理；本机回环仍直连）；地址二级解析：手动地址（`network_proxy`）留空时自动检测系统代理（urllib.getproxies：macOS 系统代理/Windows 注册表/环境变量，每次连接现读，socks:// 归一 socks5），手动地址优先；`resolve_proxy/httpx_proxy_arg` 去账号开关参数；accounts API 移除 `use_proxy`（DB 列按迁移只追加原则保留不读）；settings GET 附带只读 `detected_proxy` 供设置页展示
- 前端：设置页代理改「开关+地址」一组——开关开启才显示地址输入与探测状态（检测到/未检测到提示）；账号列表删「代理」按钮；types/client/openapi 快照与 schema.d.ts 同步再生
- 文档：使用指南/FAQ/OAuth2 指南/ARCHITECTURE 代理章节同步新模型
- 验证：pytest 147 全绿（test_netproxy 按总开关契约重写+新增系统探测用例，删账号开关用例）、ruff 通过、npm build 通过、openapi 快照再生；真实账号（清华邮箱）同步回归 ok；8720 常驻进程已重启加载新代码
- 遗留：总开关默认关（升级不改变现网行为），代理工具运行时开启即可；代理端口无监听时开启会致连接失败——设置页探测提示已引导

## 6fbbd12 — 每日摘要「重要邮件」可清除（✕）
- 用户反馈：重要邮件通知「查看」完还在列表里，要求加小 ✕ 清除——根因是摘要是当日快照（digest_history JSON，生成时落库），「查看」只是跳转定位邮件，本就不改动快照，属快照语义的自然结果而非 bug
- 后端：新增 `POST /api/digest/important/{email_id}/dismiss`——在最新摘要快照 JSON 落 `dismissed_important` 记录（不在列表内 404）；GET 时按记录过滤展示；同日「重新生成」经 build_digest 沿袭已清除清单不让条目复活，跨天随新摘要自然重置（次日仍重要的邮件重新露出属预期）
- 前端：DigestPage 重要邮件每条加 ✕ 按钮（lucide X，灰显 hover 加深，title「从列表清除」），mutation 成功后失效 digest 查询即见消失；清空后显示既有「近期没有重要邮件」空态
- 验证：pytest 147 全绿（+2：清除持久化且重生成不复活 / 未知 id 404）、ruff 通过、npm build 通过、openapi 快照+schema.d.ts 再生
- 遗留：需重启 python run.py 生效；「需要回复」列表未加清除（用户未要求，语义上也应由回复行为驱动）

## 3955a76 — fix: 版本号解析链——源码直跑不再依赖手工同步的回退常量
- 用户反馈：`.venv/bin/python run.py` 源码直跑，关于页显示「当前 v0.2.0」并提示升级 v0.3.0——排查发现该 venv 从未 `pip install -e .`，`importlib.metadata` 读不到 `nmail-app` 元数据，回退到 config.py 硬编码常量 `APP_VERSION = "0.2.0"`（pyproject 已 0.3.0，注释要求「随动」但实际已漂移）；「单一来源」名存实亡
- 同类隐患更重：release CI 用 `pip install -r requirements.txt + pyinstaller nmail.spec` 打包，冻结环境同样无包元数据 → **已发布的 v0.3.0 三平台二进制实际自报 v0.2.0**，会一直提示用户「升级到 0.3.0」（PyPI/uvx/wheel 用户不受影响）
- 修：config.py 改为 `_app_version()` 解析链——① 源码/可编辑：tomllib 读仓库根 pyproject.toml（改版本即时生效，pip install -e 的元数据快照过期问题一并消除）→ ② 冻结：读 nmail.spec 打入的随包 pyproject.toml 副本 → ③ wheel/uvx：读包元数据 → ④ 兜底 `"0.0.0"`（故意异常值便于暴露，不随发版维护）；release.sh「无需改 config.py」由隐患变事实
- 附带：nmail.spec datas 加 pyproject.toml；pyproject/release.sh/RELEASE.md/ARCHITECTURE.md 过期注释同步更正；新增 4 单测（版本与 pyproject 一致 / 解析器缺失与坏文件 / 冻结读随包副本 / 元数据回退）
- 验证：pytest 145 全绿（+4）、ruff 通过；源码直跑与冻结模拟（sys.frozen+_MEIPASS）实测解析 0.3.0；隔离实例（临时 NMAIL_DATA_DIR，8791 端口）/api/health 报 0.3.0
- 遗留：已发出的 v0.3.0 二进制无法在原处修复，随下一版本自愈；源码直跑的常驻进程需重启才见新版本号

## f2609c8 — UI: AI 配置 API Key 输入框默认遮蔽
- 用户反馈：AI 配置卡片里 API Key 默认明文展示不妥，应默认遮蔽——此前「默认明文」是 0911 反馈「Key 刷新后不可见」时一并改的（把「明文回显」与「默认可见」绑在了一起）；本次只改显隐默认值，回显语义不变
- 改：SettingsPage `ProfileFields`（编辑卡与新建卡共用）`keyVisible` 初始值 true→false，输入框默认 `type=password`，小眼睛一键显隐不变；保存/测试连接读取的是 state 里的真实值，遮蔽不影响任何行为
- 验证：npm run build（tsc）通过

## 32175e8 — docs: 补齐 uvx/brew 安装后的启动与再次使用说明
- 用户反馈：uvx 跑完之后怎么用、下次怎么再打开？——排查确认 INSTALL.md 只有「① 单文件」一节写了「运行后会发生什么」，③ Homebrew 与 ④ uvx 两节只讲安装不讲启动，新用户装完没有下一步
- 修：安装方式表后新增「启动与再次使用（③④ 通用）」说明——启动命令（brew→终端 `nmail`；uvx→原命令即启动命令，任意目录可运行、不落文件）、控制台窗口 + 浏览器自动打开 127.0.0.1:8720（端口占用自动顺延）、退出方式、下次使用重跑同一条命令、`uv cache clean` 清缓存
- 事实核实：brew 装完自带 `nmail` 命令（tap formula `bin.install … => "nmail"`）；uvx 缓存与残留行为经本机 uv 实测口径确认
- 关联物料：微信长图「三步上手」步骤 1 同步补「以后每次启动都是这条命令」（promo/，仓外）

## b805906 — 发版: v0.3.0 全平台——PyPI/Release/tap 即时生效，winget PR 已提，tap token 缺陷暴露
- `release: v0.3.0`（cb2f047）+ tag 推送，release CI run 34688316397：PyPI `nmail-app` 0.3.0 ✅、GitHub Release 三平台资产（windows-x64.exe / macos-arm64 / linux-x64）✅、homebrew-tap ❌（403，重跑复现）
- **homebrew-tap 的 secret `HOMEBREW_TAP_TOKEN` 从未在 Actions 成功工作**：v0.1.0 时该 job 尚未存在（formula 0.1.0/0.2.0 均手动提交 b31fa77/54ec4c4）；v0.3.0 首次真正跑到即 403——判定 fine-grained PAT 失效或权限不足（有效期/资源授权/Contents RW 待用户核对）
- 手动同步 tap formula → 0.3.0（homebrew-nmail 提交 4b3fcbe，url/SHA256 对齐 Release 资产，`brew upgrade nmail` 即生效）
- winget：fork 分支 nmail-0.3.0 提交三 manifest（version/installer/locale，ManifestVersion 1.6.0），PR microsoft/winget-pkgs#433678；InstallerSha256 对齐资产 digest（233e763d…）
- 本版内容（自 v0.2.0）：通讯录 Thunderbird 式双栏改版（联系组/手机号/自动采集开关/同邮箱聚合）、授权码明文回显、账号服务器配置可编辑（改服务器免删号）、时间显示统一、设置页加宽、通讯录横向滚动修复

## 47c6d1c — fix: 发版脚本 Mac bash 3.2 兼容——变量名后紧跟全角字符被吞进变量名
- macOS 自带 bash 3.2 + `C.UTF-8` locale 下，`$VERSION（` 这类**变量名后紧跟全角字符**的写法会把多字节首字节吞进变量名，`set -u` 下直接 `unbound variable` 崩溃（Windows git-bash 的 bash 5.x 不受影响，故此前未发现；v0.3.0 发版演练时暴露）
- 修：5 行 6 处（`$VERSION（`/`$TAG，`/`$TAG）`/`$RUN_ID（`/`$BRANCH（`/`$PR_URL（`）全部加花括号 `${VAR}`——任何 bash 版本与 locale 下都安全
- 验证：`bash scripts/release.sh 0.3.0 --dry-run` 通过（预检→版本号替换→还原全流程）

## 603a73f — fix: 通讯录列表横向溢出被裁切且无法滚动
- 用户反馈通讯录表格右侧（最近联系列）看不全、无法左右滑动——表格滚动容器挂了 `overflow-y-auto overflow-hidden`，横向溢出被直接裁掉且无滚动条；窄窗口下列头/来源徽章还会被压成竖排
- 修：容器改 `overflow-auto`（横向可滚）、表格加 `min-w-[640px]`（不再无限压缩）、全部列头与 SourceBadges 徽章加 `whitespace-nowrap`；已在 1120px 窗口实测滚动到底最后一列完整可见
- 顺带排查：真机验证时发现 8720 常驻进程还是 16:45 的旧代码（早于通讯录改版后端），与新前端对接即整页白屏（`sources.includes` 崩溃）——已重启该进程对齐（数据不受影响，health 报 commit 6bee62b）；其他遗留实例（8794×2、8799）未动

## d262f61 — 设置页加宽减少左右留白
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
