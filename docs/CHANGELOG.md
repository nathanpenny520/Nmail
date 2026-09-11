# Nmail 变更记录（docs/CHANGELOG.md）

> 规范：每次功能变更在同一提交内在此追加一条。格式：`## 提交短hash — 标题` + 要点。
> 与 git 提交一一对应；本文件是"发生了什么"，ARCHITECTURE 是"现在是什么样"。

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
