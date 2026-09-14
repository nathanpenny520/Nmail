import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Copy, Eye, EyeOff, KeyRound, Plus, RotateCcw, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { api } from '../api/client'
import type { ApiScope, ExtApiKey } from '../types'

// ── 设置页「API」分类（v0.4 P7，REDESIGN_PLAN §7.2）：
// 密钥生成/重置/吊销（明文回显所见即所存）+ 调用日志。对外 API 默认关闭。

const SCOPE_META: { key: ApiScope; label: string; desc: string }[] = [
  { key: 'read', label: 'read', desc: '邮件/文件夹/通讯录/摘要 只读' },
  { key: 'write', label: 'write', desc: '标读/移动/归档/创建草稿' },
  { key: 'send', label: 'send', desc: '发送草稿' },
  { key: 'agent', label: 'agent', desc: 'AI 总管家对话（动作仍受账号授权约束）' },
]

const SCOPE_LABEL: Record<ApiScope, string> = {
  read: '读', write: '写', send: '发', agent: 'AI',
}

const SCOPE_STYLE: Record<ApiScope, string> = {
  read: 'bg-sky-50 text-sky-600',
  write: 'bg-amber-50 text-amber-600',
  send: 'bg-rose-50 text-rose-600',
  agent: 'bg-violet-50 text-violet-600',
}

function fmtLimit(n: number | null) {
  return n ? `${n}/天` : '不限'
}

export default function ExtApiSection() {
  const queryClient = useQueryClient()
  const listQuery = useQuery({ queryKey: ['extkeys'], queryFn: api.getExtKeys })
  const callsQuery = useQuery({ queryKey: ['extcalls'], queryFn: () => api.getExtApiCalls(50) })
  const data = listQuery.data
  const keys = data?.keys ?? []
  const calls = callsQuery.data?.calls ?? []

  const [creating, setCreating] = useState(false)
  const [form, setForm] = useState<{ name: string; scopes: ApiScope[]; daily_limit: string }>({
    name: '', scopes: ['read'], daily_limit: '',
  })
  const [revealed, setRevealed] = useState<number | null>(null)
  const [message, setMessage] = useState('')

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['extkeys'] })
    void queryClient.invalidateQueries({ queryKey: ['extcalls'] })
  }

  const toggleMutation = useMutation({
    mutationFn: (payload: { enabled?: boolean; log_enabled?: boolean }) =>
      api.setExtApiEnabled(payload.enabled ?? !!data?.enabled, payload.log_enabled),
    onSuccess: () => {
      setMessage('')
      invalidate()
    },
    onError: (err: Error) => setMessage(`保存失败：${err.message}`),
  })
  const createMutation = useMutation({
    mutationFn: () =>
      api.createExtKey({
        name: form.name.trim(),
        scopes: form.scopes,
        daily_limit: form.daily_limit.trim() ? Number(form.daily_limit) : null,
      }),
    onSuccess: () => {
      setCreating(false)
      setForm({ name: '', scopes: ['read'], daily_limit: '' })
      setMessage('')
      invalidate()
    },
    onError: (err: Error) => setMessage(`创建失败：${err.message}`),
  })
  const resetMutation = useMutation({
    mutationFn: (id: number) => api.updateExtKey(id, { reset: true }),
    onSuccess: invalidate,
    onError: (err: Error) => setMessage(`重置失败：${err.message}`),
  })
  const revokeMutation = useMutation({
    mutationFn: (id: number) => api.revokeExtKey(id),
    onSuccess: invalidate,
    onError: (err: Error) => setMessage(`吊销失败：${err.message}`),
  })
  const purgeMutation = useMutation({
    mutationFn: (id: number) => api.revokeExtKey(id),
    onSuccess: invalidate,
    onError: (err: Error) => setMessage(`删除失败：${err.message}`),
  })

  const activeCount = keys.filter((k) => !k.revoked).length
  const copyKey = (k: ExtApiKey) => {
    if (k.key) void navigator.clipboard.writeText(k.key)
  }

  return (
    <section className="rounded-2xl border border-gray-200 bg-white p-6 shadow-sm">
      <h2 className="t-lg font-semibold">API</h2>
      <p className="mt-1 t-sm text-gray-400">
        供你自己的脚本、自动化（快捷指令/Raycast/n8n）或其他设备（经自建隧道）调用本机邮件能力。
        服务始终只监听 127.0.0.1；隧道配置示例见{' '}
        <a
          className="text-indigo-600 underline underline-offset-2"
          href="https://nmail.whizzzest.com/docs/api/"
          target="_blank"
          rel="noreferrer"
        >
          对外 API 使用指南
        </a>
        。
      </p>

      {/* 总开关与日志开关 */}
      <div className="mt-4 space-y-2">
        <label className="flex cursor-pointer items-center gap-2">
          <input
            type="checkbox"
            className="h-4 w-4 accent-indigo-600"
            checked={!!data?.enabled}
            onChange={(e) => toggleMutation.mutate({ enabled: e.target.checked })}
          />
          <span className="t-md">启用对外 API</span>
          <span className="t-xs text-gray-400">（默认关闭；启用后 /api/ext/v1/* 才接受调用）</span>
        </label>
        <label className="flex cursor-pointer items-center gap-2">
          <input
            type="checkbox"
            className="h-4 w-4 accent-indigo-600"
            checked={data?.log_enabled ?? true}
            onChange={(e) => toggleMutation.mutate({ log_enabled: e.target.checked })}
          />
          <span className="t-md">记录调用日志</span>
          <span className="t-xs text-gray-400">（保留 30 天，含被拒绝的调用）</span>
        </label>
      </div>

      {message && <p className="mt-2 t-sm text-red-600">{message}</p>}

      {/* 用法速览 */}
      <div className="mt-4 rounded-xl border border-gray-100 bg-gray-50/60 p-3 t-sm text-gray-500">
        <div className="flex flex-wrap items-center gap-2">
          <span className="t-xs font-medium text-gray-400">基础地址</span>
          <code className="rounded bg-white px-2 py-0.5 t-xs">http://127.0.0.1:8720/api/ext/v1</code>
          <span className="t-xs text-gray-400">· 限流 {data?.rate_limit_per_min ?? 60} 次/分钟</span>
        </div>
        <pre className="mt-2 overflow-x-auto rounded-lg bg-gray-900 p-3 t-xs leading-relaxed text-gray-100">{`curl "http://127.0.0.1:8720/api/ext/v1/emails?limit=5" \\
  -H "X-Api-Key: nmail_你的密钥"`}</pre>
      </div>

      {/* 密钥列表 */}
      <div className="mt-4 flex items-center gap-2">
        <h3 className="flex items-center gap-1.5 t-md font-semibold">
          <KeyRound className="h-4 w-4 text-gray-400" /> API 密钥
          <span className="t-xs font-normal text-gray-400">（{activeCount} 个启用中）</span>
        </h3>
        <button
          className="ml-auto inline-flex shrink-0 items-center gap-1 rounded-lg bg-indigo-600 px-3 py-1.5 t-sm font-medium text-white hover:bg-indigo-700"
          onClick={() => setCreating(!creating)}
        >
          <Plus className="h-3.5 w-3.5" /> 生成密钥
        </button>
      </div>

      {creating && (
        <div className="mt-3 space-y-2 rounded-xl border border-indigo-100 bg-indigo-50/50 p-3">
          <div className="flex items-center gap-2">
            <input
              className="w-44 rounded-lg border border-gray-300 px-2.5 py-1 t-sm outline-none focus:border-indigo-500"
              placeholder="备注名（如：iOS 快捷指令）"
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              autoFocus
            />
            <input
              className="w-28 rounded-lg border border-gray-300 px-2.5 py-1 t-sm outline-none focus:border-indigo-500"
              placeholder="每日上限（空=不限）"
              value={form.daily_limit}
              onChange={(e) => setForm((f) => ({ ...f, daily_limit: e.target.value.replace(/\D/g, '') }))}
            />
            <div className="ml-auto flex gap-2">
              <button
                className="rounded-lg bg-indigo-600 px-3 py-1 t-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
                disabled={form.scopes.length === 0 || createMutation.isPending}
                onClick={() => createMutation.mutate()}
              >
                生成
              </button>
              <button
                className="rounded-lg border border-gray-300 px-3 py-1 t-sm text-gray-500 hover:bg-gray-50"
                onClick={() => setCreating(false)}
              >
                取消
              </button>
            </div>
          </div>
          <div className="flex flex-wrap gap-x-4 gap-y-1">
            {SCOPE_META.map((s) => (
              <label key={s.key} className="flex cursor-pointer items-center gap-1.5" title={s.desc}>
                <input
                  type="checkbox"
                  className="h-3.5 w-3.5 accent-indigo-600"
                  checked={form.scopes.includes(s.key)}
                  onChange={(e) =>
                    setForm((f) => ({
                      ...f,
                      scopes: e.target.checked
                        ? [...f.scopes, s.key]
                        : f.scopes.filter((x) => x !== s.key),
                    }))
                  }
                />
                <span className="t-sm">{s.label}</span>
                <span className="t-xs text-gray-400">{s.desc}</span>
              </label>
            ))}
          </div>
        </div>
      )}

      <div className="mt-3 overflow-hidden rounded-xl border border-gray-100">
        <table className="w-full text-left">
          <thead className="bg-gray-50 t-xs text-gray-400">
            <tr>
              <th className="px-3 py-2 font-medium">备注</th>
              <th className="px-3 py-2 font-medium">密钥</th>
              <th className="px-3 py-2 font-medium">Scope</th>
              <th className="px-3 py-2 font-medium">上限</th>
              <th className="px-3 py-2 font-medium">最近使用</th>
              <th className="w-20 px-3 py-2" />
            </tr>
          </thead>
          <tbody>
            {listQuery.isLoading && (
              <tr><td colSpan={6} className="px-3 py-6 text-center t-sm text-gray-400">加载中…</td></tr>
            )}
            {!listQuery.isLoading && keys.length === 0 && (
              <tr><td colSpan={6} className="px-3 py-6 text-center t-sm text-gray-300">还没有密钥——点「生成密钥」创建</td></tr>
            )}
            {keys.map((k) => (
              <tr key={k.id} className={`border-t border-gray-50 ${k.revoked ? 'opacity-50' : ''}`}>
                <td className="px-3 py-2 t-md">
                  {k.name || <span className="text-gray-300">未命名</span>}
                  {k.revoked && <span className="ml-1.5 rounded bg-gray-100 px-1 t-xs text-gray-400">已吊销</span>}
                </td>
                <td className="px-3 py-2">
                  {k.revoked ? (
                    <span className="t-xs text-gray-300">—</span>
                  ) : (
                    <span className="inline-flex items-center gap-1">
                      <code className="max-w-52 truncate rounded bg-gray-50 px-1.5 py-0.5 t-xs">
                        {revealed === k.id ? k.key : `${(k.key ?? '').slice(0, 10)}••••••••`}
                      </code>
                      <button
                        className="text-gray-300 hover:text-gray-500"
                        title={revealed === k.id ? '隐藏' : '显示完整密钥'}
                        onClick={() => setRevealed(revealed === k.id ? null : k.id)}
                      >
                        {revealed === k.id ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                      </button>
                      <button
                        className="text-gray-300 hover:text-gray-500"
                        title="复制"
                        onClick={() => copyKey(k)}
                      >
                        <Copy className="h-3.5 w-3.5" />
                      </button>
                    </span>
                  )}
                </td>
                <td className="px-3 py-2">
                  <span className="flex flex-wrap gap-1">
                    {k.scopes.map((s) => (
                      <span key={s} className={`rounded px-1.5 py-0.5 t-xs font-medium ${SCOPE_STYLE[s]}`}>
                        {SCOPE_LABEL[s]}
                      </span>
                    ))}
                  </span>
                </td>
                <td className="px-3 py-2 t-sm text-gray-500">{fmtLimit(k.daily_limit)}</td>
                <td className="px-3 py-2 t-sm text-gray-400">{k.last_used_at || '从未'}</td>
                <td className="px-3 py-2">
                  {!k.revoked ? (
                    <span className="flex justify-end gap-1">
                      <button
                        className="rounded p-1 text-gray-300 hover:bg-gray-50 hover:text-gray-500"
                        title="重置（旧密钥立即失效）"
                        onClick={() => { if (confirm(`重置「${k.name || k.id}」的密钥？使用旧密钥的脚本将立即失效。`)) resetMutation.mutate(k.id) }}
                      >
                        <RotateCcw className="h-3.5 w-3.5" />
                      </button>
                      <button
                        className="rounded p-1 text-gray-300 hover:bg-red-50 hover:text-red-500"
                        title="吊销"
                        onClick={() => { if (confirm(`吊销「${k.name || k.id}」？该密钥将立即失效。`)) revokeMutation.mutate(k.id) }}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </span>
                  ) : (
                    <span className="flex justify-end">
                      <button
                        className="rounded p-1 text-gray-300 hover:bg-red-50 hover:text-red-500"
                        title="彻底删除记录"
                        onClick={() => { if (confirm(`彻底删除「${k.name || k.id}」的吊销记录？该行从列表移除，调用日志中将显示为「已删」。`)) purgeMutation.mutate(k.id) }}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* 调用日志 */}
      <h3 className="mt-5 t-md font-semibold">调用日志 <span className="t-xs font-normal text-gray-400">（最近 50 条）</span></h3>
      <div className="mt-2 max-h-64 overflow-auto rounded-xl border border-gray-100">
        <table className="w-full text-left">
          <thead className="sticky top-0 bg-gray-50 t-xs text-gray-400">
            <tr>
              <th className="px-3 py-2 font-medium">时间</th>
              <th className="px-3 py-2 font-medium">密钥</th>
              <th className="px-3 py-2 font-medium">请求</th>
              <th className="px-3 py-2 text-right font-medium">状态</th>
            </tr>
          </thead>
          <tbody>
            {callsQuery.isLoading && (
              <tr><td colSpan={4} className="px-3 py-6 text-center t-sm text-gray-400">加载中…</td></tr>
            )}
            {!callsQuery.isLoading && calls.length === 0 && (
              <tr><td colSpan={4} className="px-3 py-6 text-center t-sm text-gray-300">暂无调用记录</td></tr>
            )}
            {calls.map((c) => (
              <tr key={c.id} className="border-t border-gray-50">
                <td className="px-3 py-1.5 t-xs text-gray-400">{c.created_at.replace('T', ' ')}</td>
                <td className="px-3 py-1.5 t-sm">{c.key_id === 0 ? '（无密钥）' : c.key_name}</td>
                <td className="px-3 py-1.5 t-sm">
                  <span className="mr-1.5 rounded bg-gray-50 px-1 t-xs font-medium text-gray-500">{c.method}</span>
                  <code className="t-xs text-gray-500">{c.path}</code>
                </td>
                <td className={`px-3 py-1.5 text-right t-xs font-medium ${c.status < 400 ? 'text-emerald-600' : 'text-red-500'}`}>
                  {c.status}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-2 t-xs text-gray-400">
        安全提示：密钥泄露 = 邮箱可被读写。建议 scope 按需最小化、定期重置，并通过调用日志关注异常调用。
      </p>
    </section>
  )
}
