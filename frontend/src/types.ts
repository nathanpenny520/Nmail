export interface AIProfile {
  id: string
  name: string
  base_url: string
  model: string
  /** 已存密钥明文（本地单用户应用，回显供所见即所存；空串=未设置） */
  api_key: string
}

export interface AIProfilesResp {
  profiles: AIProfile[]
  active_profile_id: string | null
  ai_enabled: boolean
}

export interface Settings {
  poll_interval_minutes: number
  digest_time: string
  ui_font: 'compact' | 'standard' | 'large'
  body_font: 'small' | 'standard' | 'large'
  allow_remote_images: boolean
  update_check_enabled: boolean
}

export interface SettingsPayload {
  poll_interval_minutes?: number
  digest_time?: string
  ui_font?: 'compact' | 'standard' | 'large'
  body_font?: 'small' | 'standard' | 'large'
  allow_remote_images?: boolean
  update_check_enabled?: boolean
}

export interface UpdateCheckResp {
  enabled: boolean
  current_version: string
  latest_version: string | null
  is_newer: boolean
  release_url: string
  checked_at: string | null
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
  provider_name: string
  imap_server: string
  imap_port: number
  smtp_server: string
  smtp_port: number
  color: string
  ai_permission: 'readonly' | 'draft_review'
  /** 文风提示词：AI 起草该账号回复时遵循，用户手写可编辑；null=未设置 */
  style_prompt: string | null
  status: 'ok' | 'auth_error' | 'connection_error' | 'never_synced' | 'syncing'
  status_detail: string | null
  last_sync_at: string | null
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
  status: 'editing' | 'scheduled' | 'sent' | 'discarded' | string
  send_at: string | null
  attachments: DraftAttachment[]
  created_at: string
  updated_at: string
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
