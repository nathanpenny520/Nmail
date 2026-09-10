import type { AITestPayload, AITestResult, Settings, SettingsPayload } from '../types'

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
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
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

export const api = {
  getSettings: () => request<Settings>('/api/settings'),
  updateSettings: (payload: SettingsPayload) =>
    request<Settings>('/api/settings', { method: 'PUT', body: JSON.stringify(payload) }),
  testAI: (payload: AITestPayload) =>
    request<AITestResult>('/api/ai/test', { method: 'POST', body: JSON.stringify(payload) }),
}
