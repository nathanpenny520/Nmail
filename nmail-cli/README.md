# nmail-cli

Nmail 对外 API 的命令行客户端（AGENT_SKILL_PLAN P2 / REDESIGN_PLAN §19）——为外部
agent 与 skill 设计：JSON envelope（stdout）、exit code 契约、发送类两阶段确认。

## 安装

```bash
uvx nmail-cli@latest --help     # 零安装（PyPI 发布后）
# 或
pipx install nmail-cli
```

发布随主仓发版流程进行（`nmail-cli` 为独立 PyPI 包名）。

## 快速上手

```bash
nmail-cli auth login                 # 本机 Nmail（127.0.0.1:8720）自动配对建 Key（默认 read scope）
nmail-cli auth login --scopes read,write,send   # 需要发送时显式扩权
nmail-cli +me                        # 账号列表与健康
nmail-cli emails list --limit 5
nmail-cli emails read 254 --save-attachments ./downloads
nmail-cli drafts reply --email-id 254 --body-file ./reply.md
nmail-cli drafts send 44             # 第一阶段：打印摘要，exit 8
nmail-cli drafts send 44 --confirmed # 第二阶段：用户许可后重放
nmail-cli watch                      # NDJSON 每行一封新邮件
```

远程（自建隧道）：`nmail-cli auth login --base-url https://nmail.example.com --key nmail_xxx`
（`/api/extkeys` 管理面仅本机可达，远程需从 Nmail 设置-API 复制 Key 粘贴）。

## 契约

- **stdout** 只输出 JSON envelope：成功 `{"ok":true,"data":…}`，失败
  `{"ok":false,"error":{"code","message",…}}`；人话日志走 stderr。
- **exit code**：`0` 成功 · `1` 上游 5xx 可重试×2 · `2` 参数不合规不重试 · `3` 认证失效/未启用
  走 `auth login` · `4` 连不上（检查 Nmail 是否运行/隧道） · `6` 业务永久拒绝不重试 ·
  `7` 限流按 `Retry-After` 等待 · `8` 需两阶段确认（停下等用户，不得同轮自确认）。
- 配置：`~/.config/nmail-cli/config.json`（0600）；环境变量 `NMAIL_BASE_URL` / `NMAIL_API_KEY`
  可覆盖（CI/一次性场景）。

服务端 API 与安全模型见 `docs/对外API使用指南.md`；面向 agent 的技能说明见 `skills/SKILL.md`（P3）。
