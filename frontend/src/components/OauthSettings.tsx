import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, ChevronDown, Copy, ExternalLink, Loader2, ShieldCheck } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import DocsLink from './DocsLink'
import { api } from '../api/client'
import { docsUrl } from '../utils/links'
import type { Account, OauthProviderStatus } from '../types'

/**
 * OAuth2 授权登录（Gmail / Outlook）的前端公共件：
 * - useOauthAuthorize：开新窗口走授权 + 轮询回调结果（回调页由后端直出）
 * - OauthConfigCard：设置页的 OAuth 客户端配置卡（client_id 登记 + 回调地址复制）
 * - ReauthorizeButton：OAuth 账号行内的「重新授权」按钮
 */

/** 发起授权并跟踪结果；pending 期间每 1.5s 轮询一次，done/error 终态自停。 */
export function useOauthAuthorize(onDone: (email: string) => void) {
  const [state, setState] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const onDoneRef = useRef(onDone)
  onDoneRef.current = onDone

  const startMutation = useMutation({
    mutationFn: (args: { email: string; provider: string }) =>
      api.startOauthAuthorize(args.email, args.provider),
    onSuccess: (result) => {
      setError(null)
      setState(result.state)
      window.open(result.auth_url, 'nmail-oauth', 'width=560,height=720')
    },
    onError: (e) => setError((e as Error).message),
  })

  useEffect(() => {
    if (!state) return
    let alive = true
    const timer = setInterval(() => {
      api.getOauthFlow(state)
        .then((flow) => {
          if (!alive) return
          if (flow.status === 'done') {
            setState(null)
            onDoneRef.current(flow.email)
          } else if (flow.status === 'error') {
            setState(null)
            setError(flow.detail || '授权失败，请重试')
          }
        })
        .catch(() => { /* 404（过期）等：静默重试，用户可在弹窗里重新走流程 */ })
    }, 1500)
    return () => {
      alive = false
      clearInterval(timer)
    }
  }, [state])

  return {
    start: startMutation.mutate,
    pending: startMutation.isPending || state !== null,
    error,
    setError,
  }
}

const inputClass =
  'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 t-md outline-none transition-colors focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100'

function ProviderRow({ provider }: { provider: OauthProviderStatus }) {
  const queryClient = useQueryClient()
  const [editing, setEditing] = useState(false)
  const [clientId, setClientId] = useState('')
  const [clientSecret, setClientSecret] = useState('')
  const [redirectPath, setRedirectPath] = useState('/')
  const [copied, setCopied] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

  const saveMutation = useMutation({
    mutationFn: () => api.saveOauthConfig({
      provider: provider.key,
      client_id: clientId.trim(),
      client_secret: clientSecret.trim(),
      redirect_path: redirectPath.trim(),
    }),
    onSuccess: (result) => {
      setEditing(false)
      setMessage(result.configured ? '已保存，自建客户端优先生效' : '已清除，回到内置凭证')
      setTimeout(() => setMessage(null), 4000)
      void queryClient.invalidateQueries({ queryKey: ['oauth-status'] })
    },
    onError: (e) => {
      setMessage((e as Error).message)
      setTimeout(() => setMessage(null), 6000)
    },
  })

  // 状态徽章：自建已配置（优先生效）＞ 内置凭证可用
  const badge = provider.configured
    ? { cls: 'bg-emerald-50 text-emerald-600', text: `自建客户端 ${provider.client_id_masked}` }
    : { cls: 'bg-blue-50 text-blue-600', text: '内置凭证 · 可直接授权' }

  return (
    <div className="rounded-xl border border-gray-100 bg-gray-50/60 px-4 py-3">
      <div className="flex items-center gap-3">
        <ShieldCheck className={`h-4 w-4 shrink-0 ${provider.can_authorize ? 'text-emerald-500' : 'text-gray-300'}`} />
        <div className="min-w-0 flex-1">
          <div className="t-md font-medium text-gray-800">
            {provider.name}
            <span className={`ml-2 rounded-full px-2 py-0.5 t-sm ${badge.cls}`}>{badge.text}</span>
          </div>
          <div className="mt-0.5 t-sm text-gray-400">
            支持域名：{provider.domains.join(' / ')}
          </div>
        </div>
        {message && <span className="t-sm text-indigo-600">{message}</span>}
        <button
          className="shrink-0 rounded-lg border border-gray-200 px-2.5 py-1.5 t-sm text-gray-600 hover:bg-white hover:text-indigo-600"
          onClick={() => {
            setEditing((v) => {
              if (!v) {
                setRedirectPath(provider.configured ? provider.redirect_path : '/oauth/callback')
                setClientId('')
                setClientSecret('')
              }
              return !v
            })
            setMessage(null)
          }}
        >
          高级
        </button>
      </div>
      {editing && (
        <div className="mt-3 space-y-2">
          <p className="t-xs leading-relaxed text-gray-500">
            高级：使用你自己的 OAuth 客户端（自建永远优先于内置凭证）。把下方回调地址登记到你的客户端，再把 client_id 填进来。
          </p>
          <input
            className={inputClass}
            value={clientId}
            onChange={(e) => setClientId(e.target.value)}
            placeholder={provider.key === 'gmail' ? '形如 1234-abc.apps.googleusercontent.com' : 'Application (client) ID'}
            autoComplete="off"
          />
          <input
            className={inputClass}
            type="password"
            value={clientSecret}
            onChange={(e) => setClientSecret(e.target.value)}
            placeholder="client_secret（桌面应用/纯 PKCE 可留空）"
            autoComplete="off"
          />
          <input
            className={inputClass}
            value={redirectPath}
            onChange={(e) => setRedirectPath(e.target.value)}
            placeholder="回调路径：自建客户端用 /oauth/callback，登记为根路径的公开桌面客户端用 /"
            autoComplete="off"
          />
          <div className="flex items-center gap-2">
            <code className="min-w-0 flex-1 truncate rounded bg-gray-100 px-2 py-1 t-xs text-gray-700">{provider.redirect_uri}</code>
            <button
              className="inline-flex shrink-0 items-center gap-1 rounded border border-gray-200 px-2 py-1 t-xs text-gray-600 hover:bg-gray-50"
              disabled={!provider.redirect_uri}
              onClick={() => {
                void navigator.clipboard.writeText(provider.redirect_uri)
                setCopied(true)
                setTimeout(() => setCopied(false), 2000)
              }}
            >
              {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
              {copied ? '已复制' : '复制'}
            </button>
          </div>
          <div className="flex items-center gap-2">
            <button
              className="rounded-lg bg-indigo-600 px-3 py-1.5 t-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
              disabled={!clientId.trim() || saveMutation.isPending}
              onClick={() => saveMutation.mutate()}
            >
              {saveMutation.isPending ? '保存中…' : '保存'}
            </button>
            {provider.configured && (
              <button
                className="rounded-lg border border-gray-200 px-3 py-1.5 t-sm text-gray-500 hover:bg-white hover:text-red-600 disabled:opacity-50"
                disabled={saveMutation.isPending}
                onClick={() => {
                  setClientId('')
                  setClientSecret('')
                  saveMutation.mutate()
                }}
              >
                清除自建配置
              </button>
            )}
            <span className="t-xs text-gray-400">
              详细步骤与报错对照见 <DocsLink href={docsUrl('oauth/')}>官网 OAuth2 使用指南</DocsLink>
            </span>
          </div>
        </div>
      )}
    </div>
  )
}

export function OauthConfigCard() {
  const statusQuery = useQuery({ queryKey: ['oauth-status'], queryFn: api.getOauthStatus })
  const [open, setOpen] = useState(false)
  const providers = statusQuery.data?.providers ?? []
  const allAuthorizable = providers.length > 0 && providers.every((p) => p.can_authorize)

  return (
    <div className="rounded-xl border border-indigo-100 bg-indigo-50/40 px-4 py-3">
      <button
        className="flex w-full items-center gap-2 text-left"
        onClick={() => setOpen((v) => !v)}
      >
        <ChevronDown className={`h-4 w-4 shrink-0 text-indigo-500 transition-transform ${open ? 'rotate-180' : ''}`} />
        <span className="flex-1 t-md font-medium text-indigo-900">
          OAuth2 授权登录（Gmail / Outlook）
          {allAuthorizable && <span className="ml-2 rounded-full bg-emerald-100 px-2 py-0.5 t-sm text-emerald-700">可直接授权</span>}
        </span>
        <span className="t-sm text-indigo-400">免授权码直连，Google/微软已停用密码登录</span>
      </button>
      {open && (
        <div className="mt-3 space-y-3">
          {/* 快速授权（默认）：内置公开桌面客户端凭证，零配置直接授权 */}
          <div className="rounded-lg bg-white/70 px-3 py-2 t-sm leading-relaxed text-gray-600">
            <div className="font-medium text-gray-700">快速授权（默认）</div>
            <p className="mt-0.5">
              添加账号 → 输入邮箱地址 → 点「授权登录」→ 浏览器完成登录即可，无需注册任何应用。
              凭证为公开信息（源自开源邮件客户端公开源码），Nmail 与凭证来源方无官方关联；
              如被服务商限制，可在下方各服务商行的「高级」中配置自己的客户端。
            </p>
          </div>
          {providers.map((p) => <ProviderRow key={p.key} provider={p} />)}
        </div>
      )}
    </div>
  )
}

/** OAuth 账号行内的重新授权：令牌失效/撤销后一键续期（同邮箱，不重建账号）。 */
export function ReauthorizeButton({ account, onDone }: {
  account: Account
  onDone?: (email: string) => void
}) {
  const [justFinished, setJustFinished] = useState(false)
  const flow = useOauthAuthorize((email) => {
    setJustFinished(true)
    setTimeout(() => setJustFinished(false), 4000)
    onDone?.(email)
  })
  useEffect(() => {
    if (!flow.error) return
    window.alert(flow.error)
    flow.setError(null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [flow.error])
  return (
    <button
      className="inline-flex shrink-0 items-center gap-1 rounded-lg border border-gray-200 px-2 py-1.5 t-sm text-gray-500 hover:bg-white hover:text-emerald-600 disabled:opacity-40"
      title="重新授权：打开浏览器完成登录，刷新访问令牌（不改邮箱地址与本地数据）"
      disabled={flow.pending}
      onClick={() => flow.start({ email: account.email, provider: account.oauth_provider })}
    >
      {flow.pending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ExternalLink className="h-3.5 w-3.5" />}
      {flow.pending ? '等待授权…' : justFinished ? '已授权' : '重新授权'}
    </button>
  )
}
