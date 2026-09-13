# OAuth2 授权登录使用指南（Gmail / Outlook）

> 面向 Nmail 使用者的实操手册。Google/微软已停用账号密码直连，Gmail/Outlook 必须走 OAuth2 授权。
> 全部内容来自真实踩坑（每个报错都实际出现过并已解决），排错对照表见文末。
> 开发者向的协议细节与控制台核验记录见 [自建邮箱客户端 Gmail+Outlook OAuth2 完整教程.md](自建邮箱客户端%20Gmail+Outlook%20OAuth2%20完整教程.md)。

## 0. 快速授权（默认，零配置，绝大多数人到这就够了）

v0.4 起内置公开桌面客户端凭证：**添加账号 → 输入邮箱地址 → 点「授权登录」→ 浏览器完成登录**，三步完成，无需去任何控制台注册应用。

- 凭证为公开信息（源自开源邮件客户端公开源码），Nmail 与凭证来源方无官方关联；
- 凭证可用性由 Google/微软单方决定，万一被限制导致授权失败，再到 §1 配置你自己的客户端（自建永远优先）；
- 个人 Outlook 账号仍需一次性开启邮箱侧开关（见 §3，这是微软的账号设置，与用什么客户端无关）。

## 1. 高级：注册你自己的 OAuth 客户端（内置凭证不可用/需要更高可控性时）

### 总览：三层配置，缺一不可

1. **OAuth 客户端**（一次性，5 分钟）：在 Google Cloud / Microsoft Entra 注册你自己的应用，把 client_id（Web 型还需 client_secret）填进 Nmail 设置页（邮箱账号 → OAuth2 卡片 → 对应服务商行「高级」）
2. **Nmail 里的授权**（每账号 30 秒）：添加账号 → 点「使用 XX 账号授权登录」→ 浏览器登录完成
3. **邮箱侧开关**（Outlook 专属，每邮箱一次）：Outlook 网页版开启 POP/IMAP 与经过身份验证的 SMTP

### 注册 OAuth 客户端

### Gmail（Google Cloud 控制台）

1. <https://console.cloud.google.com/> → 新建项目
2. **API 和服务 → 库** → 搜索 **Gmail API** → 启用
3. **OAuth 同意屏幕**（新版控制台在「Google Auth Platform → 受众群体」）：
   - 用户类型**必须选「外部」**——选「内部」个人 Gmail 授权会报 `403 org_internal`
   - 测试用户里**加上你要授权的 Gmail 地址**（测试状态必需，否则 `access_denied`）
4. **凭据 → 创建凭据 → OAuth 客户端 ID**，二选一：
   - **桌面应用**（推荐）：无需 client_secret，`http://localhost` 回环端口自动放行
   - **Web 应用**：重定向 URI 填 Nmail 设置页显示的回调地址（逐字一致），**必须**再到「客户端密钥」创建 secret 并填进 Nmail
5. Scope 只需 `https://mail.google.com/`（IMAP/SMTP 只认这一个，不要用 gmail.modify 等 API scope）

### Outlook（Microsoft Entra 管理中心）

1. <https://entra.microsoft.com/> → **标识 → 应用程序 → 应用注册 → 新注册**
2. 账户类型选「**任何组织目录中的账户和个人 Microsoft 账户**」
3. **身份验证**：
   - 添加平台 →「**移动和桌面应用程序**」（公共客户端，推荐，无需 secret）
   - 重定向 URI 填 Nmail 设置页显示的回调地址（默认 `http://localhost:8720/oauth/callback`；端口以设置页显示为准，用「复制回调地址」按钮）
   - **高级设置 → 允许公共客户端流 = 是**（无 secret 流程必需，漏了会报 `client assertion required`）
   - 用「Web」平台也可以：重定向 URI 同样登记，但必须创建客户端密钥并填进 Nmail 的 client_secret 框
4. **API 权限 → 添加权限 → Microsoft Graph → 委托的权限**，三个：
   - `IMAP.AccessAsUser.All`、`SMTP.Send`、`offline_access`
   - 不要加「应用程序权限」（那需要管理员同意，个人账号用不了）

## 2. 填进 Nmail 并授权

1. **设置 → 邮箱账号 → OAuth2 授权登录**：对应服务商行点「高级」→ 填 client_id（Web 型再加 client_secret）→ 保存。**回调路径**保持默认 `/oauth/callback`，并按行内显示的完整地址去控制台登记（Google/微软对 localhost 回环只豁免端口、不豁免路径）；登记为根路径的公开桌面客户端把路径改为 `/`。自建配置后即优先于内置凭证生效；「清除自建配置」回到内置凭证
2. **添加账号**：输入邮箱地址 → 点「使用 Google/Microsoft 账号授权登录」→ 浏览器完成登录 → 自动建号并后台同步
3. 已有 OAuth 账号令牌失效时，账号列表点「**重新授权**」即可，不用删号重建（刷新会用签发令牌时的同一客户端，授权后切换自建/内置不会互相干扰）

## 3. Outlook 邮箱侧开关（每邮箱一次，最易漏）

个人 Outlook 账号**默认禁用 POP/IMAP**，不开则授权全对也收不了信：

1. <https://outlook.live.com> → **设置 → 邮件 → 同步电子邮件**
2. 开启「**让设备和应用使用 POP/IMAP**」
3. 开启「**经过身份验证的 SMTP**」（否则发信报 `535 5.7.139`）
4. 新注册的 Outlook 邮箱建议先登录一次网页版再用

## 4. 大陆网络与代理

- **Gmail（imap.gmail.com）直连被墙**：Nmail 自动跟随系统代理（和浏览器一致，无需设置）——代理工具开启「系统代理」即自动识别；若工具没开「系统代理」模式，到 设置 → 通用 折叠的「手动指定代理地址」填一次（如 `socks5://127.0.0.1:7890` 或 `http://127.0.0.1:7890`）
- **代理工具必须处于运行状态**——它没开时 Gmail 授权/同步会失败（报错如实提示）
- **所有账号**的收发与授权统一走代理（无需按账号设置）；Outlook 及国内直连可达的邮箱走代理也能正常用
- 授权换令牌的通道策略：优先走代理，代理不可达自动直连兜底——代理配置坏了不影响授权
- 本机地址（127.0.0.1/localhost，如 Proton Bridge）永远直连

## 5. 排错对照表（全部真实踩过）

| 报错 | 原因 | 解法 |
|---|---|---|
| `403 org_internal` | 同意屏幕用户类型选了「内部」 | 改「外部」，并把你的邮箱加进测试用户 |
| `redirect_uri_mismatch` / `invalid_request: redirect_uri ... not valid` | 回调地址没登记或不一致 | 控制台登记 Nmail 设置页显示的回调地址（逐字一致：协议/主机/端口/路径）；路径不对时在设置页对应服务商行内改「回调路径」再重试 |
| `client_secret is missing` | Web 型客户端没填 secret | 设置页补填 client_secret，或改用桌面型客户端 |
| `invalid_client` | client_id / secret 填错 | 核对后重填（注意 Entra 密钥复制的是「值」不是「ID」） |
| `client assertion required` | 桌面流但没开公共客户端 | Entra → 高级设置 → 允许公共客户端流 = 是 |
| `access_denied` | 授权页点了取消，或未加测试用户 | Gmail 加测试用户后重试 |
| `无法连接 XX 令牌服务 ... 10061` | 代理地址端口上没有服务在听 | 代理工具开起来，或修正地址；授权换令牌会自动直连兜底 |
| `User is authenticated but not connected` | **该邮箱**没开 POP/IMAP（授权本身是好的） | 见 §3，每个 Outlook 邮箱各开一次 |
| `535 5.7.139` | 邮箱的 SMTP AUTH 被禁 | 同 §3，开「经过身份验证的 SMTP」 |
| `SSL: WRONG_VERSION_NUMBER` | 偶发的握手抖动/服务器侧瞬断 | 点同步重试；持续出现再反馈 |
| 收件正常发信失败（`missing 1 required positional argument` 等） | 旧版本 bug | 升级 Nmail |
