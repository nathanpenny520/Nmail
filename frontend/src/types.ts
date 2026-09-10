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
