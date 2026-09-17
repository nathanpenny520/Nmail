# 体验优化轮（docs/EXPERIENCE_PLAN.md）

> 来源：用户 2026-09-17 六项体验反馈（同步窗口 / 模板签名格式 / 附件预览 / Tab 状态 / 通知机制 / AI 能力边界），调查结论经用户确认后拍板，六项全部落地。会话：S-0917-1252-体验优化。
> 批次顺序：B2 → B3 → B1 → B5 → B4 → B6。**2026-09-17 全部落地**：B2=1e37818、B3=f120525、B1=79d1988、B5=086fb29、B4=d23ba30、B6=237b677。
> 遗留：真机全量回补观察（用户实例升级后随首轮轮询开始）；apply_template 以 draft grant 落地（与 create_draft 同级）而非方案初稿的 organize。

## B1 全量同步（所有文件夹 × 全部历史）

背景：首同步硬编码 30 天（`sync.py` `FIRST_SYNC_DAYS`），且无任何历史回补——用户要求原生客户端级全量。非服务器限制。

方案：
- 去掉 30 天窗口。首同步改为「先拉最新一页立即可用，再从新到旧分块回补」：
  - `sync_state` 增列 `backfill_uid`（回补断点：下一个待拉取的更旧 UID 上界）与 `backfill_done`；MIGRATIONS 末尾追加迁移（规范 7）
  - `_sync_folder` 增量分支保持不变（`UID last_uid+1:*`）；回补未完成时每次轮询做限时回补（约 20 块 × 25 封/次），从 `backfill_uid` 向下走，到 UID 1 或空结果即标记完成
  - `iter_new_mail` 首同步分支改为：拉最新 `chunk_size` 封 → 置 `last_uid` = 最大 UID、`backfill_uid` 同值、`backfill_done=0`
- 文件夹范围：folders 表全部文件夹（排除 `special_use='all'`，Gmail All Mail 与 INBOX 重复）。回补按文件夹轮转，INBOX 优先
- **回补邮件不进 AI 流水线、不计入 new_mail 通知**（避免上万封跑 AI + 通知轰炸）；仅 INBOX 增量新邮件触发
- 进度呈现：`status_detail` 扩展 `{phase:'backfill', folder, synced, est_total}`；设置页账号卡与文件夹树可见
- UIDVALIDITY 变化仍清空该文件夹（含回补断点，UID 失效无法续传）；删账号清本地保持不变（用户确认合理）

验收：真实账号添加后 1 分钟内 INBOX 可用；随后各文件夹全量入库、可续传；期间轮询/收信/AI 分类正常。

## B2 换行修复（Markdown nl2br）

根因：`markdown_body_html` / `markdown_to_email_html` 未开 nl2br 扩展，单个换行被折叠为空格。用户确认场景：模板/签名插入后（同样波及 AI 起草与 markdown 粘贴）。编辑器直接打字不受影响（Enter 生成段落）。

- `backend/app/core/mail_html.py` 两函数 extensions 加 `"nl2br"`
- `frontend/src/components/Markdown.tsx`（聊天/晨报渲染）加 remark-breaks，口径一致
- tests 补用例：单换行→`<br>`、空行分段不变

## B3 附件预览（图片 / PDF / 文本）

范围（用户拍板）：图片、PDF、文本预览；其余类型保持下载。

- `backend/app/api/emails.py` download 端点加 `?inline=1`：mime 白名单（`image/*` 不含 svg、`application/pdf`、`text/*`）才允许 inline，其余强制 attachment；响应加 `X-Content-Type-Options: nosniff`
- `frontend/src/components/EmailReader.tsx` 附件区：图片 `<img>` / PDF `<iframe>`（浏览器内置 viewer）/ 文本 fetch + `<pre>`（>1MB 提示下载）预览弹层；其余类型保持下载
- HTML/SVG 附件不进 inline 白名单（同源脚本风险）

## B4 Tab 常驻 keep-alive

根因：路由切换 = 页面组件整体卸载，滚动/筛选/选中/聊天记录全丢（唯一 keep-alive 是写信台）。

- Layout：四个页签页面改常驻挂载（首次激活才挂载，之后 display 切换），写信 keep-alive 不变
- react-query 轮询按页签激活态门控（`enabled`/`refetchInterval`），隐藏页签不拉取
- window 级键盘监听按激活态 gate（MailBrowser / ManagerPage 等）
- `?focus=` 深链与通知跳转在常驻化后仍送达

## B5 通知修复（三项）

- Trash 误报：`sync.py` 汇总通知的 `new_total` 只统计 INBOX（results 已带 folder 字段）
- 点击跳转：桌面通知 `onclick` 补 navigate（复用 `openNotification` 类型映射）；`new_mail`/`ai_archive` 的 `ref_id` 改存可定位 email id（存量账号 id 行做兼容回落）；`?focus=` 深链承接
- 纯文本摘要：晨报通知单独生成纯文本短摘要（md→plain 清理 + 截短），完整 markdown 站内看；应用内通知面板 digest 类型改用 Markdown 组件渲染
- `ai_archive` 通知带被归档邮件清单（pipeline 返回归档列表）

## B6 AI 工具扩充（人人对等）

新增工具（`tools.py` 注册 + `_summarize_result` + 前端 `TOOL_LABELS` 中文名）：

| grant | 工具 | 自动模式 |
|---|---|---|
| read | `list_templates` / `list_signatures` | 可执行 |
| organize | `apply_template` / `apply_signature`（起草时套用，经 create/update_draft 落地） | 可执行 |
| organize | 通讯录分组管理（list/create/rename/add/remove） | 可执行 |
| organize | `set_settings` 受限白名单：notify_types、desktop_notifications_enabled、auto_insert_signature、poll_interval_minutes、trigger_sync | 可执行 |
| organize+硬规则 | `set_settings` 扩展键：agent_brief_enabled、digest_time、allow_remote_images；read_email 截断放开 | **始终出审批卡**（`_approval_reason` 硬规则，自动模式也降审批） |

- 发送补签名：`outbox.send_user_draft` 对 origin='ai' 草稿自动追加账号默认签名（受 auto_insert_signature 控制）；修正 `prompts.py`「系统会自动处理」失真说明
- 维持豁免（REDESIGN_PLAN §17.3）：secrets、ai_grants、账号凭据、API key、HTTP/命令执行、附件来源
