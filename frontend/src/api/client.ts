import type {
  AITestPayload,
  AITestResult,
  Account,
  AccountAddPayload,
  Draft,
  EmailDetail,
  EmailListResp,
  FolderInfo,
  NotificationsResp,
  OrganizeResult,
  ProvidersResp,
  SenderListEntry,
  Settings,
  SettingsPayload,
  SyncResult,
  UsageStats,
} from '../types'

function detailToString(detail: unknown): string {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map((item) => (typeof item === 'object' && item !== null && 'msg' in item
        ? String((item as { msg: unknown }).msg)
        : JSON.stringify(item)))
      .join('; ')
  }
  return JSON.stringify(detail)
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers)
  // FormData 交给浏览器自动设置 multipart 边界，不能手动指定 Content-Type
  if (!(init?.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  const res = await fetch(url, { ...init, headers })
  if (!res.ok) {
    let detail: unknown = res.statusText
    try {
      const body = await res.json()
      detail = body.detail ?? detail
    } catch {
      // 非 JSON 错误体，保留 statusText
    }
    throw new Error(detailToString(detail))
  }
  return res.json() as Promise<T>
}

export interface EmailQuery {
  account_id?: number | null
  folder?: string | null
  q?: string
  is_read?: boolean | null
  starred?: boolean | null
  category?: string | null
  archived?: boolean
  limit?: number
  offset?: number
}

function emailQueryString(query: EmailQuery): string {
  const params = new URLSearchParams()
  if (query.account_id != null) params.set('account_id', String(query.account_id))
  if (query.folder) params.set('folder', query.folder)
  if (query.q) params.set('q', query.q)
  if (query.is_read != null) params.set('is_read', String(query.is_read))
  if (query.starred != null) params.set('starred', String(query.starred))
  if (query.category) params.set('category', query.category)
  if (query.archived) params.set('archived', 'true')
  params.set('limit', String(query.limit ?? 50))
  params.set('offset', String(query.offset ?? 0))
  return params.toString()
}

export const api = {
  // ── 设置与 AI ──
  getSettings: () => request<Settings>('/api/settings'),
  updateSettings: (payload: SettingsPayload) =>
    request<Settings>('/api/settings', { method: 'PUT', body: JSON.stringify(payload) }),
  testAI: (payload: AITestPayload) =>
    request<AITestResult>('/api/ai/test', { method: 'POST', body: JSON.stringify(payload) }),

  // ── 账号 ──
  getProviders: () => request<ProvidersResp>('/api/providers'),
  getAccounts: () => request<{ accounts: Account[] }>('/api/accounts'),
  testAccount: (payload: AccountAddPayload) =>
    request<{ ok: boolean; detail: string; provider: string | null }>('/api/accounts/test', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  addAccount: (payload: AccountAddPayload) =>
    request<{ account: Account; sync: SyncResult }>('/api/accounts', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  deleteAccount: (id: number) =>
    request<{ ok: boolean }>(`/api/accounts/${id}`, { method: 'DELETE' }),
  syncAccount: (id: number) =>
    request<SyncResult>(`/api/accounts/${id}/sync`, { method: 'POST' }),
  getFolders: (id: number) =>
    request<{ folders: FolderInfo[] }>(`/api/accounts/${id}/folders`),

  // ── 邮件 ──
  getEmails: (query: EmailQuery) =>
    request<EmailListResp>(`/api/emails?${emailQueryString(query)}`),
  getEmail: (id: number, images: boolean) =>
    request<EmailDetail>(`/api/emails/${id}?images=${images ? 1 : 0}`),
  emailAction: (id: number, action: string, folder?: string) =>
    request<{ ok: boolean }>(`/api/emails/${id}/action`, {
      method: 'POST',
      body: JSON.stringify({ action, folder }),
    }),
  sendEmail: (form: FormData) => request<{ ok: boolean }>('/api/emails/send', { method: 'POST', body: form }),

  // ── 通知 ──
  getNotifications: () => request<NotificationsResp>('/api/notifications'),
  markNotificationsRead: () =>
    request<{ ok: boolean }>('/api/notifications/read-all', { method: 'POST' }),

  // ── AI 层 ──
  getDrafts: (status: string = 'pending') =>
    request<{ drafts: Draft[] }>(`/api/drafts?status=${status}`),
  updateDraft: (id: number, content: string) =>
    request<{ ok: boolean }>(`/api/drafts/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ content }),
    }),
  draftAction: (id: number, action: 'approve' | 'discard', content?: string) =>
    request<{ ok: boolean }>(`/api/drafts/${id}/action`, {
      method: 'POST',
      body: JSON.stringify({ action, ...(content !== undefined ? { content } : {}) }),
    }),
  regenerateDraft: (emailId: number, instruction?: string) =>
    request<{ ok: boolean; draft_id: number; content: string }>('/api/drafts/regenerate', {
      method: 'POST',
      body: JSON.stringify({ email_id: emailId, ...(instruction ? { instruction } : {}) }),
    }),
  aiChat: (payload: { email_id?: number; email_ids?: number[]; question: string; history?: { role: string; content: string }[] }) =>
    request<{ answer: string }>('/api/ai/chat', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  aiWrite: (payload: { text: string; op: string; instruction?: string }) =>
    request<{ text: string }>('/api/ai/write', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  aiOrganize: (payload: { account_id?: number; folder?: string; limit?: number }) =>
    request<OrganizeResult>('/api/ai/organize', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  aiUsage: () => request<UsageStats>('/api/ai/usage'),

  // ── 白/黑名单 ──
  getSenderLists: () =>
    request<{ entries: SenderListEntry[] }>('/api/sender-lists'),
  addSenderList: (pattern: string, list_type: 'whitelist' | 'blacklist') =>
    request<{ ok: boolean }>('/api/sender-lists', {
      method: 'POST',
      body: JSON.stringify({ pattern, list_type }),
    }),
  removeSenderList: (id: number) =>
    request<{ ok: boolean }>(`/api/sender-lists/${id}`, { method: 'DELETE' }),
  updateAccount: (id: number, payload: { password?: string; ai_permission?: string }) =>
    request<{ ok: boolean; account: Account }>(`/api/accounts/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),
}
