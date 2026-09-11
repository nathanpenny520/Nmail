import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2, MailPlus, RefreshCw, Trash2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api } from '../api/client'
import AddAccountModal from '../components/AddAccountModal'
import type { Account, AITestResult, Settings } from '../types'

const inputClass =
  'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm outline-none transition-colors focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100'

const STATUS_META: Record<Account['status'], { label: string; dot: string; text: string }> = {
  ok: { label: '正常', dot: 'bg-emerald-500', text: 'text-emerald-600' },
  auth_error: { label: '授权码可能已过期', dot: 'bg-red-500', text: 'text-red-600' },
  connection_error: { label: '连接异常', dot: 'bg-amber-500', text: 'text-amber-600' },
  never_synced: { label: '未同步', dot: 'bg-gray-300', text: 'text-gray-400' },
}

export default function SettingsPage() {
  const queryClient = useQueryClient()
  const { data, isLoading, error } = useQuery({ queryKey: ['settings'], queryFn: api.getSettings })

  const [baseUrl, setBaseUrl] = useState('')
  const [model, setModel] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [pollMinutes, setPollMinutes] = useState(5)
  const [digestTime, setDigestTime] = useState('08:30')
  const [uiFont, setUiFont] = useState<'compact' | 'standard' | 'large'>('compact')
  const [bodyFont, setBodyFont] = useState<'small' | 'standard' | 'large'>('standard')

  const [showAddAccount, setShowAddAccount] = useState(false)
  const [accountMessage, setAccountMessage] = useState<string | null>(null)

  useEffect(() => {
    if (!data) return
    setBaseUrl(data.ai.base_url)
    setModel(data.ai.model)
    setPollMinutes(data.poll_interval_minutes)
    setDigestTime(data.digest_time)
    setUiFont(data.ui_font)
    setBodyFont(data.body_font)
  }, [data])

  const saveMutation = useMutation({
    mutationFn: api.updateSettings,
    onSuccess: (saved: Settings) => {
      queryClient.setQueryData(['settings'], saved)
      setApiKey('')
    },
  })

  const testMutation = useMutation({
    mutationFn: api.testAI,
  })

  // ── 账号管理 ──
  const accountsQuery = useQuery({ queryKey: ['accounts'], queryFn: api.getAccounts })
  const accounts = accountsQuery.data?.accounts ?? []

  const syncOneMutation = useMutation({
    mutationFn: (id: number) => api.syncAccount(id),
    onSuccess: (result, id) => {
      const newCount = result.folders?.reduce((s, f) => s + f.new_count, 0) ?? 0
      const email = accounts.find((a) => a.id === id)?.email ?? id
      setAccountMessage(
        result.ok
          ? `${email} 同步完成${newCount > 0 ? `，新邮件 ${newCount} 封` : '，暂无新邮件'}`
          : `${email} 同步失败：${result.error}`,
      )
      void queryClient.invalidateQueries({ queryKey: ['accounts'] })
      setTimeout(() => setAccountMessage(null), 6000)
    },
  })

  const deleteAccountMutation = useMutation({
    mutationFn: (id: number) => api.deleteAccount(id),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['accounts'] }),
  })

  const permissionMutation = useMutation({
    mutationFn: ({ id, ai_permission }: { id: number; ai_permission: string }) =>
      api.updateAccount(id, { ai_permission }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['accounts'] }),
  })

  const usageQuery = useQuery({ queryKey: ['ai-usage'], queryFn: api.aiUsage })

  const toneMutation = useMutation({
    mutationFn: (id: number) => api.learnToneDna(id),
    onSuccess: () => {
      setAccountMessage('语气学习完成：AI 起草时会模仿你的写作风格')
      void queryClient.invalidateQueries({ queryKey: ['accounts'] })
      setTimeout(() => setAccountMessage(null), 6000)
    },
    onError: (err: Error) => {
      setAccountMessage(`语气学习失败：${err.message}`)
      setTimeout(() => setAccountMessage(null), 6000)
    },
  })

  const handleSave = () => {
    saveMutation.mutate({
      ai: { base_url: baseUrl, model, ...(apiKey ? { api_key: apiKey } : {}) },
      poll_interval_minutes: pollMinutes,
      digest_time: digestTime,
      ui_font: uiFont,
      body_font: bodyFont,
    })
  }

  const handleTest = () => {
    testMutation.mutate({
      base_url: baseUrl,
      model,
      ...(apiKey ? { api_key: apiKey } : {}),
    })
  }

  const handleClearKey = () => {
    saveMutation.mutate({ ai: { api_key: '' } })
  }

  if (isLoading) {
    return <div className="p-8 text-sm text-gray-400">加载设置中…</div>
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6 p-8">
      <h1 className="text-xl font-semibold">设置</h1>

      {/* 邮箱账号 */}
      <section className="rounded-2xl border border-gray-200 bg-white p-6 shadow-sm">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold">邮箱账号</h2>
          <button
            className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-700"
            onClick={() => setShowAddAccount(true)}
          >
            <MailPlus className="h-3.5 w-3.5" /> 添加账号
          </button>
        </div>

        <div className="mt-4 space-y-2">
          {accountsQuery.isLoading && <div className="text-sm text-gray-400">加载中…</div>}
          {!accountsQuery.isLoading && accounts.length === 0 && (
            <div className="rounded-xl border border-dashed border-gray-200 px-4 py-6 text-center text-sm text-gray-400">
              还没有添加邮箱。填入邮箱和授权码即可聚合收发。
            </div>
          )}
          {accounts.map((account) => {
            const meta = STATUS_META[account.status]
            return (
              <div
                key={account.id}
                className="flex items-center gap-3 rounded-xl border border-gray-100 bg-gray-50/60 px-4 py-3"
              >
                <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ backgroundColor: account.color }} />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-medium text-gray-800">{account.email}</div>
                  <div className="mt-0.5 text-xs">
                    <span className={`inline-flex items-center gap-1 ${meta.text}`}>
                      <span className={`h-1.5 w-1.5 rounded-full ${meta.dot}`} />
                      {meta.label}
                    </span>
                    <span className="ml-2 text-gray-400">
                      {account.provider_name}
                      {account.last_sync_at
                        ? ` · 上次同步 ${new Date(account.last_sync_at).toLocaleString('zh-CN', { hour12: false })}`
                        : ''}
                    </span>
                    {account.status_detail && (
                      <div className="mt-0.5 text-[11px] text-red-400/90">{account.status_detail}</div>
                    )}
                  </div>
                </div>
                <select
                  className="rounded-lg border border-gray-200 bg-white px-2 py-1.5 text-xs text-gray-600 outline-none focus:border-indigo-400"
                  value={account.ai_permission || 'draft_review'}
                  onChange={(e) =>
                    permissionMutation.mutate({ id: account.id, ai_permission: e.target.value })
                  }
                  title="该账号的 AI 权限"
                >
                  <option value="draft_review">AI：草稿待审</option>
                  <option value="readonly">AI：只读摘要</option>
                </select>
                <button
                  className={`rounded-lg border px-2 py-1.5 text-xs disabled:opacity-40 ${
                    account.has_tone_dna
                      ? 'border-violet-200 bg-violet-50 text-violet-600'
                      : 'border-gray-200 text-gray-500 hover:bg-white hover:text-violet-600'
                  }`}
                  title={account.has_tone_dna ? '已学习，点击可重新学习' : '从已发送邮件学习你的写作语气，AI 草稿更像你写的'}
                  onClick={() => toneMutation.mutate(account.id)}
                  disabled={toneMutation.isPending}
                >
                  {toneMutation.isPending
                    ? '学习中…'
                    : account.has_tone_dna ? '语气已学 ✓' : '学习我的语气'}
                </button>
                <button
                  className="rounded-lg border border-gray-200 p-1.5 text-gray-500 hover:bg-white hover:text-indigo-600 disabled:opacity-40"
                  title="立即同步"
                  onClick={() => syncOneMutation.mutate(account.id)}
                  disabled={syncOneMutation.isPending}
                >
                  <RefreshCw className={`h-3.5 w-3.5 ${syncOneMutation.isPending ? 'animate-spin' : ''}`} />
                </button>
                <button
                  className="rounded-lg border border-gray-200 p-1.5 text-gray-500 hover:bg-white hover:text-red-600 disabled:opacity-40"
                  title="删除账号（本地邮件与附件一并删除）"
                  onClick={() => {
                    if (confirm(`删除账号 ${account.email}？本地已下载的邮件和附件会一并删除，服务器邮件不受影响。`)) {
                      deleteAccountMutation.mutate(account.id)
                    }
                  }}
                  disabled={deleteAccountMutation.isPending}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            )
          })}
          {accountMessage && (
            <div className="rounded-lg bg-indigo-50 px-3 py-2 text-xs text-indigo-700">{accountMessage}</div>
          )}
          {accounts.some((a) => a.status === 'auth_error') && (
            <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs leading-relaxed text-red-700">
              有账号授权码失效：登录对应邮箱网页版 → 设置 → 开启 IMAP/SMTP 并重新生成授权码，
              然后删除账号重新添加（或更新授权码）。
            </div>
          )}
        </div>
      </section>

      {showAddAccount && (
        <AddAccountModal
          onClose={() => setShowAddAccount(false)}
          onAdded={(email, newCount) => {
            setShowAddAccount(false)
            void queryClient.invalidateQueries({ queryKey: ['accounts'] })
            setAccountMessage(
              `${email} 已添加${newCount > 0 ? `，首次同步到 ${newCount} 封邮件` : '，首次同步完成'}`,
            )
            setTimeout(() => setAccountMessage(null), 8000)
          }}
        />
      )}

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          设置加载失败：{(error as Error).message}
        </div>
      )}

      {/* AI 端点 */}
      <section className="rounded-2xl border border-gray-200 bg-white p-6 shadow-sm">
        <h2 className="font-semibold">AI 端点（OpenAI 兼容）</h2>
        <p className="mt-1 text-xs leading-relaxed text-gray-500">
          填入任意 OpenAI 兼容服务：OpenAI、DeepSeek、OpenRouter，或本地 Ollama / LM Studio
          （如 <code>http://localhost:11434/v1</code>，密钥可留空）。云端端点会收到邮件正文；
          指向本地端点则 0 外发。
        </p>

        <div className="mt-4 space-y-4">
          <label className="block">
            <span className="mb-1 block text-sm text-gray-600">Base URL</span>
            <input
              className={inputClass}
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              placeholder="https://api.openai.com/v1"
            />
          </label>

          <label className="block">
            <span className="mb-1 block text-sm text-gray-600">
              API Key{' '}
              {data?.ai.api_key_set && (
                <span className="ml-1 text-xs text-emerald-600">已保存（留空则保持不变）</span>
              )}
            </span>
            <input
              className={inputClass}
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder={data?.ai.api_key_set ? '••••••••' : 'sk-…（本地模型可留空）'}
              autoComplete="off"
            />
          </label>

          <label className="block">
            <span className="mb-1 block text-sm text-gray-600">模型名</span>
            <input
              className={inputClass}
              value={model}
              onChange={(e) => setModel(e.target.value)}
              placeholder="gpt-4o-mini / deepseek-chat / qwen3:8b"
            />
          </label>
        </div>

        <div className="mt-5 flex items-center gap-3">
          <button
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-700 disabled:opacity-50"
            onClick={handleSave}
            disabled={saveMutation.isPending}
          >
            {saveMutation.isPending ? '保存中…' : '保存'}
          </button>
          <button
            className="rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50 disabled:opacity-50"
            onClick={handleTest}
            disabled={testMutation.isPending}
          >
            {testMutation.isPending ? (
              <span className="inline-flex items-center gap-2">
                <Loader2 className="h-4 w-4 animate-spin" /> 测试中…
              </span>
            ) : (
              '测试连接'
            )}
          </button>
          {data?.ai.api_key_set && (
            <button
              className="text-xs text-gray-400 underline-offset-2 hover:text-red-500 hover:underline"
              onClick={handleClearKey}
            >
              清除已存密钥
            </button>
          )}
          {saveMutation.isSuccess && !saveMutation.isPending && (
            <span className="text-xs text-emerald-600">已保存</span>
          )}
          {saveMutation.isError && (
            <span className="text-xs text-red-600">保存失败：{(saveMutation.error as Error).message}</span>
          )}
        </div>

        {testMutation.data && <TestResult result={testMutation.data} />}
      </section>

      {/* 通用 */}
      <section className="rounded-2xl border border-gray-200 bg-white p-6 shadow-sm">
        <h2 className="font-semibold">通用</h2>
        <div className="mt-4 grid grid-cols-2 gap-4">
          <label className="block">
            <span className="mb-1 block text-sm text-gray-600">
              轮询间隔（分钟）<span className="ml-1 text-xs text-gray-400">立即生效</span>
            </span>
            <input
              className={inputClass}
              type="number"
              min={1}
              max={60}
              value={pollMinutes}
              onChange={(e) => setPollMinutes(Number(e.target.value))}
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-sm text-gray-600">
              每日摘要时间<span className="ml-1 text-xs text-gray-400">每天到点自动生成并提醒</span>
            </span>
            <input
              className={inputClass}
              type="time"
              value={digestTime}
              onChange={(e) => setDigestTime(e.target.value)}
            />
          </label>
        </div>
        <div className="mt-4 grid grid-cols-2 gap-4">
          <label className="block">
            <span className="mb-1 block text-sm text-gray-600">
              界面字号<span className="ml-1 text-xs text-gray-400">保存后全局生效</span>
            </span>
            <select
              className={inputClass}
              value={uiFont}
              onChange={(e) => setUiFont(e.target.value as 'compact' | 'standard' | 'large')}
            >
              <option value="compact">紧凑（小）</option>
              <option value="standard">标准</option>
              <option value="large">大</option>
            </select>
          </label>
          <label className="block">
            <span className="mb-1 block text-sm text-gray-600">
              邮件正文字号<span className="ml-1 text-xs text-gray-400">只影响邮件内容显示</span>
            </span>
            <select
              className={inputClass}
              value={bodyFont}
              onChange={(e) => setBodyFont(e.target.value as 'small' | 'standard' | 'large')}
            >
              <option value="small">小</option>
              <option value="standard">标准</option>
              <option value="large">大</option>
            </select>
          </label>
        </div>
      </section>

      {/* AI 用量 */}
      <section className="rounded-2xl border border-gray-200 bg-white p-6 shadow-sm">
        <h2 className="font-semibold">AI 用量</h2>
        {usageQuery.data ? (
          <>
            <div className="mt-3 grid grid-cols-3 gap-3 text-center">
              <div className="rounded-xl bg-gray-50 px-3 py-3">
                <div className="text-lg font-semibold text-gray-800">{usageQuery.data.calls}</div>
                <div className="text-[11px] text-gray-400">总调用</div>
              </div>
              <div className="rounded-xl bg-gray-50 px-3 py-3">
                <div className="text-lg font-semibold text-gray-800">
                  {((usageQuery.data.prompt_tokens + usageQuery.data.completion_tokens) / 1000).toFixed(1)}k
                </div>
                <div className="text-[11px] text-gray-400">总 tokens</div>
              </div>
              <div className="rounded-xl bg-gray-50 px-3 py-3">
                <div className="text-lg font-semibold text-gray-800">{usageQuery.data.failures}</div>
                <div className="text-[11px] text-gray-400">失败</div>
              </div>
            </div>
            {usageQuery.data.by_task.length > 0 && (
              <div className="mt-3 space-y-1.5">
                {usageQuery.data.by_task.map((t) => {
                  const labels: Record<string, string> = {
                    classify: '分类', draft: '草稿', chat: '对话', write: '写作辅助',
                  }
                  return (
                    <div key={t.task_type} className="flex items-center gap-2 text-xs">
                      <span className="w-16 text-gray-500">{labels[t.task_type] ?? t.task_type}</span>
                      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-gray-100">
                        <div
                          className="h-full rounded-full bg-violet-400"
                          style={{
                            width: `${Math.max(4, (t.tokens / Math.max(...usageQuery.data.by_task.map((x) => x.tokens))) * 100)}%`,
                          }}
                        />
                      </div>
                      <span className="w-24 text-right text-gray-400">
                        {t.calls} 次 · {t.tokens.toLocaleString()} tk
                      </span>
                    </div>
                  )
                })}
              </div>
            )}
          </>
        ) : (
          <p className="mt-2 text-xs text-gray-400">加载用量中…</p>
        )}
      </section>
    </div>
  )
}

function TestResult({ result }: { result: AITestResult }) {
  if (result.ok) {
    return (
      <div className="mt-4 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
        连接成功 · 模型 <b>{result.model}</b> · 延迟 {result.latency_ms} ms
        {result.reply && <> · 回复「{result.reply}」</>}
      </div>
    )
  }
  return (
    <div className="mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
      <p className="font-medium">连接失败</p>
      <p className="mt-1 break-all text-xs">{result.error}</p>
    </div>
  )
}
