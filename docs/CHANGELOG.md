# Nmail 变更记录（docs/CHANGELOG.md）

> 规范：每次功能变更在同一提交内在此追加一条。格式：`## 提交短hash — 标题` + 要点。
> 与 git 提交一一对应；本文件是"发生了什么"，ARCHITECTURE 是"现在是什么样"。

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
- gen_icons.py 改为满幅重排：背景按方块自身逐行边缘中位色重建垂直渐变，前景以色距软 alpha 抠出信封+光晕，放大至 74% 居中——系统裁完圆角即自然成图
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
