export interface AIProfile {
  id: string
  name: string
  base_url: string
  model: string
  /** 已存密钥明文（本地单用户应用，回显供所见即所存；空串=未设置） */
  api_key: string
  /** 上下文窗口 tokens（REDESIGN_PLAN §17.8）：缺省=1,000,000；本地小窗模型按实际值指定 */
  context_window?: number | null
}

export interface AIProfilesResp {
  profiles: AIProfile[]
  active_profile_id: string | null
  ai_enabled: boolean
}

/** 桌面通知的类型细分键；后端读侧与默认合并，缺省键视为开 */
export type NotifyTypeKey = 'new_mail' | 'ai_draft' | 'digest' | 'account_error'

export interface Settings {
  poll_interval_minutes: number
  digest_time: string
  ui_font: 'compact' | 'standard' | 'large'
  body_font: 'small' | 'standard' | 'large'
  allow_remote_images: boolean
  update_check_enabled: boolean
  /** 系统代理探测结果（只读展示，不入库） */
  detected_proxy: string | null
  /** 实际生效通道（检测到的系统代理；null=直连）——只读展示，不入库 */
  effective_proxy: string | null
  /** 通讯录自动采集（收发往来地址自动入册）；关=仅手动增改 */
  contacts_auto_collect: boolean
  /** 桌面通知总开关（应用内铃铛与未读角标不受影响） */
  desktop_notifications_enabled: boolean
  /** 桌面通知按类型细分 */
  notify_types: Partial<Record<NotifyTypeKey, boolean>>
  /** 写信/回复自动带该账号签名（设置页「写信」管理签名内容） */
  auto_insert_signature: boolean
  /** AI 晨报（§18.6）：到摘要时间自动总结未读并拟好回复草稿，替代每日摘要 */
  agent_brief_enabled: boolean
}

export interface SettingsPayload {
  poll_interval_minutes?: number
  digest_time?: string
  ui_font?: 'compact' | 'standard' | 'large'
  body_font?: 'small' | 'standard' | 'large'
  allow_remote_images?: boolean
  update_check_enabled?: boolean
  contacts_auto_collect?: boolean
  desktop_notifications_enabled?: boolean
  notify_types?: Partial<Record<NotifyTypeKey, boolean>>
  auto_insert_signature?: boolean
  agent_brief_enabled?: boolean
}

/** 本机路径（设置页「关于」展示软件本地性；均为运行进程实时解析的真实值） */
export interface SystemPaths {
  data_dir: string
  install_dir: string
  data_dir_overridden: boolean
}

export interface UpdateCheckResp {
  enabled: boolean
  current_version: string
  latest_version: string | null
  is_newer: boolean
  release_url: string
  checked_at: string | null
}

/** 桌面图标状态（GET /api/desktop-shortcut） */
export interface DesktopShortcutResp {
  installed: boolean
  healthy: boolean
  paths: string[]
  channel: string
  platform: string
  installed_at: string | null
}

/** 桌面图标安装/移除结果 */
export interface DesktopShortcutActionResp {
  ok: boolean
  paths: string[]
  error: string | null
}

/** 自更新任务状态（GET /api/update-apply）：phase = idle|downloading|verifying|pip_upgrading|ready|failed */
export interface UpdateApplyResp {
  channel: string
  can_self_update: boolean
  upgrade_hint: string | null
  phase: string
  progress: number
  error: string | null
  staged_version: string | null
  current_version: string
  updated_at: string | null
}

export interface UpdateApplyStartResp {
  ok: boolean
  already_running?: boolean
  error?: string
}

export interface AITestPayload {
  base_url?: string
  model?: string
  api_key?: string
}

export interface AITestResult {
  ok: boolean
  model: string
  reply: string | null
  latency_ms: number
  error: string | null
}

// ── P1 邮箱核心 ───────────────────────────────────────────────

export interface Account {
  id: number
  email: string
  /** 授权码明文回显（所见即所存，同 AI key；OAuth2 账号为空串） */
  password: string
  provider_name: string
  imap_server: string
  imap_port: number
  smtp_server: string
  smtp_port: number
  color: string
  /** password=授权码/密码登录；oauth2=Gmail/Outlook OAuth 授权（XOAUTH2） */
  auth_type: 'password' | 'oauth2'
  /** OAuth 服务商标识：gmail | outlook | ''（密码账号） */
  oauth_provider: string
  ai_permission: 'readonly' | 'draft_review'
  /** AI 细粒度授权（v0.4 P6）；null = 按旧 ai_permission 枚举映射 */
  ai_grants: { read: boolean; draft: boolean; organize: boolean; send: boolean; delete: boolean } | null
  /** AI 专属邮箱：默认自动模式、管线草稿低危直发 */
  is_ai_mailbox: boolean
  /** 文风提示词：AI 起草该账号回复时遵循，用户手写可编辑；null=未设置 */
  style_prompt: string | null
  status: 'ok' | 'auth_error' | 'connection_error' | 'never_synced' | 'syncing'
  status_detail: string | null
  last_sync_at: string | null
}

// ── OAuth2 授权登录（Gmail / Outlook）──

export interface OauthProviderStatus {
  key: 'gmail' | 'outlook'
  name: string
  /** 用户自建客户端已配置（优先生效；设置页展示用） */
  configured: boolean
  /** 内置公开桌面客户端凭证可用（v0.4 P5） */
  builtin_available: boolean
  /** 可发起授权（自建 OR 内置） */
  can_authorize: boolean
  /** 生效客户端来源：user=自建 | builtin=内置 */
  client_source: 'user' | 'builtin' | string
  /** 生效客户端的掩码 client_id */
  client_id_masked: string
  /** 生效客户端登记的回调路径（内置为 /；自建缺省 /oauth/callback） */
  redirect_path: string
  /** 按监听端口与回调路径拼好的完整回环地址，登记到自建 OAuth 客户端时使用 */
  redirect_uri: string
  domains: string[]
  imap_server: string
  smtp_server: string
}

export interface OauthStatusResp {
  providers: OauthProviderStatus[]
}

export interface OauthAuthorizeResp {
  auth_url: string
  state: string
}

export interface OauthFlowStatus {
  status: 'pending' | 'done' | 'error'
  detail: string
  email: string
}

export interface ProviderPreset {
  name: string
  domains: string[]
  note: string
  imap_server: string
  imap_port: number
  smtp_server: string
  smtp_port: number
}

export interface ProvidersResp {
  providers: ProviderPreset[]
  manual_note: string
}

export interface ProbeResult {
  found: boolean
  imap_server?: string
  imap_port?: number
  smtp_server?: string
  smtp_port?: number
  note: string | null
}

export interface FolderInfo {
  name: string
  delim: string
  flags: string[]
}

/** 文件夹树缓存行（v0.4 P2，folders 表派生；is_archive=该账号归档目标文件夹） */
export interface FolderCacheItem {
  name: string
  delim: string
  special_use: string | null
  subscribed: boolean
  is_system: boolean
  is_archive: boolean
  unread: number
}

export interface AccountAddPayload {
  email: string
  password: string
  imap_server?: string
  imap_port?: number
  smtp_server?: string
  smtp_port?: number
}

export interface SyncResult {
  ok: boolean
  folders: { folder: string; new_count: number; latest_subject?: string }[]
  error: string | null
}

export type Category = 'work' | 'personal' | 'notification' | 'verification' | 'promo' | 'social' | ''

export interface CategoryMeta {
  key: string
  label: string
  color: string
  badge_cls: string
}

/** /api/meta 未就绪时的内置回退；真源在后端 app/ai/categories.py（经 /api/meta 下发）。 */
export const CATEGORY_FALLBACK: CategoryMeta[] = [
  { key: 'work', label: '工作', color: '#6366f1', badge_cls: 'bg-indigo-100 text-indigo-700' },
  { key: 'personal', label: '个人', color: '#10b981', badge_cls: 'bg-emerald-100 text-emerald-700' },
  { key: 'notification', label: '通知', color: '#0ea5e9', badge_cls: 'bg-sky-100 text-sky-700' },
  { key: 'verification', label: '验证码', color: '#f59e0b', badge_cls: 'bg-amber-100 text-amber-700' },
  { key: 'promo', label: '营销', color: '#f43f5e', badge_cls: 'bg-rose-100 text-rose-600' },
  { key: 'social', label: '社交', color: '#8b5cf6', badge_cls: 'bg-violet-100 text-violet-700' },
]

export interface EmailSummary {
  id: number
  account_id: number
  account_email: string
  account_color: string
  folder: string
  uid: number
  subject: string
  sender_name: string
  sender_email: string
  date: string | null
  snippet: string
  is_read: boolean
  starred: boolean
  archived_local: boolean
  has_attachments: boolean
  category: Category
  importance: string
  needs_reply: boolean
  reply_reason: string
}

export interface EmailDetail extends EmailSummary {
  recipients: string[]
  cc: string[]
  body_text: string
  body_html: string | null
  remote_blocked: number
  remote_img_count: number
  attachments: EmailAttachment[]
}

export interface EmailAttachment {
  id: number
  filename: string
  mime: string
  size: number
  download_url: string
}

export interface EmailListResp {
  total: number
  items: EmailSummary[]
}

export interface NotificationItem {
  id: number
  type: string
  title: string
  body: string | null
  ref_id: string | null
  is_read: boolean
  created_at: string
}

export interface NotificationsResp {
  unread: number
  items: NotificationItem[]
}

// ── 写信工作台（用户手写草稿）─────────────────────────────────

export interface DraftAttachment {
  id: number
  draft_id: number
  filename: string
  mime: string
  size: number
}

export interface UserDraft {
  id: number
  account_id: number
  mode: 'new' | 'reply' | 'replyAll' | 'forward' | string
  in_reply_to: number | null
  to_addrs: string
  cc_addrs: string
  bcc_addrs: string
  subject: string
  body_html: string
  /** v0.4 P3：editing | scheduled | pending_review（AI 待审）| sent | discarded */
  status: 'editing' | 'scheduled' | 'pending_review' | 'sent' | 'discarded' | string
  /** ai = AI 拟稿（待审流），human = 手写 */
  origin: 'ai' | 'human' | string
  instruction: string | null
  send_at: string | null
  attachments: DraftAttachment[]
  created_at: string
  updated_at: string
  /** 回复目标邮件上下文（in_reply_to 关联；可能已被删除 → null） */
  email: {
    subject: string
    sender_name: string
    sender_email: string
    date: string
    snippet: string
  } | null
}

/** AI Agent 动作审计行（v0.4 P6，ai_actions 表） */
export interface AgentProposal {
  id: number
  kind: string
  pattern: string
  evidence_count: number
  sample_subjects: string | null
  status: 'pending' | 'approved' | 'rejected'
  created_at: string
  decided_at: string | null
}

export interface AgentMemory {
  id: number
  content: string
  evidence: string
  source: string
  created_at: string
  updated_at: string
}

export interface AgentAction {
  id: number
  session_id: number | null
  account_id: number | null
  account_email: string | null
  tool: string
  params: Record<string, unknown>
  mode: 'approval' | 'auto' | string
  origin: 'ui' | 'api' | string
  status: 'pending' | 'approved' | 'rejected' | 'executed' | 'failed' | 'expired' | 'undone' | string
  result: Record<string, unknown> | null
  undoable: boolean
  error: string | null
  created_at: string
  decided_at: string | null
}

/** Agent SSE 事件（text/tool_call/tool_result/approval_required/ask_user/error/done） */
export interface AgentEvent {
  type: 'text' | 'text_delta' | 'run_started' | 'tool_call' | 'tool_result'
    | 'approval_required' | 'ask_user' | 'paused' | 'error' | 'done' | string
  text?: string
  delta?: string
  tool?: string
  args?: Record<string, unknown>
  call_id?: string
  grant?: string
  ok?: boolean
  summary?: string
  action_id?: number
  reason?: string
  run_id?: number
  meta?: Record<string, unknown>
  error?: string
  question?: string
  options?: string[]
  /** 前端卡片状态（审批处理后/撤销后本地更新用，非后端字段） */
  status?: string
}

/** Agent 运行记录（A6/A8：agent_runs 行 + 步级观测，GET /api/ai/agent/runs） */
export interface AgentRunRow {
  id: number
  session_id: number | null
  mode: string
  origin: string
  status: string
  steps: number
  budget_used_ms: number
  created_at: string
  updated_at: string
}

export interface AgentRunDetail {
  run: AgentRunRow
  resumable: boolean
  pending: { tool?: string; args?: Record<string, unknown>; kind?: string } | null
  steps: {
    step: number | string
    model: string
    prompt_tokens: number
    completion_tokens: number
    ok: boolean
    at: string
  }[]
}

/** Agent 消息分段（REDESIGN_PLAN §17.4，与后端 _build_segments 同构） */
export interface AgentSegment {
  kind: 'text' | 'step' | 'approval' | 'ask_user' | 'error'
  content?: string
  tool?: string
  call_id?: string
  args?: Record<string, unknown>
  status?: 'running' | 'ok' | 'fail' | 'waiting' | string
  summary?: string
  action_id?: number
  reason?: string
  meta?: Record<string, unknown>
  run_id?: number
  echo?: boolean
  question?: string
  options?: string[]
}

/** 通讯录联系人（2026-09-12 改版：聚合行）——同邮箱多账号聚合为一行，sources 为来源集合 */
export interface ContactItem {
  id: number
  email: string
  name: string
  phone: string
  notes: string
  /** 'auto' / 'manual' 的组合（聚合各账号行） */
  sources: string[]
  use_count: number
  last_seen_at: string | null
  created_at: string
  /** 该邮箱在通讯录中的账号行数（1=单一归属） */
  account_rows: number
}

/** 自定义联系组（成员按 email 记） */
export interface ContactGroup {
  id: number
  name: string
  created_at: string
  member_count: number
  /** 仍存在于通讯录中的成员邮箱（详情页归属展示用） */
  members: string[]
}

/** 左侧树四个智能视图计数 */
export interface ContactViewCounts {
  all: number
  auto: number
  manual: number
  ungrouped: number
}

/** 联系人详情：聚合行 + 各账号明细行 */
export interface ContactDetail {
  contact: ContactItem
  rows: {
    id: number
    account_id: number | null
    email: string
    name: string
    phone: string
    source: string
    use_count: number
    last_seen_at: string | null
  }[]
}

/** 写信台模板/签名（Markdown 文本存储，插入时转 HTML） */
export interface ComposeTemplate {
  id: string
  name: string
  content: string
}

export interface ComposeSignature {
  account_id: number
  content: string
}

export interface ComposeExtras {
  templates: ComposeTemplate[]
  signatures: ComposeSignature[]
}

// ── P2 AI 层 ─────────────────────────────────────────────────

export interface Draft {
  id: number
  email_id: number
  account_id: number
  content: string
  origin: string
  status: 'pending' | 'sent' | 'discarded'
  instruction: string | null
  created_at: string
  email: {
    subject: string
    sender_name: string
    sender_email: string
    date: string | null
    snippet: string
  }
}

export interface OrganizeResult {
  classified: number
  archived: number
  drafts: number
  skipped_no_ai: boolean
}

export interface JobInfo {
  id: number
  kind: string
  account_id: number | null
  status: 'running' | 'done' | 'failed'
  progress: number
  stage: string
  detail: string
  result: Record<string, unknown> | null
}

export interface UsageStats {
  calls: number
  prompt_tokens: number
  completion_tokens: number
  failures: number
  by_day: { day: string; calls: number; tokens: number }[]
  by_task: { task_type: string; calls: number; tokens: number }[]
}

export interface SenderListEntry {
  id: number
  pattern: string
  list_type: 'whitelist' | 'blacklist' | 'image_trust'
  created_at: string
}

// ── P3 每日摘要 ──────────────────────────────────────────────

export interface DigestItem {
  email_id: number
  subject: string
  sender: string
  date: string | null
}

export interface DigestNeedReply extends DigestItem {
  reason: string
  has_draft: boolean
}

export interface DigestImportant extends DigestItem {
  category: string
  importance: string
  reason: string
}

export interface DigestData {
  date: string
  overview: {
    new_today: number
    unread: number
    auto_archived: number
    need_reply: number
  }
  by_category: Record<string, number>
  trend: { day: string; count: number }[]
  by_account: { email: string; color: string; count: number; unread: number }[]
  need_reply: DigestNeedReply[]
  important: DigestImportant[]
  ai_overview: string
  /** AI 晨报正文（§18.6：scheduler 定时运行产出，独立区块呈现；无则不存在该键） */
  agent_brief?: string
}

export interface DigestResp {
  dates: string[]
  digest: DigestData | null
}

// ── P4 AI 会话持久化 ─────────────────────────────────────────

export interface ChatSession {
  id: number
  title: string
  kind: 'manager' | string
  account_id: number | null
  pinned: boolean
  message_count?: number
  created_at: string
  updated_at: string
}

export interface ChatMessage {
  id: number
  role: 'user' | 'assistant'
  content: string
  model: string
  created_at: string
}

// ── P7 对外 API（REDESIGN_PLAN §7）────────────────────────────

export type ApiScope = 'read' | 'write' | 'send' | 'agent'

export interface ExtApiKey {
  id: number
  name: string
  /** 明文回显（secrets.json 所见即所存）；已吊销的行不含此字段 */
  key?: string
  scopes: ApiScope[]
  daily_limit: number | null
  last_used_at: string | null
  revoked: boolean
  created_at: string
}

export interface ExtKeysResp {
  enabled: boolean
  log_enabled: boolean
  rate_limit_per_min: number
  base_url: string
  keys: ExtApiKey[]
}

export interface ApiCallItem {
  id: number
  key_id: number
  key_name: string
  method: string
  path: string
  status: number
  created_at: string
}
