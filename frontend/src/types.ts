export interface AISettings {
  base_url: string
  model: string
  api_key_set: boolean
}

export interface Settings {
  ai: AISettings
  poll_interval_minutes: number
  digest_time: string
}

export interface SettingsPayload {
  ai?: {
    base_url?: string
    model?: string
    /** 空字符串表示清除已存密钥；省略表示保持不变 */
    api_key?: string
  }
  poll_interval_minutes?: number
  digest_time?: string
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
