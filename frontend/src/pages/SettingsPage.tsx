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

  const [showAddAccount, setShowAddAccount] = useState(false)
  const [accountMessage, setAccountMessage] = useState<string | null>(null)

  useEffect(() => {
    if (!data) return
    setBaseUrl(data.ai.base_url)
    setModel(data.ai.model)
    setPollMinutes(data.poll_interval_minutes)
    setDigestTime(data.digest_time)
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

  const handleSave = () => {
    saveMutation.mutate({
      ai: { base_url: baseUrl, model, ...(apiKey ? { api_key: apiKey } : {}) },
      poll_interval_minutes: pollMinutes,
      digest_time: digestTime,
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
              每日摘要时间<span className="ml-1 text-xs text-gray-400">P3 生效</span>
            </span>
            <input
              className={inputClass}
              type="time"
              value={digestTime}
              onChange={(e) => setDigestTime(e.target.value)}
            />
          </label>
        </div>
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
