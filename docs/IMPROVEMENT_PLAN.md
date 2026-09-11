# Nmail 全面提升计划（docs/IMPROVEMENT_PLAN.md）

> **目的**：降低代码耦合度与后续开发难度（首要目标），同时落实全面审核发现的鲁棒性/安全/测试问题。
> **来源**：2026-09-11 全量代码审核（后端 ~4,000 行 + 前端 ~6,600 行逐行通读）与同日复查（v9/v10 迁移、写信台二期、AI 总开关、设置侧栏化、发版自动化落地后）。
> **修订 2026-09-11 15:46**：逐条对照当前代码核实后修订——R1（IMAP 超时）、R10/3.5（分块拉取）、A9 同步侧（后台化+进度）、T6（.gitignore）已由「同步引擎四步优化」系列提交（e8c0084…28ef2df）解决，移出待办；M3 缩窄为「AI 整理/批量动作异步化」；修正前端文件路径与通知横幅规模；§3.1 补充添加账号预检路径例外。
> **使用方式**：每项有稳定编号（A=解耦/R=鲁棒/S=安全/Q=去重/T=工程化）。开工按 CLAUDE.md 规范在 SESSIONS.md 登记「认领 IMPROVE-<编号>」；完成一项在本文勾选并回填提交哈希。**本文只做方案不绑实现**，动手前先读 §3 对应小节与现状代码。

---

## 0. 复查快照（2026-09-11）

上轮审核后已自行解决/部分解决的项（不再列入计划正文）：

| 原发现 | 现状 |
|---|---|
| 前端 ComposeModal 死代码 | ✅ 已删除（写信台全面接管） |
| 上传文件名路径注入 | ⚠️ 半修：`user_drafts.py:172` 已剥路径；旧端点 `emails.py:399` 未对齐（见 R4） |
| Tone DNA 黑盒 | ✅ 退役 → 文风提示词（迁移 v10，用户可控） |
| AI 无总开关 | ✅ `ai_enabled` 已加（停用=传统邮件模式） |
| 设置页平铺过长 | ✅ 侧边栏分类（但 1,031 行单文件待拆，见 Q6） |
| 发版手工 | ✅ `scripts/release.sh` + RELEASE.md |
| R1 IMAP 无超时 | ✅ 已修：`MailBox(timeout=60)`，超时并入 connection_error（e8c0084） |
| 首翻 bulk 全量驻留内存（R10/3.5） | ✅ 已修：`iter_new_mail` 25 封/块 + 断点续拉 + 块间节流（e8c0084→28ef2df） |
| 同步长任务阻塞请求（A9 同步侧） | ✅ 已修：`start_sync` 后台线程 + 账号状态实时进度，手动/添加/调度三入口全走它 |

复查后**仍然成立**的核心问题（正文逐项展开）：DB 事务边界缺失（A4）、move 后 uid 写坏（R2）、无 Origin/Host 校验（S1）、MailConfig 构造 ×8（A1）、AI 错误样板 ×9（A5）、`e.date` 字符串比较（R6）、调度器反向依赖 API 层（A2，写信台二期引入）、API→API 私有导入（A3）。~~IMAP 无超时（R1）~~ 已修。

---

## 1. 目标与原则

**三个目标（按优先级）**

1. **解耦**：消除「API 层互相 import 私有符号」「调度器依赖 API 层」「凭据/连接逻辑散布 8 处」这类跨层纠缠——新功能开发时不必再同时理解五个模块。
2. **降难**：统一重复模式（错误翻译、日志、flash、格式化），把「每个调用点都要记得 commit/翻译异常/写用量」变成「框架替你做对」；前端接口类型由后端 schema 生成，消除双维护。
3. **鲁棒**：修掉审核发现的正确性/挂起/安全洞（§4/§5）。

**改造原则（硬约束）**

- **不做大爆炸重构**：每项独立可提交、可验证、可回滚；单项违反「验证后提交」规范即停。
- **不改变产品行为**（除 bug 修复）；不违背 CLAUDE.md 关键决策（无规则引擎、无 OS 独有 API、迁移只追加、AI 人在回路）。
- **不引入重框架**：不上 ORM / asyncio 全面改写 / DI 容器 / 状态管理库；用 stdlib + 现有依赖解决。
- 收益/成本比排序；涉及刚重写的文件（写信台 compose/*、SettingsPage、Layout）开工前按规范即时重读并与看板核对。

---

## 2. 耦合与开发难度诊断（问题地图）

| # | 耦合点 | 位置 | 后果 |
|---|---|---|---|
| A1 | MailConfig 手工构造 ×8 | accounts.py ×4、emails.py、drafts.py、sync.py、（user_drafts 经 `_imap_for`） | 每个发信/收信功能都要重复「查账号→查密钥→拼配置→查 SMTP 缺失」四步 |
| A2 | **调度器 → API 层反向依赖** | `scheduler.py:59` `from app.api.user_drafts import send_draft_now` | 分层倒置；且 `send_draft_now` 抛 `HTTPException`——后台线程里抛 HTTP 异常语义错误 |
| A3 | API → API 私有导入 | `user_drafts.py:18` import `emails._imap_for/re_split`；`ai.py:13` import `chats.append_message/require_session` | 下划线符号跨模块即公共契约，改签名牵连无声 |
| A4 | 共享 SQLite 连接无事务边界 | database.py 单连接 + 各调用点自行 `commit()`、异常无 rollback | 跨线程提交互相污染；写正确性靠「每个调用点都记得做对」 |
| A5 | AI 错误翻译样板 ×9 + log_usage 样板 ×15 调用 | ai.py、drafts.py、tasks.py | 新增一个 AI 端点要复制三段样板 |
| A6 | 分类枚举散布 6 处 | prompts/tasks/pipeline/digest + types.ts + DigestPage | 加一个分类改 6 个文件，漏一处即静默 bug |
| A7 | 前端接口类型/客户端手工双维护 | src/types.ts + api/client.ts(318) | 后端改字段靠人肉同步，SettingsPage 里的 guardVersion hack 就是为此打的补丁 |
| A8 | 发送通路双轨残余 | `POST /api/emails/send`（前端零调用）与 user_drafts/drafts 三条发送路径 | 发信逻辑三处各写一遍（消毒/纯文本派生/In-Reply-To/归档 Sent） |
| A9 | 长任务耦合进 HTTP 请求生命周期（同步侧已解决） | 手动同步/添加账号/首翻已后台化（start_sync+进度）；**仍同步执行**：AI 整理（organize）、批量 IMAP 动作（trash/move） | 大账号 AI 整理 HTTP 挂起分钟级、双击重复触发 |
| A10 | 前端重复模式 | 通知横幅两套（DraftsPage flash ×8、MailBrowser syncMessage ×19）、日期/大小工具散布、聊天 UI ×2、SettingsPage 1,018 行 | 新页面继续复制粘贴，定时器清理各自为政 |

---

## 3. 解耦与降难方案（核心改造）

### 3.1 新增 `core/mailbox.py`：账号凭据/连接/发送的统一入口（解 A1、A3 前半）✅ 已完成（fadc747 建模块切 sync + 2cd5e74 API 层 7 处迁入、删 _imap_for；仅存 accounts.py 两处「密码来自请求」的文档化例外）

把「拿一个可用的账号上下文」收成唯一入口，消除 8 处 MailConfig 拼装与 `emails._imap_for` 私有导出：

```python
# core/mailbox.py（新）
class MailError(Exception):
    """业务级邮件错误；code ∈ missing_credential|not_found|smtp_missing|server"""
    def __init__(self, code: str, message: str): ...

@dataclass
class AccountHandle:
    row: sqlite3.Row          # accounts 原始行
    cfg: MailConfig           # 含 smtp_*，不再丢
    @property
    def id(self) -> int: ...

def load_account(account_id: int) -> AccountHandle:
    """查账号+密钥，缺一即抛 MailError。全项目唯一的 MailConfig 构造点。"""

@contextmanager
def open_imap(handle: AccountHandle) -> Iterator[MailBox]: ...   # 含网易 ID、超时（R1）

def send_message(handle, *, to, cc, bcc, subject, html, text=None,
                 attachment_paths=None, in_reply_to=None) -> EmailMessage:
    """唯一 SMTP 发送路径：消毒→纯文本派生→发送→归档 Sent。见 3.5。"""
```

- API 层加一个统一翻译：`MailError → HTTPException(4xx/502, message)`（放 `api/deps.py`，见 3.3）。
- `re_split` 等地址工具随迁至 `core/mailbox.py`（或 `core/addresses.py`），API 层不再互相 import。
- **迁移顺序**：先建 mailbox.py 并让 `sync.py` 切换（它已是 core 层，零风险）→ 再逐个切 accounts/emails/drafts/user_drafts → 删除 `_imap_for`。
- **例外**：`accounts.py` 添加账号的连接预检发生在账号行入库前（表单直连 `test_connection`），允许从表单构造 MailConfig，不属重复构造；SMTP 缺失检查收进 `send_message` 统一判断。

### 3.2 `database.py` 事务边界：`tx()` + 写锁（解 A4）✅ 已落地（0b549c9，与 isolation_level=None 同一提交）

现状每个调用点自己 `commit()`、异常从不 rollback、跨线程共享连接。改为「框架替你做对」：

```python
# database.py
_write_lock = threading.Lock()

@contextmanager
def tx():
    """写事务：进程内全局写锁；成功提交、异常回滚。读操作照旧用 get_conn()。"""
    with _write_lock:
        conn = get_conn()
        try:
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
```

- 连接改 `sqlite3.connect(..., isolation_level=None)`（autocommit）：单条语句立即生效（与现状实际行为一致），多语句原子性显式用 `tx()`；同时加 `PRAGMA busy_timeout=5000` 兜底跨进程。
- **两件事必须同一提交切换**（isolation_level=None 会让旧 `commit()` 变 no-op，行为等价于「每语句即提交」，现有调用点因此不需要同步改造）。
- 迁移策略：新增代码一律 `with tx() as conn:`；存量 ~30 处 `conn.commit()` 用一次机械替换收敛（`_apply_classification`、`batch_action`、`_sync_folder` 等多语句点优先）。

### 3.3 AI 层收口：统一翻译 + 日志辅助 + 枚举单一来源（解 A5、A6）✅ 已落地（6b57584 + 54ef776）

**a) `api/deps.py`（新）**——错误翻译一处定义：

```python
def ai_config_or_400(profile_id: str | None = None):
    """FastAPI 依赖：AI 未配置/停用 → 400；server 错误由各端点 502 包装。"""
def mail_error_to_http(fn):   # 装饰器或依赖二选一
    """MailError → HTTPException；其余异常 → 502（中文文案）。"""
```
ai.py ×5、drafts.py ×2 的 `except AINotConfigured/except Exception` 样板全部改走依赖。

**b) `ai/tasks.py` 日志辅助**——把 6 个函数里「成功记日志/失败记日志再 raise」收成：

```python
def _logged(task_type: str, summary: str, account_id=None):
    """上下文管理器：进入即开始计时，异常记失败日志后 re-raise，成功记用量。"""
    # 用法：with _logged("classify", f"{len(items)} 封", account_id):
    #           text, usage = llm.chat(...)
```

**c) `ai/categories.py`（新）+ `GET /api/meta`**——分类/重要度枚举单一来源：

```python
CATEGORIES = ("work", "personal", "notification", "verification", "promo", "social")
AUTO_ARCHIVE = frozenset({"promo"})
# /api/meta 返回：categories: [{key, label, color}], importance: [...]
# 前端 types.ts 的 CATEGORY_META、DigestPage 的 CATEGORY_COLORS 改为启动时拉取缓存
```
prompts 文本由 `CATEGORIES` 生成；tasks 校验、pipeline.AUTO_ARCHIVE、digest.CATEGORIES、前端徽章/图表色全部消费同一来源。**加分类从改 6 处 → 改 1 处**。

### 3.4 任务执行器 `core/jobs.py`：长任务异步化 + 进度（解 A9，范围缩窄）✅ 已落地（fde0745 基建 + 8f6b417 organize + d1c3a1b 批量 trash/move）

> 2026-09-11 修订：同步/首翻已由 `start_sync` 后台化并自带进度（本轮已落地），**本项范围缩窄为**：AI 整理（organize）、批量 IMAP 动作两个仍同步执行的入口异步化；sync 类 job 是否统一入 jobs 表（换取历史可观测性）待动手时再评估。

```sql
-- 迁移 v11（只追加）
CREATE TABLE jobs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT NOT NULL,            -- sync | organize | first_sync | digest
  account_id INTEGER,
  status TEXT NOT NULL DEFAULT 'running',   -- running | done | failed
  progress REAL NOT NULL DEFAULT 0,         -- 0..1
  stage   TEXT NOT NULL DEFAULT '',         -- connecting/fetching/storing/classifying/drafting
  detail  TEXT NOT NULL DEFAULT '',         -- 阶段明细/错误文案（面向用户）
  result_json TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

- `core/jobs.py`：`ThreadPoolExecutor(max_workers=2)` + `RUNNERS: dict[kind, fn]` 注册表；`submit(kind, **payload) -> job_id`；执行器通过 `report(stage, progress, detail)` 回写（内部走 `tx()`）。
- **改造端点**（全部改为立即返回 `{job_id}`；sync/添加账号两项已由 start_sync 解决，不再列入）：
  - `POST /api/ai/organize`、`POST /api/emails/batch-action`（IMAP 类动作 trash/move）
- **新增端点**：`GET /api/jobs/active`（列表）、`GET /api/jobs/{id}`。
- **同步复用（可选）**：start_sync 已覆盖同步场景；是否把同步历史统一入 jobs 表（获得可观测性、替代 sync 现在的裸 logger）待 M3 动手时评估。
- **per-account 锁**（防调度与手动并发同步同一账号撞服务商 IMAP 并发限制，尤其 163）：

```python
_sync_locks: dict[int, threading.Lock] = {}
def sync_lock(account_id: int) -> threading.Lock:
    with _locks_guard:
        return _sync_locks.setdefault(account_id, threading.Lock())
```
- **前端**：`useJob(jobId)` hook（轮询 1s，完成/失败即停）；MailBrowser「收信/AI 整理」按钮改为提交 job + 底部进度条（替换现有 syncMessage 机制，与 Q2 的 useFlash 协同）。

### 3.5 IMAP 客户端加固（✅ 已完成，保留作记录）

- ✅ **超时（R1）**：`MailBox(timeout=60)` 已落地（imap_client.py:66），超时并入 connection_error（e8c0084）。
- ✅ **分块拉取（R10）**：`iter_new_mail` 生成器已落地——先轻量 SEARCH UID 清单，按 25 封/块 FETCH，块级断点续拉 + 块间节流；稀疏文件夹按密度自适应逐 UID 精确拉取（e8c0084/bb9d796/28ef2df）。
- 本节不再有待办；后续若需进度百分比，在 `iter_new_mail` 的块产出点上扩展回调即可（3.4 的进度数据源）。

### 3.6 发送通路归一（解 A8，收尾）✅ 已落地（2cd5e74：send_message 唯一发送 + core/outbox 草稿发送 + 调度器脱离 API 层；端点删除于 M1 393293e）

- 三条发送路径（`/api/emails/send`、user_drafts `send_draft_now`、drafts `approve`）统一收敛到 `mailbox.send_message()`（3.1）：消毒、纯文本派生、In-Reply-To、归档 Sent 只写一遍。
- `POST /api/emails/send` + `client.ts` 的 `sendEmail` **删除**（前端已零调用）；`emails.py:399` 的裸 `f.filename` 问题随删除一并消失。
- `scheduler.send_due_drafts` 改调 `mailbox.send_message`（API 层只留薄壳），**HTTPException 不再出现在后台线程**（A2 消除）。
- 分层目标：`core/` 不 import `app.api.*`；`scheduler.py` 不 import `app.api.*`。可用 ruff `TID`/import-linter 规则固化（T4）。

### 3.7 前端提效（解 A7、A10）

**a) 接口类型生成（收益最大的单项）**

```bash
# 一次性：后端起好后导出 schema 快照（避免前端构建依赖运行中的后端）
curl http://127.0.0.1:8720/openapi.json > frontend/openapi.json
npx openapi-typescript frontend/openapi.json -o frontend/src/api/schema.d.ts
```
- `client.ts` 的返回类型逐步从手写 `types.ts` 切到 `schema['/api/emails']['get']['responses']['200']`；新端点一律走生成类型。
- **根除** SettingsPage `guardVersion` 版本守护这类漂移补丁的生存土壤（字段增删后端 schema 即真理）。
- `package.json` 加 `gen:api` script + 把 openapi.json 纳入「API 改动必更」清单。

**b) 公共件去重**

| 新增 | 替换 | 说明 |
|---|---|---|
| `hooks/useFlash.ts` | 通知横幅归一：DraftsPage flash ×8 + MailBrowser syncMessage ×19 | 内部管理 setTimeout + 卸载清理 |
| `utils/format.ts` | shortDate/formatDate/relativeTime/fmtSize（4 文件） | 一次归拢 |
| `components/ChatView.tsx` | AiPanel 与 ManagerPage 的消息列表/输入/流式拼接 | 两处行为本就一致（history 截 6 条、占位删除逻辑相同） |

**c) 大文件拆分**（动刚重写的文件，开工前与看板核对）

- `SettingsPage.tsx`（1,018 行）→ `pages/settings/`：`GeneralSection / AccountsSection / AIProfilesSection / UsageSection / AboutSection` + 侧栏骨架；侧栏分类结构刚落定，趁热拆成本最低。
- `components/MailBrowser.tsx`（711 行）→ 列表行/工具栏/批量栏三个子组件（低优先，随 M3 顺手做）。

---

## 4. 鲁棒性修复清单（审核洞察保留，复查更新）

| # | 问题 | 位置 | 修法 | 状态 |
|---|---|---|---|---|
| R1 | IMAP 无超时，调度线程可永久挂起 | imap_client.py:66 | `timeout=60` + 超时并入 connection_error | ✅ 已修（e8c0084） |
| R2 | move 拿不到新 uid 时旧 uid 写进新文件夹，撞 UNIQUE 后下次同步静默丢信 | emails.py:117,369 | 拿不到新 uid → 删除本地行交增量重建 | ✅（4c22b2f） |
| R3 | 共享连接跨线程事务污染 | database.py | 3.2 `tx()` 方案 | ✅（0b549c9） |
| R4 | `/api/emails/send` 裸 `f.filename` 路径注入 | emails.py:399 | 随 3.6 删除端点即消 | ✅ 提前完成（393293e） |
| R5 | 恶意网页可 multipart 无预检 POST 触发本机发信（drive-by）；DNS rebinding 同理 | main.py | S1 Origin/Host 校验 | ✅（9ab675a） |
| R6 | 混合时区 `e.date` 字符串比较，日界漏算/多算 | ai.py:134、digest.py:44 | 统一 `COALESCE(e.date_sort, e.date)` | ✅（56b9883） |
| R7 | notifications / ai_logs 无界增长；UIDVALIDITY 重置后附件文件成孤儿 | sync.py:202、notifications | 启动时保留策略（通知 500 条 / ai_logs 90 天）；重置分支顺带删 `attachments/<email_id>/` 目录 | ✅（e5eafc9） |
| R8 | 总管家未配 AI 时先落库了用户消息 → 孤儿消息 | ai.py chat_manager_stream | 配置解析挪到 `append_message` 之前 | ✅（d34a54a） |
| R9 | settings 表单值损坏 → 所有读取请求 500 | database.py get_setting | json.loads 包 try 返回 default | ✅（208443c） |
| R10 | 首翻 bulk 全量驻留内存 | imap_client.py | 3.5 分块拉取（已落地） | ✅ 已修（e8c0084） |

---

## 5. 安全加固

| # | 项 | 方案 |
|---|---|---|
| S1 | 本机 API 无源校验（R5） | main.py 加 ~20 行中间件：`Host` 必须为 `127.0.0.1:<port>`/`localhost:<port>`；`Origin` 存在时必须同源。静态资源与 /api 一并覆盖。不引依赖、不影响正常使用 |
| S2 | 异常文本入库卫生 | ai_logs.summary / status_detail 落库前过滤 Authorization/Sensitive 头片段；保持 `[:200]` 截断现状 |
| S3 | secrets.json | 现状（POSIX chmod、永不回传）保持；仅补一条：`set_secret` 写失败（磁盘满等）当前会抛裸异常——包成明确报错文案 |

---

## 6. 测试与工程化

| # | 项 | 内容 |
|---|---|---|
| T1 | pytest 基础层（零测试现状） | `backend/tests/`：`mail_html`（XSS 样本集：script/onclick/javascript:/收发 data: 差异/远程图计数/cid 替换）、`_extract_json`、`match_sender_list`、`reply_subject`、`_server_from_xml`、`update_check._is_newer`、迁移幂等（临时 `NMAIL_DATA_DIR` 连跑两遍）、TestClient 下 `list_emails` 筛选矩阵与 batch 归档。**纯函数层优先，不追求覆盖率** |
| T2 | ruff 扩规则 | `--select F` → `F,E9,B,SIM,UP`，修存量一次收敛；CI 与本地命令同步更新（CLAUDE.md） |
| T3 | CI 流水线 | 新增 `.github/workflows/ci.yml`：ruff + pytest + `npm run build`（现有 release.yml 只在 tag 触发，主干无门禁） |
| T4 | 分层规则固化 | ruff flake8-tidy-imports 或 import-linter：禁止 `scheduler → app.api`、禁止 `core → app.api`（3.6 完成后启用） |
| T5 | 版本号单一来源 | pyproject 与 `config.APP_VERSION` 双维护 → config 改读 `importlib.metadata.version("nmail-app")`，冻结环境回退常量 |
| T6 | 仓库卫生 | ✅ 无需动作：`.gitignore` 已含 `reference/`，仓库根不存在 referencee/ 目录（原条目为笔误，复核于 2026-09-11 修订） |

---

## 7. 里程碑路线图

> 规模标注：S=半天内 / M=1 天内 / L=2 天上下。每步遵守「文档同步 + ruff + npm build + 冒烟」；标注 ⚠ 的项触碰并行会话刚改过的文件，开工前重读。

**M1 地基与快修（✅ 已完成 2026-09-11，S-0911-1546 会话：6fbf821/4c22b2f/393293e/208443c/56b9883/d34a54a/9ab675a/fadc747/0b549c9；R1/T6 早已完成移除）**
- R2 move uid（S）｜ R4 删 /api/emails/send（S）｜ R8 孤儿消息（S）｜ R9 get_setting 容错（S）｜ R6 date_sort 比较（S）
- 3.2 `tx()` + isolation_level=None（M，同一提交切换）
- 3.1 建 `core/mailbox.py` 并切 `sync.py`（M）；S1 Origin/Host 中间件（S，注意 vite dev 代理需配 `changeOrigin: true` 否则被 Host 校验拒掉）
- 验收：ruff 通过；临时目录冒烟 `/api/health`；S1 用 curl 分别验证坏 Host/坏 Origin 被拒、正常访问放行

**M2 发送归一与 AI 收口（✅ 已完成 2026-09-11，S-0911-1632 会话：2cd5e74 / 6b57584 / 54ef776 / 9f0bc5e；真实账号发信回归待用户重启后验证）**
- 3.6 发送通路归一 + 删 `/api/emails/send`（M）｜ A2 调度器依赖消除（随 3.6）｜ T4 分层规则（S）
- 3.3 deps.py + `_logged` + `ai/categories.py` + `/api/meta` + 前端消费（M）
- 验收：AI 新端点零样板（拿 write 端点当样例对照）；真实账号发一封 user_draft + 一封 AI 草稿 approve，串线与 Sent 归档正常

**M3 AI 整理异步化（✅ 已完成 2026-09-11，S-0911-1700 会话：fde0745 / 8f6b417 / d1c3a1b / e5eafc9；真实账号大邮箱进度体验待用户重启后验证）**
- 3.4 jobs 表 + core/jobs.py + AI 整理与批量 IMAP 动作两端点改造（M）｜ 前端 useJob + 进度条（M）｜ R7 启动清理随此落地
- 验收：AI 整理 HTTP 立即返回、全程可进度可视；真实账号验证

**M4 前端提效与护栏**
- 3.7a 类型生成（S+渐进替换）｜ 3.7b useFlash/format/ChatView（M）｜ 3.7c SettingsPage 拆分（M，⚠）｜ T1 pytest 基础层（M）｜ T2/T3 ruff+CI（S）｜ T5 版本号（S）
- 验收：CI 绿；types.ts 手写接口类型清零；新增端点全程无需手写类型

---

## 8. 边界：本计划不做什么

- **不换技术栈/不加重框架**：无 ORM、无 asyncio 改写、无 DI/状态库/组件库引入。
- **不改产品边界**：不做规则引擎、不做日历/CRM/任务、不做服务端部署（CLAUDE.md 关键决策原样）。
- **不做双向同步**：只补对账能力（M3 后可视需要加「重建本地数据」按钮），IMAP 单向拉取语义不变。
- **不重写迁移历史**：v1–v10 冻结；jobs 表走 v11 只追加。
- FTS5 trigram、单进程单连接 + WAL、SSE 流式等现有选型**保持**——它们与单机定位匹配，审核确认无替换必要。
