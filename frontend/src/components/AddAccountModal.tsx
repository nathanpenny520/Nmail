import { useMutation, useQuery } from '@tanstack/react-query'
import { CheckCircle2, ChevronDown, Loader2, Radar, X, XCircle } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import type { AccountAddPayload, ProviderPreset } from '../types'

interface AddAccountModalProps {
  onClose: () => void
  onAdded: (accountEmail: string, newCount: number) => void
}

const inputClass =
  'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm outline-none transition-colors focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100'

export default function AddAccountModal({ onClose, onAdded }: AddAccountModalProps) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [imapServer, setImapServer] = useState('')
  const [imapPort, setImapPort] = useState(993)
  const [smtpServer, setSmtpServer] = useState('')
  const [smtpPort, setSmtpPort] = useState(465)

  const providersQuery = useQuery({ queryKey: ['providers'], queryFn: api.getProviders })
  const providers = providersQuery.data?.providers ?? []
  const manualNote = providersQuery.data?.manual_note ?? ''

  const detected: ProviderPreset | null = useMemo(() => {
    const domain = email.split('@')[1]?.trim().toLowerCase()
    if (!domain) return null
    return providers.find((p) => p.domains.includes(domain)) ?? null
  }, [email, providers])

  // 未命中预设时自动探测服务器配置（autoconfig / 常见主机名试连），探到即预填
  const emailValid = /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email.trim())
  const probeQuery = useQuery({
    queryKey: ['account-probe', email.trim().toLowerCase()],
    queryFn: () => api.probeAccount(email.trim()),
    enabled: emailValid && !detected,
    staleTime: Infinity,
  })
  const probed = probeQuery.data?.found ? probeQuery.data : null

  useEffect(() => {
    if (!probed) return
    if (!imapServer && probed.imap_server) {
      setImapServer(probed.imap_server)
      setImapPort(probed.imap_port ?? 993)
    }
    if (!smtpServer && probed.smtp_server) {
      setSmtpServer(probed.smtp_server)
      setSmtpPort(probed.smtp_port ?? 465)
    }
    setShowAdvanced(true) // 探测结果展示在高级区，自动展开供确认
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [probeQuery.data])

  const payload = (): AccountAddPayload => ({
    email: email.trim(),
    password,
    ...(imapServer ? { imap_server: imapServer.trim(), imap_port: imapPort } : {}),
    ...(smtpServer ? { smtp_server: smtpServer.trim(), smtp_port: smtpPort } : {}),
  })

  const testMutation = useMutation({ mutationFn: () => api.testAccount(payload()) })
  const saveMutation = useMutation({
    mutationFn: () => api.addAccount(payload()),
    onSuccess: (result) => {
      const newCount = result.sync.folders?.reduce((s, f) => s + f.new_count, 0) ?? 0
      onAdded(result.account.email, newCount)
    },
  })
  const busy = testMutation.isPending || saveMutation.isPending
  const canSubmit = email.includes('@') && password.length > 0 && !busy

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/30 p-6">
      <div className="w-full max-w-lg overflow-hidden rounded-2xl bg-white shadow-2xl">
        <div className="flex items-center justify-between border-b border-gray-100 px-5 py-3">
          <h2 className="text-sm font-semibold">添加邮箱账号</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-700">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="space-y-4 p-5">
          <label className="block">
            <span className="mb-1 block text-sm text-gray-600">邮箱地址</span>
            <input
              className={inputClass}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              autoFocus
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-sm text-gray-600">密码 / 授权码</span>
            <input
              className={inputClass}
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="多数服务商要求使用授权码，而非登录密码"
              autoComplete="off"
            />
          </label>

          {email.includes('@') && (
            <div
              className={`rounded-xl border p-3 text-xs leading-relaxed ${
                detected || probed
                  ? 'border-indigo-200 bg-indigo-50 text-indigo-800'
                  : 'border-amber-200 bg-amber-50 text-amber-800'
              }`}
            >
              {detected ? (
                <>
                  <b>已识别：{detected.name}</b>
                  <p className="mt-1">{detected.note}</p>
                </>
              ) : probed ? (
                <>
                  <b className="inline-flex items-center gap-1">
                    <Radar className="h-3.5 w-3.5" /> 已自动探测到服务器配置
                  </b>
                  <p className="mt-1">
                    IMAP <code>{probed.imap_server}:{probed.imap_port}</code> · SMTP{' '}
                    <code>{probed.smtp_server}:{probed.smtp_port}</code>
                    （已填入下方高级选项，可修改）
                  </p>
                  {probed.note && <p className="mt-1 text-indigo-600/80">{probed.note}</p>}
                </>
              ) : probeQuery.isFetching ? (
                <span className="inline-flex items-center gap-2">
                  <Loader2 className="h-3.5 w-3.5 animate-spin" /> 正在自动探测服务器配置…
                </span>
              ) : (
                <>
                  <b>未识别的服务商</b>
                  <p className="mt-1">{manualNote}</p>
                </>
              )}
            </div>
          )}

          <div>
            <button
              className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-800"
              onClick={() => setShowAdvanced((v) => !v)}
            >
              <ChevronDown className={`h-3.5 w-3.5 transition-transform ${showAdvanced ? 'rotate-180' : ''}`} />
              高级：手动指定服务器
            </button>
            {showAdvanced && (
              <div className="mt-2 grid grid-cols-2 gap-2">
                <input
                  className={inputClass}
                  value={imapServer}
                  onChange={(e) => setImapServer(e.target.value)}
                  placeholder="IMAP 服务器"
                />
                <input
                  className={inputClass}
                  type="number"
                  value={imapPort}
                  onChange={(e) => setImapPort(Number(e.target.value))}
                  placeholder="IMAP 端口"
                />
                <input
                  className={inputClass}
                  value={smtpServer}
                  onChange={(e) => setSmtpServer(e.target.value)}
                  placeholder="SMTP 服务器（发信用）"
                />
                <input
                  className={inputClass}
                  type="number"
                  value={smtpPort}
                  onChange={(e) => setSmtpPort(Number(e.target.value))}
                  placeholder="SMTP 端口"
                />
              </div>
            )}
          </div>

          {testMutation.data && (
            <div
              className={`flex items-start gap-2 rounded-lg border p-3 text-xs ${
                testMutation.data.ok
                  ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                  : 'border-red-200 bg-red-50 text-red-700'
              }`}
            >
              {testMutation.data.ok
                ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
                : <XCircle className="mt-0.5 h-4 w-4 shrink-0" />}
              {testMutation.data.detail}
            </div>
          )}
          {saveMutation.isError && (
            <div className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-700">
              <XCircle className="mt-0.5 h-4 w-4 shrink-0" />
              {(saveMutation.error as Error).message}
            </div>
          )}
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-gray-100 px-5 py-3">
          <button
            className="rounded-lg border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50"
            onClick={() => testMutation.mutate()}
            disabled={!canSubmit}
          >
            {testMutation.isPending ? '测试中…' : '测试连接'}
          </button>
          <button
            className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-5 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
            onClick={() => saveMutation.mutate()}
            disabled={!canSubmit}
          >
            {saveMutation.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            {saveMutation.isPending ? '正在保存并首次同步…' : '保存并同步'}
          </button>
        </div>
      </div>
    </div>
  )
}
