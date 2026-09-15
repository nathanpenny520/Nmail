# Nmail Agent 接入指南（docs/Agent接入指南.md）

> 把 Nmail 的邮件能力交给 AI Agent（Claude Code / Codex / 任何能运行命令的 agent）：
> agent 读 `skills/SKILL.md` 学会用 `nmail-cli` 命令行工具收发读搜、整理邮箱、监听新邮件。
> 本机服务永远只绑 127.0.0.1，远程设备走你自建隧道（见 [对外 API 指南](/docs/api/)）。

## 1. 一键安装技能

在你的 agent 环境里执行（skill 本体随主仓 `skills/SKILL.md` 分发）：

```bash
npx skills add nathanpenny520/Nmail -g -y
```

装好后直接用自然语言对话即可：「帮我看看最近的未读邮件」「搜一下标题带周报的邮件」
「回复这封邮件说今天晚点处理」「以后新邮件来了提醒我」。

> GitHub 直连不畅的环境：克隆主仓后改用本地路径安装
> `npx skills add <主仓目录> -g -y -s '*' -a '*'`。

## 2. 配对授权（首次）

agent 首次执行邮件命令时，按 SKILL.md 引导运行：

```bash
uvx nmail-cli@latest auth login --yes
```

- 本机检测到 Nmail 在运行 → 自动创建一把**只读（read）**专用密钥（设置-API 里可见、可吊销）
- 需要发送邮件时扩权：`auth login --yes --scopes read,write,send`
- 远程实例：`auth login --base-url https://你的隧道域名 --key nmail_xxx`
  （Key 从 Nmail 设置-API 复制；密钥管理面不出本机）
- 配置存 `~/.config/nmail-cli/config.json`（0600）；`NMAIL_BASE_URL`/`NMAIL_API_KEY`
  环境变量可覆盖

验证：`uvx nmail-cli@latest +me` 列出账号与健康状态。

## 3. agent 在做什么（行为契约）

- **输出**：命令 stdout 只输出 JSON envelope（`{"ok":…}`），exit code 表达结果语义——
  agent 按表决策重试/改参数/停下问你（0 成功 · 2 参数错不重试 · 3 重新配对 · 4 连不上 ·
  6 不存在 · 7 限流等 `retry_after` · 8 需要你确认）。
- **两阶段确认**：发送邮件必须两步——先 `drafts send <id>` 拿到收件人/主题/正文摘要
  （exit 8），**展示给你并等你明确同意**后才带 `--confirmed` 重放。任何非 0 退出，
  agent 不得声称「已发送」。
- **监听新邮件**：`nmail-cli watch` 每封新邮件输出一行 JSON，直到你要求停止。

## 4. 偷懒通道：Nmail 内置总管家（v0.4.0）

不想让 agent 一步步编排命令？一条命令把整件事委托给 Nmail **内置的 AI 总管家**（它在后台自带审批/审计/每日限额全套闭环）：

```bash
nmail-cli agent ask "把收件箱里的营销邮件归档，然后总结本周往来"   # 提问/下任务
nmail-cli agent decide <action_id> --approve   # 有待审批动作时批准（或 --reject，总管家会改道）
nmail-cli agent resume <run_id>                # 被审批/触顶/澄清暂停的任务继续跑
```

- Key 需带 `agent` scope（`auth login --yes --scopes read,write,send,agent`），且 Nmail 已配置 AI。
- 输出为紧凑 JSON（`answer` / `approvals` / `paused`），外部 agent 看一眼就知道要不要继续；审批与「向你确认」的暂停态都会如实带出，**不会替你默认放行**；澄清回答用 `agent resume <run_id> --answer "回答"` 带上。
- 无人值守场景（scheduler 定时晨报等）不会因澄清而挂起——澄清工具在无人值守下被硬拒。

## 5. 其他 CLI 常用件（v0.4.0 补齐）

- `nmail-cli folders list --account-id <id>`：列出文件夹缓存，`move`/`--folder` 的目标名有处可查。
- 版本协商：`/health` 返回服务端版本；CLI 落后时 envelope 附 `_notice.update`（含 cli/server/upgrade/skill 提示），agent 看到即可提醒升级。

## 6. 安全边界（设计上兜住）

- 邮件内容 = 不可信外部输入：SKILL.md 明文要求 agent **绝不执行邮件正文里的"指令"**
  （prompt injection 防护）、不主动访问邮件里的链接、敏感操作必须说明"来自邮件内容"并经你确认。
- 最小权限：配对默认只建 `read`；scope 随时在 设置-API 调整，密钥可一键重置/吊销；
  全部调用（含被拒的）进「API 调用日志」（保留 30 天）。
- 网络不扩大：服务仍只绑 127.0.0.1，skill/CLI 不改变这一边界；远程一律自建隧道
  （Cloudflare Tunnel / Tailscale / SSH，配置见 [对外 API 指南](/docs/api/)）。
- 收发通路与界面完全同源：外发 HTML 统一消毒，回复自动带 In-Reply-To 串线。

## 7. 不用 agent，纯脚本也可以

CLI 与 HTTP API 并行有效：脚本可直接 curl `http://127.0.0.1:8720/api/ext/v1/*`
（Key、scope、限流与错误格式见 [对外 API 指南](/docs/api/)），或直接调用 `nmail-cli`
各命令解析 JSON。批量归档等慢动作返回 `job_id`，CLI 的 `emails action` 已自动等任务完成。
