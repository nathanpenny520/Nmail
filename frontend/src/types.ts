export interface AIProfile {
  id: string
  name: string
  base_url: string
  model: string
  api_key_set: boolean
}

export interface AIProfilesResp {
  profiles: AIProfile[]
  active_profile_id: string | null
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
  has_tone_dna: boolean
  status: 'ok' | 'auth_error' | 'connection_error' | 'never_synced'
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

export const CATEGORY_META: Record<string, { label: string; cls: string }> = {
  work: { label: '工作', cls: 'bg-indigo-100 text-indigo-700' },
  personal: { label: '个人', cls: 'bg-emerald-100 text-emerald-700' },
  notification: { label: '通知', cls: 'bg-sky-100 text-sky-700' },
  verification: { label: '验证码', cls: 'bg-amber-100 text-amber-700' },
  promo: { label: '营销', cls: 'bg-rose-100 text-rose-600' },
  social: { label: '社交', cls: 'bg-violet-100 text-violet-700' },
}

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
  status: 'editing' | 'sent' | 'discarded' | string
  created_at: string
  updated_at: string
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
