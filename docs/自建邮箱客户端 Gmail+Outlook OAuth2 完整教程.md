# 自建邮箱客户端 Gmail + Outlook.com(Microsoft) OAuth2 完整教程

> **核验说明**：本文档基于 2026-09-11 的官方文档逐项核验（Google Developers、Microsoft Learn、Microsoft Support）。原稿中 4 处错误已修正、2 处过时信息已更新、若干易踩坑点已补充，详见文末《核验记录》。

---

## 0. 为什么现在必须用 OAuth2（2026 年现状）

自建邮箱客户端对接 Gmail / Outlook.com，**账号密码（基础认证）已经不可用了**：

- **Google 侧**：Google 于 2022-05-30 全面关闭"不够安全的应用"（Less Secure Apps，用户名+密码直连）。自 2025-03-14 起，Google Workspace 账号使用第三方应用访问 Gmail 必须走 OAuth（仅应用专用密码作为例外过渡）。个人 Gmail 账号目前仍可在开启两步验证后生成应用专用密码，但 Google 明确将其定位为"兼容性过渡方案"，正在逐步收紧。**自建客户端应直接实现 OAuth2，一次到位。**
- **微软侧**：Microsoft 已分阶段停用 Outlook.com 个人账号（@outlook.com / @hotmail.com / @live.com / @msn.com）的 POP / IMAP / SMTP 基础认证（2024-09 起逐步推进，2025 年完成）；Exchange Online 的 SMTP AUTH 基础认证也于 2026-03 起分阶段关闭（预计 2026-04-30 完成）。**现在 Outlook.com 的官方要求就是 Modern Auth（OAuth2）。**

核心结论：IMAP/SMTP 使用 **SASL XOAUTH2** 认证，不再使用账号密码。

---

## 1. 核心原理：XOAUTH2 编码（客户端必须实现）

IMAP / SMTP 在 `AUTHENTICATE XOAUTH2` 时，发送的字符串格式为：

```
user=<EMAIL>\001auth=Bearer <ACCESS_TOKEN>\001\001
```

将上面整个字符串做 **base64 编码**后发给邮件服务器。这是 Gmail 和 Outlook 共用的 SASL XOAUTH2 格式，**是最容易踩坑的点**。

关键细节：

- `\001` 是 **ASCII 0x01 控制字符（SOH）**，不是字符串 `"\001"` 这三个字符。用 Python 表示是 `'\x01'`，用 C/C++ 表示是 `'\x01'`，写进字符串字面量时一定要用二进制字节，否则 base64 编码错误、直接认证失败。
- 示例原始字符串：`user=test@gmail.com\x01auth=Bearer ya29.a0AfH6...token...\x01\x01`
- base64 示例（供对照）：`dXNlcj10ZXN0QGdtYWlsLmNvbQFhdXRoPUJlYXJlciB5YTI5LmEwQWZINg==`

---

## 2. 第一部分：Gmail OAuth2 配置（个人 @gmail.com / Google Workspace）

### Step 1：Google Cloud 创建项目

1. 打开 <https://console.cloud.google.com/>
2. 新建项目，自定义项目名
3. 进入项目 → **API 和服务 → 库**，搜索 **Gmail API** → 启用

### Step 2：OAuth 同意屏幕（Consent Screen）

1. **API 和服务 → OAuth 同意屏幕**
2. 用户类型：
   - 个人 gmail 账号：必须选 **外部（External）**
   - Workspace 内部账号：可选"内部"（仅组织内用户可用）
3. 填写必填项：应用名称、支持邮箱、开发者联系邮箱
4. 作用域（Scopes）添加：
   ```
   https://mail.google.com/
   ```
   > ⚠️ **重要修正**：IMAP/POP/SMTP 的 XOAUTH2 登录**只认 `https://mail.google.com/` 这一个 scope**。不要试图用 `gmail.modify`、`gmail.labels`、`gmail.readonly` 等细粒度 scope——那些是 **Gmail REST API** 的 scope，换来的 token 无法用于 IMAP/SMTP 登录，会直接认证失败。
5. 测试用户：添加你要登录测试的 gmail 邮箱（测试阶段只有添加的测试账号能授权）
6. 保存继续

> ⚠️ 未发布（Testing）状态下应用只能由测试用户授权；上线供外部用户使用需要提交 Google OAuth 应用审核。

### Step 3：创建 OAuth 客户端 ID（重点：区分应用类型）

**API 和服务 → 凭据 → 创建凭据 → OAuth 客户端 ID**

| 应用类型 | 选择项 | 重定向 URI | Client Secret |
|---|---|---|---|
| 桌面客户端（本地 GUI 自建客户端，**推荐**） | **桌面应用** | 无需填写（loopback 自动允许） | 控制台会生成，但 **PKCE 流程不使用它，不应硬编码** |
| Web 网页客户端 | 网页应用 | 必须填写并**完全匹配**，本地调试如 `http://127.0.0.1:xxxx/callback` | 生成，须严格保密 |

下载凭据 JSON 保存备用。

> 说明：Google 控制台对"桌面应用"类型也会显示一个 client_secret（installed app 的 secret 本身不被 Google 视为机密），但推荐的做法是走 **PKCE**（code_challenge / code_verifier），完全不传 client_secret。

### Step 4：Gmail OAuth Endpoint 与 Scope

| 项 | 值 |
|---|---|
| 授权地址 | `https://accounts.google.com/o/oauth2/v2/auth` |
| Token 地址 | `https://oauth2.googleapis.com/token`（**修正**：原稿的 `www.googleapis.com/oauth2/v3/token` 不是 token 交换端点） |
| Scope | `https://mail.google.com/` |
| 桌面端 | 必须启用 PKCE（code_challenge / code_verifier），不需要 client_secret |

### Step 5：Gmail IMAP/SMTP 服务器参数（XOAUTH2 认证）

| 协议 | 主机 | 端口 | 加密 | 认证方式 |
|---|---|---|---|---|
| IMAP | imap.gmail.com | 993 | SSL/TLS | XOAUTH2 |
| SMTP | smtp.gmail.com | 465 | SSL/TLS | XOAUTH2 |
| SMTP 备选 | smtp.gmail.com | 587 | STARTTLS | XOAUTH2 |

前置条件：

- Gmail 网页 → **设置 → 转发和 POP/IMAP** → 启用 **IMAP 访问**（确认已开启，否则 IMAP 连接被拒）
- Google 官方文档明确：Gmail IMAP/SMTP 使用标准 SASL，在 `AUTHENTICATE` 命令中走 XOAUTH2 机制

> 补充：Gmail 的 OAuth 会话时长约等于 access_token 的有效期（通常 1 小时）。连接建立后若超过 token 有效期，Gmail 会关闭会话，客户端需用刷新后的新 token 重连。

### Gmail OAuth 完整授权流程（客户端代码实现）

1. 生成 `code_verifier` → SHA-256 生成 `code_challenge`
2. 浏览器打开授权 URL，带上 `client_id`、`redirect_uri`、`response_type=code`、`scope`、`code_challenge`
3. 用户登录 Google 账号，授权你的应用
4. 回调拿到 `authorization_code`
5. POST 到 token 端点，带上 `code` + `code_verifier`（+ `client_id`，桌面 PKCE 不传 `client_secret`），换取：
   - `access_token`（短期，约 1 小时）
   - `refresh_token`（长期，妥善持久化存储）
   - `expires_in`
6. IMAP/SMTP 握手，使用 XOAUTH2 + access_token 登录

> 坑点：
> - 测试环境（Testing）下，**每次重新同意授权**才会返回 refresh_token
> - 首次授权请求参数必须带 **`access_type=offline`**，否则不会返回 refresh_token
> - 回调地址（重定向 URI）必须与 Google Cloud 中登记的**完全一致**（多一个 `/`、大小写不同都会报 `redirect_uri_mismatch`）

---

## 3. 第二部分：Microsoft Outlook.com / Office365 OAuth2（outlook.com / hotmail / M365）

> 个人 Outlook 账号必须选"多租户 + 个人账号支持"，否则 live.com 账号无法授权。

### Step 1：进入 Microsoft Entra 应用注册

1. 访问 <https://entra.microsoft.com/> → **应用注册 → 新注册**
2. 名称：自定义客户端名称
3. **支持的账户类型（极其关键）**：
   - ✅ **任何组织目录中的账户（任何 Microsoft Entra 租户）和个人 Microsoft 账户（例如 Skype、Xbox）**
   - ❌ 不要选"仅个人 Microsoft 账户"以外的单租户选项，个人 outlook 账号会报错无法授权
4. 重定向 URI：
   - **桌面客户端（PKCE）**：平台选 **移动和桌面应用**，会自动添加 `https://login.microsoftonline.com/common/oauth2/nativeclient`
   - **Web 客户端**：平台选 Web，填写回调地址如 `http://127.0.0.1/callback`
5. 点击注册，复制 **Application (client) ID**（即 client_id）

### Step 2：API 权限（委托权限 Delegated，用户登录授权；不是应用权限）

1. 进入注册好的应用 → **API 权限 → 添加权限 → Microsoft Graph → 委托权限（Delegated permissions）**
2. 添加以下 3 个 scope：

```
https://outlook.office.com/IMAP.AccessAsUser.All
https://outlook.office.com/SMTP.Send
offline_access
```

- `offline_access` 用于获取 refresh_token，**必须加**
- 不要添加**应用程序权限（Application permissions）**：那是后台服务无用户登录场景，需要管理员同意，个人 outlook 账号不能用

### Step 3：微软 OAuth Endpoint（/common 端点，支持个人 + 企业账号）

| 项 | 值 |
|---|---|
| 授权地址 | `https://login.microsoftonline.com/common/oauth2/v2.0/authorize` |
| Token 地址 | `https://login.microsoftonline.com/common/oauth2/v2.0/token` |
| Scope 字符串 | `https://outlook.office.com/IMAP.AccessAsUser.All https://outlook.office.com/SMTP.Send offline_access` |
| 桌面客户端 | 推荐 PKCE，不需要 Client Secret |
| Web 客户端 | 可在"证书和机密"中创建客户端密钥（Client Secret） |

### Step 4：Outlook IMAP/SMTP 服务器参数（XOAUTH2）

| 协议 | 主机 | 端口 | 加密 | 认证方式 |
|---|---|---|---|---|
| IMAP | outlook.office365.com | 993 | SSL/TLS | XOAUTH2 |
| SMTP（个人 Outlook.com 官方值） | smtp-mail.outlook.com | 587 | STARTTLS | XOAUTH2 |
| SMTP（M365 组织账号常用） | smtp.office365.com | 587 | STARTTLS | XOAUTH2 |

> ⚠️ 微软 SMTP 不推荐 465，优先 587 + STARTTLS。

前置条件（个人 Outlook.com 账号，最容易漏的一步）：

- Outlook.com 的 **POP & IMAP 访问默认是禁用的**。需要到 **Outlook.com 设置 → 邮件 → 同步电子邮件**，把 **"让设备和应用使用 POP/IMAP"** 开关打开
- 若 SMTP 报 `535 5.7.139 Authentication unsuccessful, SmtpClientAuthentication is disabled`：
  - 个人 Outlook.com 账号：在 Outlook.com 设置中开启**"经过身份验证的 SMTP"**（邮件 → 同步电子邮件）
  - M365 组织账号：需要管理员用 Exchange Online PowerShell 开启：`Set-CASMailbox <用户> -SmtpClientAuthenticationDisabled $false`

### Microsoft OAuth 授权流程

与 Gmail 几乎一致（Authorization Code + PKCE）：

1. 生成 `code_verifier` / `code_challenge`
2. 打开微软登录授权页面
3. 用户登录 outlook 账号，授予权限
4. 回调拿到 `code`，POST 换取 `access_token`、`refresh_token`
5. token 过期后用 `refresh_token` 刷新 `access_token`
6. IMAP/SMTP `AUTHENTICATE XOAUTH2` 登录，**编码格式与 Gmail 完全一样**

> 常见坑：scope 写错资源——**不要用 `graph.microsoft.com` 的资源**。IMAP/SMTP 必须用 `outlook.office.com` 下的 scope（`IMAP.AccessAsUser.All` / `SMTP.Send`），否则 token 鉴权失败。

---

## 4. 第三部分：客户端开发通用代码要点（自建邮箱客户端）

### 4.1 Token 管理逻辑

- **access_token**：短期（约 1 小时），每次 IMAP/SMTP 连接必须使用有效 access_token
- **refresh_token**：长期，**加密持久化存储**（数据库 / 本地密钥环，不要明文存配置文件）
- 刷新接口：POST 到 token 端点，`grant_type=refresh_token`，拿到新 access_token；部分场景 refresh_token 会轮换（微软 v2 端点默认轮换，需更新保存）

### 4.2 IMAP XOAUTH2 握手示例（伪命令流）

```
A001 AUTHENTICATE XOAUTH2
+ dXNlcj1hYkBnbWFpbC5jb20BAXRoPUJlYXJlciB5YTI5LmEwQWZINg==
* OK User authenticated
```

说明：服务器发 `+` 表示等待客户端发送 base64 编码的 XOAUTH2 字符串；发送后若认证通过返回 `OK`。

### 4.3 推荐开发库

| 语言 | 推荐方案 |
|---|---|
| C# | **MailKit**（原生支持 XOAUTH2，最成熟） |
| Python | `imaplib` / `smtplib` + `google-auth-oauthlib` / `msal`，自行实现 XOAUTH2 base64 编码 |
| C++ | libetpan，或手写 IMAP/SMTP + libcurl 做 OAuth 请求 |

### 4.4 高频踩坑清单（核验修正版）

1. **重定向 URI 严格完全匹配**，多一个 `/` 或大小写不同就报错
2. **微软 IMAP scope 必须是 `outlook.office.com`**，不是 `graph.microsoft.com`，token 会鉴权失败
3. **Gmail scope 必须是 `https://mail.google.com/`**，`gmail.modify` / `gmail.labels` 等 API scope 不能用于 IMAP/SMTP 登录
4. **Gmail 测试环境**：授权参数不带 `access_type=offline` 不会返回 refresh_token；测试阶段每次重新授权才发 refresh_token
5. **XOAUTH2 编码**：`\001` 不是字符串 `"\001"`，是**二进制 0x01 字节**，base64 编码出错直接认证失败
6. **端口与加密不匹配**：Gmail 465 是 SSL、587 是 STARTTLS，不能混用；微软 SMTP 用 587 + STARTTLS
7. **微软安全默认策略**：MFA 会阻断基础认证，但 OAuth2 不受影响；条件访问策略依然可以拦截 token
8. **Google OAuth 测试阶段**：只有添加的测试用户可以登录，其他 gmail 账号无法授权
9. **Outlook.com 个人账号 POP/IMAP 默认禁用**：不先开启"让设备和应用使用 POP/IMAP"，连接直接失败
10. **SMTP 535 5.7.139**：邮箱的 SMTP AUTH 被禁用（个人账号在 Outlook.com 设置开启"经过身份验证的 SMTP"；M365 需管理员 PowerShell 开启）

### 4.5 测试建议

先用 Postman / 简单脚本完成 OAuth 授权拿到 access_token，再手动测试 IMAP XOAUTH2 登录，调通协议层后，再集成进你的客户端。

---

## 5. 第四部分：OAuth 安全注意事项

1. 桌面客户端 PKCE 模式**不要硬编码 client_secret**（PKCE 流程本身也不需要）
2. **refresh_token 加密存储**，不能明文保存
3. **不要把 access_token 打印到日志**
4. Google OAuth 上线必须提交 **OAuth 应用审核**，否则外部用户无法授权
5. access_token 仅保留在内存中，按需从密钥环读取

---

## 6. 核验记录（2026-09-11）

**确认无误的内容**：XOAUTH2 编码格式（`user=...\x01auth=Bearer ...\x01\x01` + base64）；Gmail 服务器参数（imap.gmail.com:993 SSL、smtp.gmail.com:465 SSL / 587 STARTTLS）；Google 授权端点与同意屏幕流程；`access_type=offline` 要求；Outlook 账户类型选择、`/common` 端点、nativeclient 重定向 URI、三个委托 scope；MailKit 对 XOAUTH2 的原生支持。

**修正项**：

| # | 原稿内容 | 修正后 | 依据 |
|---|---|---|---|
| 1 | Google Token 地址 `https://www.googleapis.com/oauth2/v3/token` | `https://oauth2.googleapis.com/token` | Google Developers 官方文档 |
| 2 | Gmail scope 可细拆为 gmail.modify、gmail.labels | **不可拆**，IMAP/SMTP 只认 `https://mail.google.com/` | Google XOAUTH2 协议文档 |
| 3 | 桌面客户端"生成 Client ID，无 client_secret" | 控制台会生成 client_secret，但 PKCE 不使用、不应硬编码 | Google Developers |
| 4 | Outlook SMTP 仅写 smtp.office365.com | 个人 Outlook.com 官方值为 `smtp-mail.outlook.com:587 STARTTLS`；smtp.office365.com 为 M365 常用 | Microsoft Support |
| 5 | 未提及 Outlook.com POP/IMAP 需手动开启 | 补充：默认禁用，需在设置→邮件→同步电子邮件 开启 | Microsoft Support |

**更新项**：微软 Outlook.com 基础认证已分阶段停用（2024-09 起，2025 年完成）；Exchange Online SMTP AUTH 基础认证 2026-03/04 分阶段关闭；Google LSA 已于 2022-05 关闭、Workspace 自 2025-03-14 强制 OAuth。

**主要参考来源**：

- Google：IMAP/POP/SMTP 官方文档 <https://developers.google.com/workspace/gmail/imap/imap-smtp>
- Google：XOAUTH2 协议 <https://developers.google.com/workspace/gmail/imap/xoauth2-protocol>
- Google：OAuth 2.0 端点 <https://developers.google.com/identity/protocols/oauth2/web-server>
- Google：OAuth 2.0 for iOS & Desktop Apps <https://developers.google.com/identity/protocols/oauth2/native-app>
- Microsoft Learn：使用 OAuth 对 IMAP、POP 或 SMTP 连接进行身份验证 <https://learn.microsoft.com/en-us/exchange/client-developer/legacy-protocols/how-to-authenticate-an-imap-pop-smtp-application-by-using-oauth>
- Microsoft Support：Outlook.com 的 POP、IMAP 和 SMTP 设置 <https://support.microsoft.com/en-us/outlook/pop-imap-and-smtp-settings-for-outlook-com>
- Microsoft Support：使用基本身份验证时无法连接 Outlook.com <https://support.microsoft.com/en-us/support/known-issues/outlook-and-other-apps-are-unable-to-connect-to-outlook-com-when-using-basic-authentication>

---

## 7. 附录：下一步

如需，可以直接提供一段**可运行的最小 Python Demo**，完整实现 Gmail / Outlook PKCE OAuth + XOAUTH2 IMAP 登录（含 refresh_token 刷新与加密存储示例）。确认后即可生成。
