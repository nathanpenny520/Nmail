import type {
  AITestPayload,
  AITestResult,
  Account,
  AccountAddPayload,
  AIProfile,
  AIProfilesResp,
  ChatMessage,
  ChatSession,
  ComposeExtras,
  CategoryMeta,
  Draft,
  EmailDetail,
  EmailListResp,
  FolderInfo,
  JobInfo,
  NotificationsResp,
  OauthAuthorizeResp,
  OauthFlowStatus,
  OauthStatusResp,
  ProbeResult,
  ProvidersResp,
  SenderListEntry,
  Settings,
  SettingsPayload,
  UpdateCheckResp,
  UsageStats,
  UserDraft,
  DigestResp,
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
  getUpdateCheck: (force: boolean = false) =>
    request<UpdateCheckResp>(`/api/update-check${force ? '?force=true' : ''}`),
  testAI: (payload: AITestPayload) =>
    request<AITestResult>('/api/ai/test', { method: 'POST', body: JSON.stringify(payload) }),

  // ── AI 配置档案（多模型 / 多 Key）──
  getAIProfiles: () => request<AIProfilesResp>('/api/ai/profiles'),
  createAIProfile: (payload: { name: string; base_url: string; model: string; api_key?: string }) =>
    request<{ profile: AIProfile }>('/api/ai/profiles', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  updateAIProfile: (
    id: string,
    payload: { name?: string; base_url?: string; model?: string; api_key?: string },
  ) =>
    request<{ profile: AIProfile }>(`/api/ai/profiles/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),
  deleteAIProfile: (id: string) =>
    request<{ ok: boolean }>(`/api/ai/profiles/${id}`, { method: 'DELETE' }),
  activateAIProfile: (id: string) =>
    request<{ ok: boolean; active_profile_id: string }>(`/api/ai/profiles/${id}/activate`, {
      method: 'PUT',
    }),
  setAIEnabled: (enabled: boolean) =>
    request<{ ok: boolean; ai_enabled: boolean }>('/api/ai/enabled', {
      method: 'PUT',
      body: JSON.stringify({ enabled }),
    }),
  fetchAIModels: (payload: { profile_id?: string; base_url?: string; api_key?: string }) =>
    request<{ ok: boolean; models: string[]; error: string | null }>('/api/ai/models', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  // ── 账号 ──
  getProviders: () => request<ProvidersResp>('/api/providers'),
  probeAccount: (email: string) =>
    request<ProbeResult>('/api/accounts/probe', {
      method: 'POST',
      body: JSON.stringify({ email }),
    }),
  getAccounts: () => request<{ accounts: Account[] }>('/api/accounts'),
  testAccount: (payload: AccountAddPayload) =>
    request<{ ok: boolean; detail: string; provider: string | null }>('/api/accounts/test', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  addAccount: (payload: AccountAddPayload) =>
    request<{ account: Account }>('/api/accounts', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  deleteAccount: (id: number) =>
    request<{ ok: boolean }>(`/api/accounts/${id}`, { method: 'DELETE' }),
  /** 触发后台同步，立即返回；进度经账号 status/status_detail 轮询呈现 */
  syncAccount: (id: number, folder?: string) =>
    request<{ started: boolean; reason?: string }>(
      `/api/accounts/${id}/sync${folder ? `?folder=${encodeURIComponent(folder)}` : ''}`,
      { method: 'POST' },
    ),
  getFolders: (id: number) =>
    request<{ folders: FolderInfo[] }>(`/api/accounts/${id}/folders`),
  createFolder: (id: number, name: string) =>
    request<{ ok: boolean; name: string }>(`/api/accounts/${id}/folders`, {
      method: 'POST',
      body: JSON.stringify({ name }),
    }),

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
  batchAction: (ids: number[], action: string, folder?: string) =>
    request<{ ok: boolean; updated: number; failed: number; job_id?: number }>('/api/emails/batch-action', {
      method: 'POST',
      body: JSON.stringify({ ids, action, ...(folder ? { folder } : {}) }),
    }),
  getMeta: () => request<{ categories: CategoryMeta[] }>('/api/meta'),

  // ── 写信工作台草稿 ──
  createUserDraft: (payload: Partial<UserDraft>) =>
    request<{ draft: UserDraft }>('/api/user-drafts', { method: 'POST', body: JSON.stringify(payload) }),
  getUserDrafts: (status: string = 'editing') =>
    request<{ drafts: UserDraft[] }>(`/api/user-drafts?status=${status}`),
  getUserDraft: (id: number) => request<{ draft: UserDraft }>(`/api/user-drafts/${id}`),
  updateUserDraft: (id: number, payload: Partial<UserDraft>) =>
    request<{ ok: boolean }>(`/api/user-drafts/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),
  sendUserDraft: (id: number) =>
    request<{ ok: boolean }>(`/api/user-drafts/${id}/send`, { method: 'POST' }),
  scheduleDraft: (id: number, sendAt: string) =>
    request<{ draft: UserDraft }>(`/api/user-drafts/${id}/schedule`, {
      method: 'POST',
      body: JSON.stringify({ send_at: sendAt }),
    }),
  unscheduleDraft: (id: number) =>
    request<{ draft: UserDraft }>(`/api/user-drafts/${id}/unschedule`, { method: 'POST' }),
  uploadDraftAttachments: (id: number, files: File[]) => {
    const form = new FormData()
    for (const f of files) form.append('files', f)
    return request<{ draft: UserDraft }>(`/api/user-drafts/${id}/attachments`, {
      method: 'POST',
      body: form,
    })
  },
  deleteDraftAttachment: (id: number, attId: number) =>
    request<{ draft: UserDraft }>(`/api/user-drafts/${id}/attachments/${attId}`, { method: 'DELETE' }),
  deleteUserDraft: (id: number) =>
    request<{ ok: boolean }>(`/api/user-drafts/${id}`, { method: 'DELETE' }),

  // ── 写信台模板/签名/Markdown 转换 ──
  getComposeExtras: () => request<ComposeExtras>('/api/compose-extras'),
  updateComposeExtras: (payload: ComposeExtras) =>
    request<ComposeExtras>('/api/compose-extras', { method: 'PUT', body: JSON.stringify(payload) }),
  markdownToHtml: (text: string) =>
    request<{ html: string }>('/api/compose-extras/markdown', {
      method: 'POST',
      body: JSON.stringify({ text }),
    }),

  // ── 通知 ──
  getNotifications: () => request<NotificationsResp>('/api/notifications'),
  markNotificationRead: (id: number) =>
    request<{ ok: boolean }>(`/api/notifications/${id}/read`, { method: 'POST' }),
  markNotificationsRead: () =>
    request<{ ok: boolean }>('/api/notifications/read-all', { method: 'POST' }),
  deleteNotification: (id: number) =>
    request<{ ok: boolean }>(`/api/notifications/${id}`, { method: 'DELETE' }),
  clearReadNotifications: () =>
    request<{ ok: boolean; deleted: number }>('/api/notifications/clear-read', { method: 'POST' }),

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
  deleteDraft: (id: number) =>
    request<{ ok: boolean }>(`/api/drafts/${id}`, { method: 'DELETE' }),
  reopenDraft: (id: number) =>
    request<{ ok: boolean }>(`/api/drafts/${id}/reopen`, { method: 'POST' }),
  aiChat: (payload: { email_id?: number; email_ids?: number[]; question: string; history?: { role: string; content: string }[] }) =>
    request<{ answer: string }>('/api/ai/chat', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  aiManagerChat: (payload: { question: string; history?: { role: string; content: string }[]; account_id?: number; days?: number }) =>
    request<{ answer: string }>('/api/ai/chat-manager', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  aiWrite: (payload: { text: string; op: string; instruction?: string; want_html?: boolean }) =>
    request<{ text: string; html?: string }>('/api/ai/write', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  aiOrganize: (payload: { account_id?: number; folder?: string; limit?: number }) =>
    request<{ job_id: number }>('/api/ai/organize', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  aiUsage: () => request<UsageStats>('/api/ai/usage'),

  // ── 后台任务 ──
  getJob: (id: number) => request<JobInfo>(`/api/jobs/${id}`),
  getActiveJobs: () => request<{ jobs: JobInfo[] }>('/api/jobs/active'),

  // ── AI 会话历史 ──
  getChats: () => request<{ sessions: ChatSession[] }>('/api/ai/chats'),
  createChat: (payload?: { title?: string; account_id?: number | null }) =>
    request<{ session: ChatSession }>('/api/ai/chats', {
      method: 'POST',
      body: JSON.stringify(payload ?? {}),
    }),
  getChat: (id: number) =>
    request<{ session: ChatSession; messages: ChatMessage[] }>(`/api/ai/chats/${id}`),
  updateChat: (id: number, payload: { title?: string; pinned?: boolean }) =>
    request<{ session: ChatSession }>(`/api/ai/chats/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),
  deleteChat: (id: number) =>
    request<{ ok: boolean }>(`/api/ai/chats/${id}`, { method: 'DELETE' }),

  // ── 白/黑名单 ──
  getSenderLists: () =>
    request<{ entries: SenderListEntry[] }>('/api/sender-lists'),
  addSenderList: (pattern: string, list_type: 'whitelist' | 'blacklist' | 'image_trust') =>
    request<{ ok: boolean }>('/api/sender-lists', {
      method: 'POST',
      body: JSON.stringify({ pattern, list_type }),
    }),
  removeSenderList: (id: number) =>
    request<{ ok: boolean }>(`/api/sender-lists/${id}`, { method: 'DELETE' }),
  updateAccount: (id: number, payload: {
    password?: string
    ai_permission?: string
    style_prompt?: string | null
    use_proxy?: boolean
  }) =>
    request<{ ok: boolean; account: Account }>(`/api/accounts/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),

  // ── OAuth2 授权登录（Gmail / Outlook）──
  getOauthStatus: () => request<OauthStatusResp>('/api/oauth/status'),
  saveOauthConfig: (payload: { provider: string; client_id: string; client_secret?: string; redirect_path?: string }) =>
    request<{ ok: boolean; configured: boolean }>('/api/oauth/config', {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),
  /** 发起授权：返回浏览器要打开的授权 URL，账号建/改在回调完成后发生 */
  startOauthAuthorize: (email: string, provider: string) =>
    request<OauthAuthorizeResp>('/api/oauth/authorize', {
      method: 'POST',
      body: JSON.stringify({ email, provider }),
    }),
  /** 轮询授权结果（回调页由后端直出，前端经此感知完成/失败） */
  getOauthFlow: (state: string) => request<OauthFlowStatus>(`/api/oauth/flow/${state}`),

  // ── 每日摘要 ──
  getDigest: () => request<DigestResp>('/api/digest'),
  generateDigest: () =>
    request<DigestResp['digest']>('/api/digest/generate', { method: 'POST' }),
}
