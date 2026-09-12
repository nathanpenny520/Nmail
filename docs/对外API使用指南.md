# Nmail 对外 API 使用指南（docs/对外API使用指南.md）

> v0.4 P7（REDESIGN_PLAN §7）。Nmail 的对外 API 由**本机进程**提供（`http://127.0.0.1:8720/api/ext/v1/*`），
> 供你自己的脚本、自动化（iOS 快捷指令、Raycast、n8n、curl 等）调用；服务始终只绑定 127.0.0.1，
> 其他设备经**你自建的隧道**到达（下文给三种最小配置）。Nmail 不提供任何云端托管服务。

## 0. 三步上手

1. **启用**：设置 → API → 勾选「启用对外 API」（默认关闭）。
2. **生成密钥**：设置 → API → 「生成密钥」——填备注、勾 scope（见下）、可选每日上限。
   密钥明文可随时在列表中查看/复制（存本机 secrets.json，所见即所存）。
3. **调用**：所有请求带 `X-Api-Key` 请求头：

```bash
curl "http://127.0.0.1:8720/api/ext/v1/emails?limit=5" \
  -H "X-Api-Key: nmail_你的密钥"
```

## 1. Scope 与安全模型

| Scope | 能做什么 |
|-------|---------|
| `read` | 邮件列表/搜索/详情/附件、文件夹、通讯录、每日摘要、任务进度 |
| `write` | 标读/星标/移动/归档/删除（入废篓）、创建草稿、触发文件夹同步 |
| `send` | 发送草稿（`POST /drafts/{id}/approve`，走与界面相同的发送通路） |
| `agent` | AI 总管家对话（写动作仍受该账号「AI 权限」与审批/自动模式约束，全部进 AI 操作记录） |

- 一个密钥可勾多个 scope；**建议按用途最小化**（只读监控脚本就只给 `read`）。
- 密钥泄露 = 邮箱可被读写。支持一键**重置**（旧串立即失效）与**吊销**；建议定期轮换。
- 全部调用（含被拒绝的）默认记入「调用日志」（保留 30 天，可在设置页关闭）。
- 限流：60 次/分钟/密钥（超限 429）；可给每个密钥设每日调用上限。
- `/api/ext/*` 豁免本机来源（Host/Origin）校验、改持 API Key——这正是隧道能用的前提；
  浏览器恶意网页无法伪造自定义请求头（预检不通），drive-by 风险由密钥兜住。
- `/health` 免认证（仅返回 `{"ok":true}`），供隧道连通性自测。

## 2. 端点一览

| 端点 | 方法 | Scope | 说明 |
|------|------|-------|------|
| `/health` | GET | — | 存活探测 |
| `/accounts` | GET | read | 账号列表与健康状态 |
| `/emails` | GET | read | 列表/搜索。参数：`account_id` `folder` `q`（≥3 字走全文检索）`is_read` `starred` `category` `limit`（≤200）`offset` |
| `/emails/{id}` | GET | read | 详情（HTML 正文已消毒，远程图片默认拦截） |
| `/emails/{id}/attachments/{aid}` | GET | read | 下载附件 |
| `/emails/actions` | POST | write | 批量动作 `{"ids":[...],"action":"read\|unread\|star\|unstar\|move\|trash\|archive\|unarchive","folder":"目标"}`；打标类同步返回，移动类异步返回 `job_id` |
| `/jobs/{job_id}` | GET | read | 轮询批量动作进度 |
| `/drafts?status=` | GET | read | 草稿列表（默认 `pending_review` AI 待审） |
| `/drafts` | POST | write | 创建草稿 `{"account_id","to","cc","bcc","subject","body_html"}`（地址为逗号分隔串；不会自动发送） |
| `/drafts/{id}/approve` | POST | send | 发送草稿（In-Reply-To/消毒/Sent 归档与界面同通路） |
| `/folders?account_id=` | GET | read | 文件夹缓存列表 |
| `/folders/sync?account_id=&name=` | POST | write | 按需同步指定文件夹（名字走查询参数，IMAP 名含分隔符） |
| `/contacts?q=&limit=` | GET | read | 通讯录搜索 |
| `/digest` | GET | read | 最新每日摘要 |
| `/agent/chat` | POST | agent | 总管家对话（非流式）：`{"question","account_ids?","mode?":"approval\|auto"}` → `{answer, approvals, events}` |
| `/agent/chat/stream` | POST | agent | 同上，SSE 流式（事件：text/tool_call/tool_result/approval_required/error/done） |
| `/agent/actions/{id}/decide` | POST | agent | 批准/拒绝 Agent 待审批动作 `{"decision":"approve\|reject","args"?}` |

错误语义：`401` 缺少/无效密钥 · `403` 未启用或 scope 不足 · `404` 资源不存在 · `429` 限流/超每日上限 · `502` 上游（IMAP/SMTP/AI）失败。完整字段定义见 `http://127.0.0.1:8720/openapi.json`（`/api/ext/v1` tag）。

### 调用示例

```bash
# 搜最近 24h 内来自某人的邮件
curl "http://127.0.0.1:8720/api/ext/v1/emails?q=报销&limit=10" -H "X-Api-Key: $KEY"

# 把 12、13 号邮件归档（异步，返回 job_id）
curl -X POST "http://127.0.0.1:8720/api/ext/v1/emails/actions" \
  -H "X-Api-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"ids":[12,13],"action":"archive"}'

# 建草稿并发送（write + send 两个 scope）
DRAFT=$(curl -s -X POST "http://127.0.0.1:8720/api/ext/v1/drafts" \
  -H "X-Api-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"account_id":1,"to":"boss@example.com","subject":"周报","body_html":"<p>本周完成…</p>"}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['draft']['id'])")
curl -X POST "http://127.0.0.1:8720/api/ext/v1/drafts/$DRAFT/approve" -H "X-Api-Key: $KEY"

# 问 AI 总管家（审批模式下写动作会返回 approvals，拿 action_id 去批准）
curl -X POST "http://127.0.0.1:8720/api/ext/v1/agent/chat" \
  -H "X-Api-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"question":"上周的营销邮件有哪些？"}'
```

## 3. 从其他设备访问：自建隧道三种最小配置

> 远程设备 → 你Mac/PC 上的 Nmail。三种任选其一；**没有公共 IP 也能用**（出站连接建立隧道）。

### 3.1 Cloudflare Tunnel（推荐：有域名、免公网 IP、自带 HTTPS）

```bash
# 一次性：安装 cloudflared 并登录（浏览器授权你的 Cloudflare 账号）
brew install cloudflared && cloudflared tunnel login

# 建隧道并把 nmail.example.com 指到本机 8720
cloudflared tunnel create nmail
cloudflared tunnel route dns nmail nmail.example.com
cloudflared tunnel --url http://127.0.0.1:8720 run nmail
```

远程设备调用：`curl https://nmail.example.com/api/ext/v1/emails -H "X-Api-Key: ..."`。
稳定使用建议写 `~/.cloudflared/config.yml`（`tunnel: nmail` + `ingress:` 映射）并安装为系统服务（`cloudflared service install`）。

### 3.2 Tailscale（推荐：自己设备间互访，零暴露公网）

```bash
brew install tailscale   # 或装客户端，登录同一账号
tailscale up
```

远程设备装 Tailscale 后直接访问宿主机 tailnet 名：
`curl http://你的机器.tailnet-name.ts.net.:8720/api/ext/v1/emails -H "X-Api-Key: ..."`
（或在 Tailscale 管理台给该机器开 MagicDNS 名；无需任何端口转发，流量端到端加密。）

### 3.3 SSH 隧道（临时用、零安装）

```bash
# 在远程设备上执行：把本机的 8720 映射到远程设备的 8720
ssh -N -L 8720:127.0.0.1:8720 用户@你的机器
```

远程设备随后照常调用 `http://127.0.0.1:8720/api/ext/v1/*`（流量走 SSH 加密）。

## 4. 常见问题

- **429 Too Many Requests**：触发 60 次/分钟限流或密钥每日上限——脚本侧加间隔/重试退避，或调高每日上限。
- **401 但密钥没填错**：该密钥可能已被重置/吊销（列表里看「最近使用」），复制最新串即可。
- **想临时全停**：取消勾选「启用对外 API」——所有 `/api/ext/*`（除 `/health`）立即 403，密钥与配置保留。
- **安全底线**：Nmail 永远只监听 127.0.0.1；把端口直接暴露公网（路由器端口转发等）**不受支持也不建议**——请走上述隧道方案。
