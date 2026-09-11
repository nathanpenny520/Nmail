# Nmail 变更记录（docs/CHANGELOG.md）

> 规范：每次功能变更在同一提交内在此追加一条。格式：`## 提交短hash — 标题` + 要点。
> 与 git 提交一一对应；本文件是"发生了什么"，ARCHITECTURE 是"现在是什么样"。

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

## 待提交 — 图标：apple-touch-icon 按 Apple 规范重排
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
