import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { BadgeCheck, BarChart3, Bot, Eye, EyeOff, Info, Loader2, Mail, MailPlus, Plus, RefreshCw, SlidersHorizontal, Trash2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api } from '../api/client'
import AddAccountModal from '../components/AddAccountModal'
import { OauthConfigCard, ReauthorizeButton } from '../components/OauthSettings'
import type { Account, AITestResult, AIProfile, Settings } from '../types'

const inputClass =
  'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 t-md outline-none transition-colors focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100'

const STATUS_META: Record<Account['status'], { label: string; dot: string; text: string }> = {
  ok: { label: '正常', dot: 'bg-emerald-500', text: 'text-emerald-600' },
  auth_error: { label: '授权码可能已过期', dot: 'bg-red-500', text: 'text-red-600' },
  connection_error: { label: '连接异常', dot: 'bg-amber-500', text: 'text-amber-600' },
  never_synced: { label: '未同步', dot: 'bg-gray-300', text: 'text-gray-400' },
  syncing: { label: '同步中', dot: 'bg-sky-400 animate-pulse', text: 'text-sky-600' },
}

const TASK_LABELS: Record<string, string> = {
  classify: '分类', draft: '草稿', chat: '对话', write: '写作辅助',
  digest: '每日摘要',
}

// token 数显示：≥1万 显示「x.x万」，否则千分位
const fmtTokens = (n: number) =>
  n >= 10000 ? `${(n / 10000).toFixed(1).replace(/\.0$/, '')}万` : n.toLocaleString()

// ── 设置侧边栏分类 ──
const SECTIONS = [
  { key: 'general', label: '通用', icon: SlidersHorizontal },
  { key: 'accounts', label: '邮箱账号', icon: Mail },
  { key: 'ai', label: 'AI 配置', icon: Bot },
  { key: 'usage', label: 'AI 用量', icon: BarChart3 },
  { key: 'about', label: '关于', icon: Info },
] as const
type SectionKey = (typeof SECTIONS)[number]['key']

export default function SettingsPage() {
  const queryClient = useQueryClient()
  const { data, isLoading, error } = useQuery({ queryKey: ['settings'], queryFn: api.getSettings })

  const [section, setSection] = useState<SectionKey>(() => {
    const saved = localStorage.getItem('nmail_settings_section')
    return SECTIONS.some((s) => s.key === saved) ? (saved as SectionKey) : 'general'
  })
  useEffect(() => {
    localStorage.setItem('nmail_settings_section', section)
  }, [section])

  const [pollMinutes, setPollMinutes] = useState(5)
  const [digestTime, setDigestTime] = useState('08:30')
  const [uiFont, setUiFont] = useState<'compact' | 'standard' | 'large'>('compact')
  const [bodyFont, setBodyFont] = useState<'small' | 'standard' | 'large'>('standard')
  const [allowRemoteImages, setAllowRemoteImages] = useState(false)

  const [showAddAccount, setShowAddAccount] = useState(false)
  const [accountMessage, setAccountMessage] = useState<string | null>(null)
  const [showNewProfile, setShowNewProfile] = useState(false)
  const [styleOpenId, setStyleOpenId] = useState<number | null>(null)
  const [settingsError, setSettingsError] = useState('')

  useEffect(() => {
    if (!data) return
    setPollMinutes(data.poll_interval_minutes)
    setDigestTime(data.digest_time)
    setUiFont(data.ui_font)
    setBodyFont(data.body_font)
    setAllowRemoteImages(data.allow_remote_images)
  }, [data])

  // 版本守护：响应缺新字段说明后端进程是旧版本（旧 Pydantic 会静默忽略未知字段）
  const guardVersion = (saved: Settings) => {
    queryClient.setQueryData(['settings'], saved)
    if (saved.ui_font === undefined || saved.poll_interval_minutes === undefined) {
      setSettingsError('后端版本较旧，设置未能真正保存——请重启 python run.py 后重试')
    } else {
      setSettingsError('')
    }
  }

  // 通用表单（轮询/摘要时间）：改动后由底部粘性保存栏统一提交
  const saveMutation = useMutation({
    mutationFn: api.updateSettings,
    onSuccess: guardVersion,
  })
  const handleSave = () =>
    saveMutation.mutate({ poll_interval_minutes: pollMinutes, digest_time: digestTime })
  const discardChanges = () => {
    if (!data) return
    setPollMinutes(data.poll_interval_minutes)
    setDigestTime(data.digest_time)
  }
  const dirty =
    !!data && (pollMinutes !== data.poll_interval_minutes || digestTime !== data.digest_time)

  // 字号：选择即保存、即时生效
  const fontMutation = useMutation({
    mutationFn: api.updateSettings,
    onSuccess: guardVersion,
    onError: (err: Error) => setSettingsError(`保存失败：${err.message}`),
  })
  const changeUiFont = (v: 'compact' | 'standard' | 'large') => {
    setUiFont(v)
    fontMutation.mutate({ ui_font: v })
  }
  const changeBodyFont = (v: 'small' | 'standard' | 'large') => {
    setBodyFont(v)
    fontMutation.mutate({ body_font: v })
  }
  const changeRemoteImages = (v: boolean) => {
    setAllowRemoteImages(v)
    fontMutation.mutate({ allow_remote_images: v })
  }

  // 更新检查：开关即存；「检查更新」跳过 24h 缓存立即对比一次
  const updateCheckQuery = useQuery({
    queryKey: ['update-check'],
    queryFn: () => api.getUpdateCheck(false),
    staleTime: 10 * 60_000,
    retry: false,
  })
  const updateToggleMutation = useMutation({
    mutationFn: (enabled: boolean) => api.updateSettings({ update_check_enabled: enabled }),
    onSuccess: (saved) => {
      guardVersion(saved)
      void queryClient.invalidateQueries({ queryKey: ['update-check'] })
    },
    onError: (err: Error) => setSettingsError(`保存失败：${err.message}`),
  })
  const checkUpdateMutation = useMutation({
    mutationFn: () => api.getUpdateCheck(true),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['update-check'] })
      void queryClient.invalidateQueries({ queryKey: ['notifications'] })
    },
  })
  const updateState = checkUpdateMutation.data ?? updateCheckQuery.data

  // ── AI 配置档案 ──
  const profilesQuery = useQuery({ queryKey: ['ai-profiles'], queryFn: api.getAIProfiles })
  const profiles = profilesQuery.data?.profiles ?? []
  const activeProfileId = profilesQuery.data?.active_profile_id ?? null
  const aiEnabled = profilesQuery.data?.ai_enabled ?? true
  const aiEnabledMutation = useMutation({
    mutationFn: (enabled: boolean) => api.setAIEnabled(enabled),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['ai-profiles'] }),
    onError: (err: Error) => setSettingsError(`保存失败：${err.message}`),
  })

  // ── 账号管理 ──
  // 同步为后台任务：有账号在同步时 2s 轮询状态（进度显示在账号行），全部结束即停
  const accountsQuery = useQuery({
    queryKey: ['accounts'],
    queryFn: api.getAccounts,
    refetchInterval: (query) =>
      query.state.data?.accounts.some((a) => a.status === 'syncing') ? 2000 : false,
  })
  const accounts = accountsQuery.data?.accounts ?? []

  const syncOneMutation = useMutation({
    mutationFn: (id: number) => api.syncAccount(id),
    onSuccess: (result, id) => {
      const email = accounts.find((a) => a.id === id)?.email ?? id
      setAccountMessage(
        result.started
          ? `${email} 正在后台同步，完成后会通知；进度见账号状态`
          : `${email} 已在同步中，请稍候`,
      )
      void queryClient.invalidateQueries({ queryKey: ['accounts'] })
      setTimeout(() => setAccountMessage(null), 6000)
    },
    onError: (err: Error) => {
      setAccountMessage(`同步触发失败：${err.message}`)
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

  if (isLoading) {
    return <div className="p-8 t-md text-gray-400">加载设置中…</div>
  }

  return (
    <div className="mx-auto flex max-w-4xl gap-8 p-8">
      {/* 侧边栏分类 */}
      <div className="w-36 shrink-0">
        <h1 className="t-lg font-semibold">设置</h1>
        <nav className="mt-4 space-y-0.5">
          {SECTIONS.map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              onClick={() => setSection(key)}
              className={`flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 t-md transition-colors ${
                section === key
                  ? 'bg-indigo-50 font-medium text-indigo-700'
                  : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
              }`}
            >
              <Icon className="h-4 w-4 shrink-0" />
              {label}
            </button>
          ))}
        </nav>
      </div>

      <div className="min-w-0 flex-1 space-y-6">
        {settingsError && (
          <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 t-md text-amber-800">
            ⚠ {settingsError}
          </div>
        )}

        {error && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 t-md text-red-700">
            设置加载失败：{(error as Error).message}
          </div>
        )}

        {/* ── 通用 ── */}
        {section === 'general' && (
          <section className="rounded-2xl border border-gray-200 bg-white p-6 shadow-sm">
            <h2 className="t-lg font-semibold">通用</h2>
            <div className="mt-4 grid grid-cols-2 gap-4">
              <label className="block">
                <span className="mb-1 block t-md text-gray-600">
                  轮询间隔（分钟）<span className="ml-1 t-sm text-gray-400">立即生效</span>
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
                <span className="mb-1 block t-md text-gray-600">
                  每日摘要时间<span className="ml-1 t-sm text-gray-400">每天到点自动生成并提醒</span>
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
                <span className="mb-1 block t-md text-gray-600">
                  界面字号
                  <span className="ml-1 t-sm text-gray-400">
                    {fontMutation.isPending ? '保存中…' : '选择即生效'}
                  </span>
                </span>
                <select
                  className={inputClass}
                  value={uiFont}
                  onChange={(e) => changeUiFont(e.target.value as 'compact' | 'standard' | 'large')}
                >
                  <option value="compact">紧凑（小）</option>
                  <option value="standard">标准</option>
                  <option value="large">大</option>
                </select>
              </label>
              <label className="block">
                <span className="mb-1 block t-md text-gray-600">
                  邮件正文字号<span className="ml-1 t-sm text-gray-400">选择即生效，只影响邮件内容</span>
                </span>
                <select
                  className={inputClass}
                  value={bodyFont}
                  onChange={(e) => changeBodyFont(e.target.value as 'small' | 'standard' | 'large')}
                >
                  <option value="small">小</option>
                  <option value="standard">标准</option>
                  <option value="large">大</option>
                </select>
              </label>
            </div>
            <label className="mt-4 block">
              <span className="mb-1 block t-md text-gray-600">
                显示邮件外部图片<span className="ml-1 t-sm text-gray-400">选择即生效；默认拦截以防追踪像素，也可在邮件内对单个发件人「始终显示」</span>
              </span>
              <select
                className={inputClass}
                value={allowRemoteImages ? 'show' : 'block'}
                onChange={(e) => changeRemoteImages(e.target.value === 'show')}
              >
                <option value="block">默认拦截（推荐）</option>
                <option value="show">直接显示</option>
              </select>
            </label>
          </section>
        )}

        {/* ── 邮箱账号 ── */}
        {section === 'accounts' && (
          <section className="rounded-2xl border border-gray-200 bg-white p-6 shadow-sm">
            <div className="flex items-center justify-between">
              <h2 className="t-lg font-semibold">邮箱账号</h2>
              <button
                className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-1.5 t-sm font-medium text-white hover:bg-indigo-700"
                onClick={() => setShowAddAccount(true)}
              >
                <MailPlus className="h-3.5 w-3.5" /> 添加账号
              </button>
            </div>

            <div className="mt-4 space-y-2">
              <OauthConfigCard />
              {accountsQuery.isLoading && <div className="t-md text-gray-400">加载中…</div>}
              {!accountsQuery.isLoading && accounts.length === 0 && (
                <div className="rounded-xl border border-dashed border-gray-200 px-4 py-6 text-center t-md text-gray-400">
                  还没有添加邮箱。填入邮箱和授权码即可聚合收发。
                </div>
              )}
              {accounts.map((account) => {
                const meta = STATUS_META[account.status] ?? STATUS_META.never_synced
                return (
                  <div
                    key={account.id}
                    className="rounded-xl border border-gray-100 bg-gray-50/60 px-4 py-3"
                  >
                    <div className="flex items-center gap-3">
                      <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ backgroundColor: account.color }} />
                      <div className="min-w-0 flex-1">
                        <div className="truncate t-md font-medium text-gray-800">{account.email}</div>
                        <div className="mt-0.5 t-sm">
                          <span className={`inline-flex items-center gap-1 ${meta.text}`}>
                            <span className={`h-1.5 w-1.5 rounded-full ${meta.dot}`} />
                            {meta.label}
                          </span>
                          <span className="ml-2 text-gray-400">
                            {account.provider_name}
                            {account.auth_type === 'oauth2' && (
                              <span className="ml-1.5 rounded-full bg-emerald-50 px-1.5 py-0.5 text-[10px] text-emerald-600">OAuth2</span>
                            )}
                            {account.last_sync_at
                              ? ` · 上次同步 ${new Date(account.last_sync_at).toLocaleString('zh-CN', { hour12: false })}`
                              : ''}
                          </span>
                          {account.status_detail && (
                            <div className={`mt-0.5 t-xs ${account.status === 'syncing' ? 'text-sky-500' : 'text-red-400/90'}`}>
                              {account.status_detail}
                            </div>
                          )}
                        </div>
                      </div>
                      <select
                        className="rounded-lg border border-gray-200 bg-white px-2 py-1.5 t-sm text-gray-600 outline-none focus:border-indigo-400"
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
                        className={`shrink-0 rounded-lg border px-2 py-1.5 t-sm ${
                          account.style_prompt
                            ? 'border-violet-200 bg-violet-50 text-violet-600'
                            : 'border-gray-200 text-gray-500 hover:bg-white hover:text-violet-600'
                        }`}
                        title="自定义文风提示词：AI 起草该账号的回复时遵循，内容完全由你撰写"
                        onClick={() => setStyleOpenId(styleOpenId === account.id ? null : account.id)}
                      >
                        {account.style_prompt ? '文风 ✓' : '文风'}
                      </button>
                      {account.auth_type === 'oauth2' && (
                        <ReauthorizeButton
                          account={account}
                          onDone={() => void queryClient.invalidateQueries({ queryKey: ['accounts'] })}
                        />
                      )}
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
                    {styleOpenId === account.id && (
                      <StylePromptEditor account={account} onClose={() => setStyleOpenId(null)} />
                    )}
                  </div>
                )
              })}
              {accountMessage && (
                <div className="rounded-lg bg-indigo-50 px-3 py-2 t-sm text-indigo-700">{accountMessage}</div>
              )}
              {accounts.some((a) => a.status === 'auth_error') && (
                <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 t-sm leading-relaxed text-red-700">
                  有账号登录凭据失效：OAuth2 账号点「重新授权」完成登录即可；
                  授权码账号请登录对应邮箱网页版 → 设置 → 开启 IMAP/SMTP 并重新生成授权码，
                  然后删除账号重新添加（或更新授权码）。
                </div>
              )}
            </div>
          </section>
        )}

        {showAddAccount && (
          <AddAccountModal
            onClose={() => setShowAddAccount(false)}
            onAdded={(email) => {
              setShowAddAccount(false)
              void queryClient.invalidateQueries({ queryKey: ['accounts'] })
              setAccountMessage(`${email} 已添加，正在后台同步首屏邮件（最近 30 天）…`)
              setTimeout(() => setAccountMessage(null), 8000)
            }}
          />
        )}

        {/* ── AI 配置 ── */}
        {section === 'ai' && (
          <section className="rounded-2xl border border-gray-200 bg-white p-6 shadow-sm">
            <div className="flex items-center justify-between">
              <h2 className="t-lg font-semibold">AI 配置（OpenAI 兼容）</h2>
              <button
                className="inline-flex items-center gap-1.5 rounded-lg bg-violet-600 px-3 py-1.5 t-sm font-medium text-white hover:bg-violet-700"
                onClick={() => setShowNewProfile((v) => !v)}
              >
                <Plus className="h-3.5 w-3.5" /> 新增配置
              </button>
            </div>

            {/* AI 总开关：关闭即回归传统邮件 */}
            <div className="mt-4 rounded-xl border border-gray-100 bg-gray-50/60 px-4 py-3">
              <label className="flex items-center gap-2 t-md font-medium text-gray-700">
                <input
                  type="checkbox"
                  className="h-4 w-4 accent-violet-600"
                  checked={aiEnabled}
                  disabled={aiEnabledMutation.isPending}
                  onChange={(e) => aiEnabledMutation.mutate(e.target.checked)}
                />
                启用 AI 功能
              </label>
              <p className="mt-1.5 t-sm leading-relaxed text-gray-400">
                关闭即回归传统邮件：整理 / 拟稿 / AI 写作 / 总管家 / 摘要生成等入口全部隐藏，
                已有分类与草稿保留，配置档案不丢失，随时可重新开启。
              </p>
            </div>

            <p className="mt-4 t-sm leading-relaxed text-gray-500">
              可保存多套端点配置（如 DeepSeek 快速、强模型写草稿、本地 Ollama），标「使用中」的配置供所有
              AI 功能默认使用；对话界面可临时切换。云端端点会收到邮件正文，本地端点则 0 外发。
            </p>

            <div className="mt-4 space-y-3">
              {profilesQuery.isLoading && <div className="t-md text-gray-400">加载中…</div>}
              {!profilesQuery.isLoading && profiles.length === 0 && !showNewProfile && (
                <div className="rounded-xl border border-dashed border-gray-200 px-4 py-6 text-center t-md text-gray-400">
                  还没有 AI 配置。点「新增配置」填入 Base URL + API Key + 模型名。
                </div>
              )}
              {profiles.map((p) => (
                <ProfileCard key={p.id} profile={p} isActive={p.id === activeProfileId} />
              ))}
              {showNewProfile && (
                <NewProfileCard onDone={() => setShowNewProfile(false)} />
              )}
              {profilesQuery.isError && (
                <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 t-sm text-red-600">
                  加载失败：{(profilesQuery.error as Error).message}
                </div>
              )}
            </div>
          </section>
        )}

        {/* ── AI 用量 ── */}
        {section === 'usage' && (
          <section className="rounded-2xl border border-gray-200 bg-white p-6 shadow-sm">
            <h2 className="t-lg font-semibold">AI 用量</h2>
            {!aiEnabled && (
              <p className="mt-1 t-sm text-gray-400">AI 已停用，以下为历史用量。</p>
            )}
            {usageQuery.data ? (
              <>
                <div className="mt-3 grid grid-cols-3 gap-3 text-center">
                  <div className="rounded-xl bg-gray-50 px-3 py-3">
                    <div className="t-lg font-semibold text-gray-800">{usageQuery.data.calls}</div>
                    <div className="t-xs text-gray-400">总调用</div>
                  </div>
                  <div className="rounded-xl bg-gray-50 px-3 py-3">
                    <div className="t-lg font-semibold text-gray-800">
                      {fmtTokens(usageQuery.data.prompt_tokens + usageQuery.data.completion_tokens)}
                    </div>
                    <div className="t-xs text-gray-400">总 Tokens</div>
                  </div>
                  <div className="rounded-xl bg-gray-50 px-3 py-3">
                    <div className="t-lg font-semibold text-gray-800">{usageQuery.data.failures}</div>
                    <div className="t-xs text-gray-400">失败</div>
                  </div>
                </div>
                {usageQuery.data.by_task.length > 0 && (
                  <div className="mt-3 space-y-1.5">
                    {usageQuery.data.by_task.map((t) => (
                      <div key={t.task_type} className="flex items-center gap-2 t-sm">
                        <span className="w-16 whitespace-nowrap text-gray-500">
                          {TASK_LABELS[t.task_type] ?? t.task_type}
                        </span>
                        <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-gray-100">
                          <div
                            className="h-full rounded-full bg-violet-400"
                            style={{
                              width: `${Math.max(4, (t.tokens / Math.max(...usageQuery.data.by_task.map((x) => x.tokens))) * 100)}%`,
                            }}
                          />
                        </div>
                        <span className="w-36 whitespace-nowrap text-right text-gray-400">
                          {t.calls} 次 · {fmtTokens(t.tokens)} Tokens
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </>
            ) : (
              <p className="mt-2 t-sm text-gray-400">加载用量中…</p>
            )}
          </section>
        )}

        {/* ── 关于 ── */}
        {section === 'about' && (
          <section className="rounded-2xl border border-gray-200 bg-white p-6 shadow-sm">
            <h2 className="t-lg font-semibold">关于</h2>
            <div className="mt-4 rounded-xl border border-gray-100 bg-gray-50/60 px-4 py-3">
              <div className="flex flex-wrap items-center gap-3">
                <label className="flex items-center gap-2 t-md text-gray-600">
                  <input
                    type="checkbox"
                    className="h-4 w-4 accent-indigo-600"
                    checked={!!data?.update_check_enabled}
                    onChange={(e) => updateToggleMutation.mutate(e.target.checked)}
                  />
                  自动检查更新
                </label>
                <span className="t-sm text-gray-400">
                  每 24 小时向 GitHub 做一次匿名版本对比，不发送本机数据
                </span>
                <span className="flex-1" />
                <span className="t-sm text-gray-500">当前 v{updateState?.current_version ?? '…'}</span>
                <button
                  className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 t-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50"
                  onClick={() => checkUpdateMutation.mutate()}
                  disabled={checkUpdateMutation.isPending}
                >
                  {checkUpdateMutation.isPending ? '检查中…' : '检查更新'}
                </button>
              </div>
              {updateState?.is_newer ? (
                <div className="mt-2 flex items-center gap-2 t-sm text-amber-700">
                  发现新版本 <b>{updateState.latest_version}</b>
                  <a
                    className="text-indigo-600 underline underline-offset-2"
                    href={updateState.release_url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    前往下载
                  </a>
                  （数据与配置不受升级影响）
                </div>
              ) : checkUpdateMutation.data ? (
                <p className="mt-2 t-sm text-emerald-600">已是最新版本 v{updateState?.current_version}</p>
              ) : updateState?.checked_at ? (
                <p className="mt-2 t-sm text-gray-400">上次检查：{updateState.checked_at.slice(0, 10)}</p>
              ) : null}
              {updateToggleMutation.isPending && <span className="t-sm text-gray-400">保存中…</span>}
            </div>
          </section>
        )}

        {/* 粘性保存栏：通用设置有改动时浮出 */}
        {dirty && (
          <div className="fixed inset-x-0 bottom-0 z-30 border-t border-gray-200 bg-white/95 backdrop-blur">
            <div className="mx-auto flex max-w-4xl items-center gap-3 px-8 py-3">
              <span className="t-sm text-gray-600">通用设置有未保存更改</span>
              <span className="flex-1" />
              {saveMutation.isError && (
                <span className="t-sm text-red-600">保存失败：{(saveMutation.error as Error).message}</span>
              )}
              <button
                className="rounded-lg border border-gray-300 px-3 py-1.5 t-sm text-gray-600 hover:bg-gray-50 disabled:opacity-50"
                onClick={discardChanges}
                disabled={saveMutation.isPending}
              >
                放弃
              </button>
              <button
                className="rounded-lg bg-indigo-600 px-4 py-1.5 t-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
                onClick={handleSave}
                disabled={saveMutation.isPending}
              >
                {saveMutation.isPending ? '保存中…' : '保存更改'}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

/** 每账号「文风提示词」编辑器：替代原语气学习，内容完全透明、用户手写。 */
function StylePromptEditor({ account, onClose }: { account: Account; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [text, setText] = useState(account.style_prompt ?? '')
  const saveMutation = useMutation({
    // 空串=清除；非空=保存
    mutationFn: () => api.updateAccount(account.id, { style_prompt: text.trim() }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['accounts'] })
      onClose()
    },
  })
  return (
    <div className="mt-3 rounded-lg border border-violet-200 bg-violet-50/50 p-3">
      <p className="t-sm leading-relaxed text-gray-600">
        文风提示词：AI 为该账号起草回复时作为要求遵循，内容完全由你撰写、随时可改；
        留空保存即清除。设置后「AI 拟稿 / AI 整理生成的草稿」都会遵循。
      </p>
      <textarea
        className={`${inputClass} mt-2 resize-y`}
        rows={4}
        maxLength={2000}
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={'例：中文商务邮件，简洁直接；称呼用「您好」，结尾「此致 敬礼」；少用感叹号，不堆客套话。'}
      />
      <div className="mt-2 flex items-center gap-2">
        <button
          className="rounded-lg bg-violet-600 px-3 py-1.5 t-sm font-medium text-white hover:bg-violet-700 disabled:opacity-50"
          onClick={() => saveMutation.mutate()}
          disabled={saveMutation.isPending}
        >
          {saveMutation.isPending ? '保存中…' : '保存'}
        </button>
        <button
          className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 t-sm text-gray-600 hover:bg-gray-50"
          onClick={onClose}
        >
          收起
        </button>
        <span className="t-xs text-gray-400">{text.length}/2000</span>
        {saveMutation.isError && (
          <span className="t-sm text-red-600">保存失败：{(saveMutation.error as Error).message}</span>
        )}
      </div>
    </div>
  )
}

function TestResult({ result }: { result: AITestResult }) {
  if (result.ok) {
    return (
      <div className="mt-4 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 t-md text-emerald-700">
        连接成功 · 模型 <b>{result.model}</b> · 延迟 {result.latency_ms} ms
        {result.reply && <> · 回复「{result.reply}」</>}
      </div>
    )
  }
  return (
    <div className="mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 t-md text-red-700">
      <p className="font-medium">连接失败</p>
      <p className="mt-1 break-all t-sm">{result.error}</p>
    </div>
  )
}

/** 模型列表自动拉取：Base URL 有效即防抖拉取；已存档案回退其密钥，新配置用输入框现值直连。 */
function useModelFetcher(baseUrl: string, apiKey: string, profileId?: string) {
  const [models, setModels] = useState<string[] | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  useEffect(() => {
    const url = baseUrl.trim()
    if (!/^https?:\/\//i.test(url)) {
      setModels(null)
      setError('')
      setLoading(false)
      return
    }
    let cancelled = false
    setLoading(true)
    const timer = window.setTimeout(async () => {
      try {
        const r = await api.fetchAIModels({
          ...(profileId ? { profile_id: profileId } : {}),
          base_url: url,
          ...(apiKey ? { api_key: apiKey } : {}),
        })
        if (cancelled) return
        setModels(r.ok ? r.models : [])
        setError(r.ok ? '' : r.error || '获取模型列表失败')
      } catch (err) {
        if (!cancelled) {
          setModels([])
          setError((err as Error).message)
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }, 700)
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [baseUrl, apiKey, profileId])
  return { models, error, loading }
}

/** 档案卡片的公共字段（编辑卡与新建卡共用一套渲染）。 */
function ProfileFields(props: {
  name: string
  baseUrl: string
  model: string
  apiKey: string
  models: string[] | null
  modelsError: string
  modelsLoading: boolean
  onName: (v: string) => void
  onBaseUrl: (v: string) => void
  onModel: (v: string) => void
  onApiKey: (v: string) => void
}) {
  // API Key 默认明文（本地应用，输入时可直接核对），可一键隐藏
  const [keyVisible, setKeyVisible] = useState(true)
  return (
    <>
      <div className="grid grid-cols-[1fr_2fr] gap-3">
        <label className="block">
          <span className="mb-1 block t-sm text-gray-500">名称</span>
          <input
            className={inputClass}
            value={props.name}
            onChange={(e) => props.onName(e.target.value)}
            placeholder="如 DeepSeek 快速"
          />
        </label>
        <label className="block">
          <span className="mb-1 block t-sm text-gray-500">Base URL</span>
          <input
            className={inputClass}
            value={props.baseUrl}
            onChange={(e) => props.onBaseUrl(e.target.value)}
            placeholder="https://api.deepseek.com/v1 或 http://localhost:11434/v1"
          />
        </label>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-3">
        <label className="block">
          <span className="mb-1 block t-sm text-gray-500">模型名</span>
          <input
            className={inputClass}
            value={props.model}
            onChange={(e) => props.onModel(e.target.value)}
            placeholder="deepseek-chat / gpt-4o-mini / qwen3:8b"
          />
        </label>
        <label className="block">
          <span className="mb-1 block t-sm text-gray-500">API Key</span>
          <div className="relative">
            <input
              className={`${inputClass} pr-9`}
              type={keyVisible ? 'text' : 'password'}
              value={props.apiKey}
              onChange={(e) => props.onApiKey(e.target.value)}
              placeholder="sk-…（本地模型可留空）"
              autoComplete="off"
              spellCheck={false}
            />
            <button
              type="button"
              tabIndex={-1}
              className="absolute right-2 top-1/2 -translate-y-1/2 p-0.5 text-gray-400 hover:text-gray-600"
              onClick={() => setKeyVisible((v) => !v)}
              title={keyVisible ? '隐藏 API Key' : '显示 API Key'}
            >
              {keyVisible ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </button>
          </div>
        </label>
      </div>
      {props.modelsLoading && (
        <p className="mt-2 t-xs text-gray-400">正在获取模型列表…</p>
      )}
      {props.models !== null && props.models.length > 0 && (
        <div className="mt-2 flex max-h-28 flex-wrap gap-1 overflow-y-auto rounded-lg bg-gray-50 p-2">
          {props.models.map((m) => (
            <button
              key={m}
              className="rounded-full border border-gray-200 bg-white px-2 py-0.5 t-xs text-gray-600 hover:border-violet-300 hover:text-violet-700"
              onClick={() => props.onModel(m)}
            >
              {m}
            </button>
          ))}
        </div>
      )}
      {props.modelsError && (
        <p className="mt-2 break-all t-xs text-red-500">{props.modelsError}</p>
      )}
    </>
  )
}

function ProfileCard({ profile, isActive }: { profile: AIProfile; isActive: boolean }) {
  const queryClient = useQueryClient()
  const [name, setName] = useState(profile.name)
  const [baseUrl, setBaseUrl] = useState(profile.base_url)
  const [model, setModel] = useState(profile.model)
  // 密钥明文回显（后端返回 api_key）：所见即所存，清空保存即清除
  const [apiKey, setApiKey] = useState(profile.api_key)
  // Base URL/API Key 变化后自动拉取模型列表
  const { models, error: modelsError, loading: modelsLoading } =
    useModelFetcher(baseUrl, apiKey, profile.id)

  const invalidate = () => void queryClient.invalidateQueries({ queryKey: ['ai-profiles'] })

  const saveMutation = useMutation({
    mutationFn: () =>
      api.updateAIProfile(profile.id, {
        name,
        base_url: baseUrl,
        model,
        api_key: apiKey, // 全量保存：与输入框一致（清空=清除）
      }),
    onSuccess: ({ profile: saved }) => {
      // 用落库返回值回填输入框：页面显示与本地存储强制一致（后端已 trim）
      setName(saved.name)
      setBaseUrl(saved.base_url)
      setModel(saved.model)
      setApiKey(saved.api_key)
      invalidate()
    },
  })
  const activateMutation = useMutation({
    mutationFn: () => api.activateAIProfile(profile.id),
    onSuccess: invalidate,
  })
  const deleteMutation = useMutation({
    mutationFn: () => api.deleteAIProfile(profile.id),
    onSuccess: invalidate,
  })
  const testMutation = useMutation({ mutationFn: api.testAI })

  return (
    <div
      className={`rounded-xl border p-4 ${
        isActive ? 'border-violet-300 bg-violet-50/40' : 'border-gray-200 bg-gray-50/40'
      }`}
    >
      <div className="mb-3 flex items-center gap-2">
        {isActive ? (
          <span className="inline-flex items-center gap-1 rounded-full bg-violet-600 px-2 py-0.5 t-xs font-medium text-white">
            <BadgeCheck className="h-3 w-3" /> 使用中
          </span>
        ) : (
          <button
            className="rounded-full border border-violet-200 bg-white px-2.5 py-0.5 t-xs text-violet-600 hover:bg-violet-50 disabled:opacity-40"
            onClick={() => activateMutation.mutate()}
            disabled={activateMutation.isPending}
          >
            设为使用中
          </button>
        )}
        <div className="flex-1" />
        <button
          className="rounded-lg border border-gray-200 p-1.5 text-gray-400 hover:bg-white hover:text-red-500 disabled:opacity-40"
          title="删除此配置"
          onClick={() => {
            if (confirm(`删除 AI 配置「${profile.name}」？已存密钥一并清除。`)) {
              deleteMutation.mutate()
            }
          }}
          disabled={deleteMutation.isPending}
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      </div>

      <ProfileFields
        name={name}
        baseUrl={baseUrl}
        model={model}
        apiKey={apiKey}
        models={models}
        modelsError={modelsError}
        modelsLoading={modelsLoading}
        onName={setName}
        onBaseUrl={setBaseUrl}
        onModel={setModel}
        onApiKey={setApiKey}
      />

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <button
          className="rounded-lg bg-violet-600 px-4 py-1.5 t-sm font-medium text-white hover:bg-violet-700 disabled:opacity-50"
          onClick={() => saveMutation.mutate()}
          disabled={saveMutation.isPending}
        >
          {saveMutation.isPending ? '保存中…' : '保存'}
        </button>
        <button
          className="rounded-lg border border-gray-300 bg-white px-4 py-1.5 t-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
          onClick={() =>
            testMutation.mutate({
              base_url: baseUrl,
              model,
              api_key: apiKey, // 全量直测：清空=按空密钥测，不回退已存密钥
            })
          }
          disabled={testMutation.isPending}
        >
          {testMutation.isPending ? (
            <span className="inline-flex items-center gap-2">
              <Loader2 className="h-3.5 w-3.5 animate-spin" /> 测试中…
            </span>
          ) : (
            '测试连接'
          )}
        </button>
        {saveMutation.isSuccess && !saveMutation.isPending && (
          <span className="t-sm text-emerald-600">已保存</span>
        )}
        {(saveMutation.isError || deleteMutation.isError || activateMutation.isError) && (
          <span className="t-sm text-red-600">
            操作失败：
            {((saveMutation.error ?? deleteMutation.error ?? activateMutation.error) as Error).message}
          </span>
        )}
      </div>

      {testMutation.data && <TestResult result={testMutation.data} />}
    </div>
  )
}

function NewProfileCard({ onDone }: { onDone: () => void }) {
  const queryClient = useQueryClient()
  const [name, setName] = useState('')
  const [baseUrl, setBaseUrl] = useState('')
  const [model, setModel] = useState('')
  const [apiKey, setApiKey] = useState('')
  // 未保存的新配置：用输入框现值直连拉取模型（无需先创建）
  const { models, error: modelsError, loading: modelsLoading } = useModelFetcher(baseUrl, apiKey)

  const createMutation = useMutation({
    mutationFn: () =>
      api.createAIProfile({
        name: name.trim() || '未命名',
        base_url: baseUrl,
        model,
        ...(apiKey ? { api_key: apiKey } : {}),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['ai-profiles'] })
      onDone()
    },
  })

  const canCreate = name.trim() !== '' && baseUrl.trim() !== '' && model.trim() !== ''

  return (
    <div className="rounded-xl border border-dashed border-violet-300 bg-violet-50/30 p-4">
      <div className="mb-3 t-sm font-medium text-violet-700">新增 AI 配置</div>
      <ProfileFields
        name={name}
        baseUrl={baseUrl}
        model={model}
        apiKey={apiKey}
        models={models}
        modelsError={modelsError}
        modelsLoading={modelsLoading}
        onName={setName}
        onBaseUrl={setBaseUrl}
        onModel={setModel}
        onApiKey={setApiKey}
      />
      <div className="mt-4 flex items-center gap-3">
        <button
          className="rounded-lg bg-violet-600 px-4 py-1.5 t-sm font-medium text-white hover:bg-violet-700 disabled:opacity-50"
          onClick={() => createMutation.mutate()}
          disabled={!canCreate || createMutation.isPending}
        >
          {createMutation.isPending ? '创建中…' : '创建'}
        </button>
        <button
          className="rounded-lg border border-gray-300 bg-white px-4 py-1.5 t-sm font-medium text-gray-600 hover:bg-gray-50"
          onClick={onDone}
        >
          取消
        </button>
        {!canCreate && <span className="t-xs text-gray-400">名称、Base URL、模型名必填</span>}
        {createMutation.isError && (
          <span className="t-sm text-red-600">创建失败：{(createMutation.error as Error).message}</span>
        )}
      </div>
    </div>
  )
}
