import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { BadgeCheck, Ban, BarChart3, BookUser, Bot, Check, ChevronLeft, Copy, Eye, EyeOff, Info, Loader2, Mail, MailPlus, Pencil, PenLine, Plug, Plus, RefreshCw, SlidersHorizontal, Trash2, UserCheck, UserPlus, UsersRound } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import AddAccountModal from '../components/AddAccountModal'
import ContextMenu, { type ContextMenuItem } from '../components/ContextMenu'
import ExtApiSection from '../components/ExtApiSection'
import { OauthConfigCard, ReauthorizeButton } from '../components/OauthSettings'
import { notifyPermission, type NotifyPermission } from '../components/NotificationBell'
import { useCompose } from '../components/compose/ComposeContext'
import { SignatureEditor, TemplateManager } from '../components/compose/InsertDialogs'
import { backendLocalDate } from '../utils/format'
import { ACCOUNT_COLOR_PALETTE } from '../utils/accountColor'
import type { Account, AITestResult, AIProfile, ContactGroup, ContactItem, NotifyTypeKey, SenderListEntry, Settings } from '../types'

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
  { key: 'compose', label: '写信', icon: PenLine },
  { key: 'contacts', label: '通讯录', icon: BookUser },
  { key: 'ai', label: 'AI 配置', icon: Bot },
  { key: 'usage', label: 'AI 用量', icon: BarChart3 },
  { key: 'api', label: 'API', icon: Plug },
  { key: 'about', label: '关于', icon: Info },
] as const
type SectionKey = (typeof SECTIONS)[number]['key']

// 桌面通知类型细分（NotifyTypeKey 顺序即 UI 呈现顺序）
const NOTIFY_TYPE_LABELS: { key: NotifyTypeKey; label: string }[] = [
  { key: 'new_mail', label: '新邮件' },
  { key: 'ai_draft', label: 'AI 草稿' },
  { key: 'digest', label: '每日摘要' },
  { key: 'account_error', label: '账号异常' },
]

export default function SettingsPage() {
  const queryClient = useQueryClient()
  const { data, isLoading, error } = useQuery({ queryKey: ['settings'], queryFn: api.getSettings })

  // 代理状态独立 3s 轮询：系统代理开关一变，状态行实时跟上（与主设置查询隔离，不重置表单）
  const { data: proxyStatus } = useQuery({
    queryKey: ['proxy-status'],
    queryFn: api.getSettings,
    refetchInterval: 3000,
  })

  const [section, setSection] = useState<SectionKey>(() => {
    const saved = localStorage.getItem('nmail_settings_section')
    return SECTIONS.some((s) => s.key === saved) ? (saved as SectionKey) : 'general'
  })
  useEffect(() => {
    localStorage.setItem('nmail_settings_section', section)
  }, [section])

  // 初始值 = 新用户默认（backend api/settings.py DEFAULT_SETTINGS）：请求返回前不闪旧档
  const [pollMinutes, setPollMinutes] = useState(1)
  const [digestTime, setDigestTime] = useState('07:00')
  const [uiFont, setUiFont] = useState<'compact' | 'standard' | 'large'>('large')
  const [bodyFont, setBodyFont] = useState<'small' | 'standard' | 'large'>('standard')
  const [allowRemoteImages, setAllowRemoteImages] = useState(false)
  const [desktopNotif, setDesktopNotif] = useState(true)
  const [notifyTypes, setNotifyTypes] = useState<Record<NotifyTypeKey, boolean>>({
    new_mail: true, ai_draft: true, digest: true, account_error: true,
  })
  const [autoSig, setAutoSig] = useState(false)
  const [notifPerm, setNotifPerm] = useState<NotifyPermission>(() => notifyPermission())

  const [showAddAccount, setShowAddAccount] = useState(false)
  const [accountMessage, setAccountMessage] = useState<string | null>(null)
  const [showNewProfile, setShowNewProfile] = useState(false)
  const [styleOpenId, setStyleOpenId] = useState<number | null>(null)
  const [aiGrantsOpenId, setAiGrantsOpenId] = useState<number | null>(null)
  const [colorPickerOpenId, setColorPickerOpenId] = useState<number | null>(null)
  const colorPickerRef = useRef<HTMLDivElement>(null)

  // 取色 popover 点外/Esc 关闭（浮层基本 UX）；监听 mousedown 以便先于其他点击生效
  useEffect(() => {
    if (colorPickerOpenId == null) return
    const onDocMouseDown = (e: MouseEvent) => {
      if (colorPickerRef.current && !colorPickerRef.current.contains(e.target as Node)) {
        setColorPickerOpenId(null)
      }
    }
    const onDocKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setColorPickerOpenId(null)
    }
    document.addEventListener('mousedown', onDocMouseDown)
    document.addEventListener('keydown', onDocKeyDown)
    return () => {
      document.removeEventListener('mousedown', onDocMouseDown)
      document.removeEventListener('keydown', onDocKeyDown)
    }
  }, [colorPickerOpenId])
  const [configOpenId, setConfigOpenId] = useState<number | null>(null)
  const [settingsError, setSettingsError] = useState('')

  useEffect(() => {
    if (!data) return
    setPollMinutes(data.poll_interval_minutes)
    setDigestTime(data.digest_time)
    setUiFont(data.ui_font)
    setBodyFont(data.body_font)
    setAllowRemoteImages(data.allow_remote_images)
    setDesktopNotif(data.desktop_notifications_enabled !== false)
    setNotifyTypes((prev) => ({
      ...prev,
      ...Object.fromEntries(
        NOTIFY_TYPE_LABELS.map(({ key }) => [key, data.notify_types?.[key] !== false]),
      ),
    }) as Record<NotifyTypeKey, boolean>)
    setAutoSig(!!data.auto_insert_signature) // 旧后端无此字段 → undefined → 关
  }, [data])

  // 版本守护：响应缺新字段说明后端进程是旧版本（旧 Pydantic 会静默忽略未知字段）
  const guardVersion = (saved: Settings) => {
    queryClient.setQueryData(['settings'], saved)
    if (saved.ui_font === undefined || saved.poll_interval_minutes === undefined
        || saved.effective_proxy === undefined) {
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

  // 选择即保存的即时项（字号/远程图片/通知/自动签名）共用一个 mutation
  const instantMutation = useMutation({
    mutationFn: api.updateSettings,
    onSuccess: guardVersion,
    onError: (err: Error) => setSettingsError(`保存失败：${err.message}`),
  })
  const changeUiFont = (v: 'compact' | 'standard' | 'large') => {
    setUiFont(v)
    instantMutation.mutate({ ui_font: v })
  }
  const changeBodyFont = (v: 'small' | 'standard' | 'large') => {
    setBodyFont(v)
    instantMutation.mutate({ body_font: v })
  }
  const changeRemoteImages = (v: boolean) => {
    setAllowRemoteImages(v)
    instantMutation.mutate({ allow_remote_images: v })
  }
  const changeDesktopNotif = (v: boolean) => {
    setDesktopNotif(v)
    instantMutation.mutate({ desktop_notifications_enabled: v })
  }
  const changeNotifyType = (key: NotifyTypeKey, v: boolean) => {
    const next = { ...notifyTypes, [key]: v }
    setNotifyTypes(next)
    instantMutation.mutate({ notify_types: next })
  }
  const changeAutoSig = (v: boolean) => {
    setAutoSig(v)
    instantMutation.mutate({ auto_insert_signature: v })
  }
  // 浏览器通知权限：设置页里申请/重查（铃铛旁的快捷按钮同样可用）
  const requestNotifPerm = () => {
    if (!('Notification' in window)) return
    void Notification.requestPermission().then((p) => setNotifPerm(p as NotifyPermission))
  }

  // 本机路径（关于页展示软件本地性；运行进程实时解析，不硬编码）
  const pathsQuery = useQuery({ queryKey: ['system-paths'], queryFn: api.getSystemPaths })

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

  // 标识色即点即存：色板限定 12 色（见 utils/accountColor.ts），改色联动邮件列表/读信/摘要各处
  const colorMutation = useMutation({
    mutationFn: ({ id, color }: { id: number; color: string }) => api.updateAccount(id, { color }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['accounts'] }),
    onError: (err: Error) => {
      setAccountMessage(`颜色保存失败：${err.message}`)
      setTimeout(() => setAccountMessage(null), 6000)
    },
  })

  const usageQuery = useQuery({ queryKey: ['ai-usage'], queryFn: api.aiUsage })

  if (isLoading) {
    return <div className="p-8 t-md text-gray-400">加载设置中…</div>
  }

  return (
    <div className="mx-auto flex max-w-6xl gap-8 p-8">
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
                    {instantMutation.isPending ? '保存中…' : '选择即生效'}
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

            {/* 通知（桌面通知走浏览器 Notification API；应用内铃铛与角标不受开关影响） */}
            <div className="mt-4 rounded-xl border border-gray-100 bg-gray-50/60 px-4 py-3">
              <label className="flex items-center gap-2 t-md font-medium text-gray-700">
                <input
                  type="checkbox"
                  className="h-4 w-4 accent-indigo-600"
                  checked={desktopNotif}
                  disabled={instantMutation.isPending}
                  onChange={(e) => changeDesktopNotif(e.target.checked)}
                />
                桌面通知
              </label>
              <p className="mt-1.5 t-sm leading-relaxed text-gray-400">
                新通知到达时弹系统通知（选择即生效）；应用内铃铛与未读角标始终显示，不受影响。
              </p>
              <div className="mt-2 flex flex-wrap gap-x-5 gap-y-1.5">
                {NOTIFY_TYPE_LABELS.map(({ key, label }) => (
                  <label
                    key={key}
                    className={`flex items-center gap-1.5 t-sm ${desktopNotif ? 'text-gray-600' : 'text-gray-300'}`}
                    title={desktopNotif ? undefined : '先开启桌面通知'}
                  >
                    <input
                      type="checkbox"
                      className="h-3.5 w-3.5 accent-indigo-600"
                      checked={notifyTypes[key]}
                      disabled={!desktopNotif || instantMutation.isPending}
                      onChange={(e) => changeNotifyType(key, e.target.checked)}
                    />
                    {label}
                  </label>
                ))}
              </div>
              <p className="mt-2 t-xs leading-relaxed text-gray-400">
                {notifPerm === 'granted' && (
                  <span className="text-emerald-600">✓ 浏览器通知权限已授予</span>
                )}
                {notifPerm === 'default' && (
                  <>
                    浏览器通知权限还未申请
                    <button
                      className="ml-1.5 rounded border border-indigo-200 bg-white px-1.5 py-0.5 text-indigo-600 hover:bg-indigo-50"
                      onClick={requestNotifPerm}
                    >
                      申请权限
                    </button>
                  </>
                )}
                {notifPerm === 'denied' && (
                  <span className="text-amber-600">
                    浏览器已拒绝通知权限——请点浏览器地址栏左侧的站点设置，把「通知」改为允许后刷新页面
                  </span>
                )}
                {notifPerm === 'unsupported' && <span>当前环境不支持桌面通知（应用内铃铛不受影响）</span>}
              </p>
            </div>

            {/* 发件人白/黑名单（零成本集合，先于 AI 生效） */}
            <SenderListsPanel />

            <div className="mt-4">
              <span className="t-md text-gray-600">网络代理</span>
              <span className="mt-1 block t-sm leading-relaxed text-gray-400">
                自动跟随系统代理，无需设置（和浏览器一致）——
                {proxyStatus?.effective_proxy
                  ? <span className="font-medium text-gray-600">当前经 {proxyStatus.effective_proxy} 连接</span>
                  : <span className="font-medium text-gray-600">当前直连</span>}
                （系统代理开关一变，这里几秒内自动刷新）；所有邮箱统一生效，
                本机服务（如 Proton Bridge）不受影响。
              </span>
            </div>
          </section>
        )}

        {/* ── 写信：自动签名 + 签名/模板管理 ── */}
        {section === 'compose' && (
          <ComposeSection accounts={accounts} autoSig={autoSig} onAutoSig={changeAutoSig} />
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
                      <div className="relative shrink-0" ref={colorPickerOpenId === account.id ? colorPickerRef : undefined}>
                        <button
                          className="block h-4 w-4 cursor-pointer rounded-full ring-offset-2 transition-shadow hover:ring-2 hover:ring-gray-300"
                          style={{ backgroundColor: account.color }}
                          title="自定义标识色"
                          aria-label={`自定义 ${account.email} 的标识色`}
                          onClick={() => setColorPickerOpenId(colorPickerOpenId === account.id ? null : account.id)}
                        />
                        {colorPickerOpenId === account.id && (
                          <div className="absolute -top-1 left-6 z-20 grid w-[172px] grid-cols-4 gap-1.5 rounded-xl border border-gray-200 bg-white p-2 shadow-lg">
                            {ACCOUNT_COLOR_PALETTE.map((c) => {
                              const usedBy = accounts.find((x) => x.id !== account.id && x.color === c)
                              return (
                                <button
                                  key={c}
                                  className={`relative flex h-8 w-8 cursor-pointer items-center justify-center rounded-full transition-transform hover:scale-110 ${
                                    account.color === c ? 'ring-2 ring-gray-900 ring-offset-1' : ''
                                  } ${usedBy ? 'opacity-40' : ''}`}
                                  style={{ backgroundColor: c }}
                                  title={usedBy ? `已被 ${usedBy.email} 使用，仍可选用` : c}
                                  aria-label={`标识色 ${c}`}
                                  onClick={() => {
                                    if (c !== account.color) colorMutation.mutate({ id: account.id, color: c })
                                    setColorPickerOpenId(null)
                                  }}
                                >
                                  {account.color === c && <Check className="h-3.5 w-3.5 text-white drop-shadow" />}
                                </button>
                              )
                            })}
                          </div>
                        )}
                      </div>
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
                              <span className="ml-1.5 rounded-full bg-emerald-50 px-1.5 py-0.5 t-xs text-emerald-600">OAuth2</span>
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
                      <button
                        className="shrink-0 rounded-lg border px-2 py-1.5 t-sm text-gray-600 hover:bg-white hover:text-indigo-600"
                        title="该账号的 AI 细粒度授权（总管家可做什么）与 AI 专属邮箱"
                        onClick={() => setAiGrantsOpenId(aiGrantsOpenId === account.id ? null : account.id)}
                      >
                        AI 权限
                      </button>
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
                      {account.auth_type !== 'oauth2' && (
                        <button
                          className="shrink-0 rounded-lg border border-gray-200 px-2 py-1.5 t-sm text-gray-600 hover:bg-white hover:text-indigo-600"
                          title="修改 IMAP/SMTP 服务器与端口、更新授权码"
                          onClick={() => setConfigOpenId(configOpenId === account.id ? null : account.id)}
                        >
                          配置
                        </button>
                      )}
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
                    {configOpenId === account.id && (
                      <AccountConfigEditor account={account} onClose={() => setConfigOpenId(null)} />
                    )}
                    {aiGrantsOpenId === account.id && (
                      <AccountAiPanel account={account} onClose={() => setAiGrantsOpenId(null)} />
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
                  然后在账号卡片点「配置」粘贴新授权码保存即可（服务器地址有误也可在此修改）。
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
            <AgentActionsList />
            <AgentMemoryList />
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

        {/* ── 通讯录（v0.4 P4）── */}
        {section === 'contacts' && <ContactsSection />}

        {/* ── 对外 API（v0.4 P7，REDESIGN_PLAN §7）── */}
        {section === 'api' && <ExtApiSection />}

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
                <p className="mt-2 t-sm text-gray-400">上次检查：{backendLocalDate(updateState.checked_at)}</p>
              ) : null}
              {updateToggleMutation.isPending && <span className="t-sm text-gray-400">保存中…</span>}
            </div>

            {/* 本机路径：体现软件本地性——数据与程序都在这台电脑上，路径为运行进程实时解析的真实值 */}
            <div className="mt-3 rounded-xl border border-gray-100 bg-gray-50/60 px-4 py-3">
              <div className="t-md font-medium text-gray-700">本机数据</div>
              <p className="mt-1 t-sm leading-relaxed text-gray-400">
                Nmail 是纯本地应用：邮件、附件、密钥与设置都只存在这台电脑上，不依赖任何云端账号。
              </p>
              <PathRow
                label="数据目录"
                path={pathsQuery.data?.data_dir}
                hint="邮件、附件、AI 密钥与设置全在这里；备份此目录即备份全部数据"
              />
              <PathRow
                label="安装目录"
                path={pathsQuery.data?.install_dir}
                hint="程序代码所在目录（源码运行=仓库根；wheel 安装=site-packages；打包版=可执行文件目录）"
              />
              {pathsQuery.data?.data_dir_overridden && (
                <p className="mt-1 t-xs text-amber-600">
                  数据目录已通过 NMAIL_DATA_DIR 环境变量重定向（当前显示即生效路径）
                </p>
              )}
            </div>
          </section>
        )}

        {/* 粘性保存栏：通用设置有改动时浮出 */}
        {dirty && (
          <div className="fixed inset-x-0 bottom-0 z-30 border-t border-gray-200 bg-white/95 backdrop-blur">
            <div className="mx-auto flex max-w-6xl items-center gap-3 px-8 py-3">
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

/** 每账号「服务器配置」编辑器（仅授权码账号）：改 IMAP/SMTP 地址端口、更新授权码；
 *  保存即后端试连，失败原样回显不落库；服务器变更会清空本地邮件重同步。 */
function AccountConfigEditor({ account, onClose }: { account: Account; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [imapServer, setImapServer] = useState(account.imap_server)
  const [imapPort, setImapPort] = useState(String(account.imap_port))
  const [smtpServer, setSmtpServer] = useState(account.smtp_server)
  const [smtpPort, setSmtpPort] = useState(String(account.smtp_port))
  const [password, setPassword] = useState(account.password ?? '')
  const [pwdVisible, setPwdVisible] = useState(false)
  const saveMutation = useMutation({
    mutationFn: () =>
      api.updateAccount(account.id, {
        imap_server: imapServer.trim(),
        imap_port: Number(imapPort) || undefined,
        smtp_server: smtpServer.trim(),
        smtp_port: Number(smtpPort) || undefined,
        ...(password.trim() ? { password: password.trim() } : {}),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['accounts'] })
      onClose()
    },
  })
  const field = 'min-w-0 flex-1 rounded-lg border border-gray-300 bg-white px-2.5 py-1.5 t-sm outline-none focus:border-indigo-500'
  return (
    <div className="mt-3 rounded-lg border border-indigo-200 bg-indigo-50/40 p-3">
      <p className="t-sm leading-relaxed text-gray-600">
        修改服务器或授权码后保存，会先试连再生效；服务器有变更会清空该账号本地已下载邮件并重新同步
        （服务器邮件不受影响）。
      </p>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <label className="flex min-w-0 flex-[2] flex-col">
          <span className="mb-1 block t-xs text-gray-500">IMAP 服务器（收信）</span>
          <input className={field} value={imapServer} spellCheck={false}
            onChange={(e) => setImapServer(e.target.value)} placeholder="imap.example.com" />
        </label>
        <label className="flex w-24 shrink-0 flex-col">
          <span className="mb-1 block t-xs text-gray-500">端口</span>
          <input className={field} value={imapPort} inputMode="numeric"
            onChange={(e) => setImapPort(e.target.value)} placeholder="993" />
        </label>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <label className="flex min-w-0 flex-[2] flex-col">
          <span className="mb-1 block t-xs text-gray-500">SMTP 服务器（发信）</span>
          <input className={field} value={smtpServer} spellCheck={false}
            onChange={(e) => setSmtpServer(e.target.value)} placeholder="smtp.example.com" />
        </label>
        <label className="flex w-24 shrink-0 flex-col">
          <span className="mb-1 block t-xs text-gray-500">端口</span>
          <input className={field} value={smtpPort} inputMode="numeric"
            onChange={(e) => setSmtpPort(e.target.value)} placeholder="465" />
        </label>
      </div>
      <label className="mt-2 flex flex-col">
        <span className="mb-1 block t-xs text-gray-500">授权码（所见即所存；换新码直接改这里）</span>
        <div className="relative flex">
          <input className={`${field} pr-9`} type={pwdVisible ? 'text' : 'password'} value={password}
            autoComplete="new-password" spellCheck={false}
            onChange={(e) => setPassword(e.target.value)} placeholder="服务商邮箱授权码" />
          <button
            className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
            onClick={(e) => { e.preventDefault(); setPwdVisible(!pwdVisible) }}
            title={pwdVisible ? '隐藏' : '显示'}
          >
            {pwdVisible ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
          </button>
        </div>
      </label>
      <div className="mt-2 flex items-center gap-2">
        <button
          className="rounded-lg bg-indigo-600 px-3 py-1.5 t-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          onClick={() => saveMutation.mutate()}
          disabled={saveMutation.isPending || !imapServer.trim() || !password.trim()}
        >
          {saveMutation.isPending ? '试连并保存中…' : '保存'}
        </button>
        {!password.trim() && <span className="t-xs text-gray-400">授权码不能为空</span>}
        <button
          className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 t-sm text-gray-600 hover:bg-gray-50"
          onClick={onClose}
        >
          收起
        </button>
        {saveMutation.isError && (
          <span className="min-w-0 flex-1 truncate t-sm text-red-600" title={(saveMutation.error as Error).message}>
            保存失败：{(saveMutation.error as Error).message}
          </span>
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
  contextWindow: string
  models: string[] | null
  modelsError: string
  modelsLoading: boolean
  onName: (v: string) => void
  onBaseUrl: (v: string) => void
  onModel: (v: string) => void
  onApiKey: (v: string) => void
  onContextWindow: (v: string) => void
}) {
  // API Key 默认遮蔽（保存/测试用的 state 不受影响，所见即所存），小眼睛一键显隐
  const [keyVisible, setKeyVisible] = useState(false)
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
      <label className="mt-3 block">
        <span className="mb-1 block t-sm text-gray-500">上下文窗口（tokens，可选）</span>
        <input
          className={inputClass}
          type="number"
          min={8192}
          step={1}
          value={props.contextWindow}
          onChange={(e) => props.onContextWindow(e.target.value)}
          placeholder="默认 1000000"
          spellCheck={false}
        />
        <span className="mt-1 block t-xs text-gray-400">
          按模型实际上下文窗口填写（如 8192 / 32768 / 128000 / 1000000）。总管家会据此自动压缩长对话（AutoCompact）；本地小窗口模型建议必填，防止压缩触发过晚导致请求超限报错。
        </span>
      </label>
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
  // 上下文窗口（§17.8）：空串=默认 1M；保存时 0=恢复默认
  const [contextWindow, setContextWindow] = useState(
    profile.context_window ? String(profile.context_window) : '',
  )
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
        context_window: contextWindow.trim() ? Number(contextWindow) : 0,
      }),
    onSuccess: ({ profile: saved }) => {
      // 用落库返回值回填输入框：页面显示与本地存储强制一致（后端已 trim）
      setName(saved.name)
      setBaseUrl(saved.base_url)
      setModel(saved.model)
      setApiKey(saved.api_key)
      setContextWindow(saved.context_window ? String(saved.context_window) : '')
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
        contextWindow={contextWindow}
        models={models}
        modelsError={modelsError}
        modelsLoading={modelsLoading}
        onName={setName}
        onBaseUrl={setBaseUrl}
        onModel={setModel}
        onApiKey={setApiKey}
        onContextWindow={setContextWindow}
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
  const [contextWindow, setContextWindow] = useState('')
  // 未保存的新配置：用输入框现值直连拉取模型（无需先创建）
  const { models, error: modelsError, loading: modelsLoading } = useModelFetcher(baseUrl, apiKey)

  const createMutation = useMutation({
    mutationFn: () =>
      api.createAIProfile({
        name: name.trim() || '未命名',
        base_url: baseUrl,
        model,
        ...(apiKey ? { api_key: apiKey } : {}),
        ...(contextWindow.trim() ? { context_window: Number(contextWindow) } : {}),
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
        contextWindow={contextWindow}
        models={models}
        modelsError={modelsError}
        modelsLoading={modelsLoading}
        onName={setName}
        onBaseUrl={setBaseUrl}
        onModel={setModel}
        onApiKey={setApiKey}
        onContextWindow={setContextWindow}
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

// ── 通讯录（2026-09-12 改版，REDESIGN_PLAN §5.4）：左树（智能视图+联系组）+ 右列表/详情双态 ──

type ContactView =
  | { kind: 'all' }
  | { kind: 'auto' }
  | { kind: 'manual' }
  | { kind: 'ungrouped' }
  | { kind: 'group'; id: number; name: string }

const CONTACT_VIEWS: { kind: 'all' | 'auto' | 'manual' | 'ungrouped'; label: string }[] = [
  { kind: 'all', label: '所有联系人' },
  { kind: 'auto', label: '自动采集' },
  { kind: 'manual', label: '手动添加' },
  { kind: 'ungrouped', label: '未分组' },
]

const viewKeyOf = (v: ContactView) => (v.kind === 'group' ? `group-${v.id}` : v.kind)

const SourceBadges = ({ sources }: { sources: string[] }) => (
  <span className="inline-flex gap-1">
    {sources.includes('auto') && (
      <span className="whitespace-nowrap rounded bg-emerald-50 px-1.5 py-0.5 t-xs text-emerald-600">自动</span>
    )}
    {sources.includes('manual') && (
      <span className="whitespace-nowrap rounded bg-gray-100 px-1.5 py-0.5 t-xs text-gray-500">手动</span>
    )}
  </span>
)

/** 开关（自动采集等）：紧凑 iOS 式样 */
const MiniSwitch = ({ on, onClick, title }: { on: boolean; onClick: () => void; title?: string }) => (
  <button
    className={`relative h-4 w-7 shrink-0 rounded-full transition-colors ${on ? 'bg-emerald-500' : 'bg-gray-300'}`}
    onClick={onClick}
    title={title}
  >
    <span
      className={`absolute top-0.5 h-3 w-3 rounded-full bg-white shadow transition-all ${on ? 'left-3.5' : 'left-0.5'}`}
    />
  </button>
)

function ContactsSection() {
  const queryClient = useQueryClient()
  const { openNew } = useCompose()
  const [view, setView] = useState<ContactView>({ kind: 'all' })
  const [q, setQ] = useState('')
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [detailId, setDetailId] = useState<number | null>(null)
  const [adding, setAdding] = useState(false)
  const [form, setForm] = useState({ email: '', name: '', phone: '' })
  const [newGroupName, setNewGroupName] = useState<string | null>(null) // null=收起；串=输入中
  const [renaming, setRenaming] = useState<{ id: number; name: string } | null>(null)
  const [menu, setMenu] = useState<{ x: number; y: number; group: ContactGroup } | null>(null)
  const [message, setMessage] = useState('')

  const { data: settings } = useQuery({ queryKey: ['settings'], queryFn: api.getSettings })
  const autoCollect = settings?.contacts_auto_collect ?? false
  const listQuery = useQuery({
    queryKey: ['contacts', viewKeyOf(view), q],
    queryFn: () =>
      api.getContacts({
        q,
        source: view.kind === 'auto' || view.kind === 'manual' ? view.kind : undefined,
        ungrouped: view.kind === 'ungrouped' || undefined,
        group_id: view.kind === 'group' ? view.id : undefined,
      }),
  })
  const groupsQuery = useQuery({ queryKey: ['contact-groups'], queryFn: api.getContactGroups })
  const contacts = listQuery.data?.contacts ?? []
  const counts = listQuery.data?.counts
  const groups = groupsQuery.data?.groups ?? []

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['contacts'] })
    void queryClient.invalidateQueries({ queryKey: ['contact-groups'] })
  }
  const fail = (label: string) => (err: Error) => setMessage(`${label}：${err.message}`)

  const toggleCollect = useMutation({
    mutationFn: (v: boolean) => api.updateSettings({ contacts_auto_collect: v }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['settings'] }),
  })
  const addMutation = useMutation({
    mutationFn: () =>
      api.createContact({ email: form.email.trim(), name: form.name.trim(), phone: form.phone.trim() }),
    onSuccess: () => {
      setForm({ email: '', name: '', phone: '' })
      setAdding(false)
      setMessage('')
      invalidate()
    },
    onError: fail('新增失败'),
  })
  const deleteContacts = useMutation({
    mutationFn: async (ids: number[]) => {
      for (const id of ids) await api.deleteContact(id)
    },
    onSuccess: (_d, ids) => {
      setSelected(new Set())
      if (detailId != null && ids.includes(detailId)) setDetailId(null)
      setMessage('')
      invalidate()
    },
    onError: fail('删除失败'),
  })
  const createGroupMutation = useMutation({
    mutationFn: (name: string) => api.createContactGroup(name),
    onSuccess: () => {
      setNewGroupName(null)
      setMessage('')
      invalidate()
    },
    onError: fail('新建组失败'),
  })
  const renameGroupMutation = useMutation({
    mutationFn: ({ id, name }: { id: number; name: string }) => api.renameContactGroup(id, name),
    onSuccess: () => {
      setRenaming(null)
      setMessage('')
      invalidate()
    },
    onError: fail('重命名失败'),
  })
  const deleteGroupMutation = useMutation({
    mutationFn: (id: number) => api.deleteContactGroup(id),
    onSuccess: (_d, id) => {
      if (view.kind === 'group' && view.id === id) setView({ kind: 'all' })
      invalidate()
    },
    onError: fail('删除组失败'),
  })

  const toggleRow = (id: number) =>
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  const viewItemCls = (active: boolean) =>
    `flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 t-sm transition-colors ${
      active ? 'bg-indigo-50 font-medium text-indigo-700' : 'text-gray-600 hover:bg-gray-50'
    }`

  const groupMenuItems: ContextMenuItem[] = menu
    ? [
        { label: '重命名', icon: Pencil, onSelect: () => setRenaming({ id: menu.group.id, name: menu.group.name }) },
        {
          label: '删除组',
          icon: Trash2,
          danger: true,
          onSelect: () => deleteGroupMutation.mutate(menu.group.id),
        },
      ]
    : []

  return (
    <section className="rounded-2xl border border-gray-200 bg-white shadow-sm">
      <div className="flex items-start justify-between px-6 pt-6">
        <div>
          <h2 className="t-lg font-semibold">通讯录</h2>
          <p className="mt-1 t-sm text-gray-400">
            收发往来地址自动入册；点击联系人进详情，可写信、编辑、备注与分组。
          </p>
        </div>
      </div>

      <div className="mt-4 flex border-t border-gray-100">
        {/* 左树：智能视图 + 联系组 */}
        <div className="flex w-52 shrink-0 flex-col border-r border-gray-100 py-3 pl-4 pr-2">
          <div className="flex items-center gap-2 px-2.5">
            <MiniSwitch
              on={autoCollect}
              onClick={() => toggleCollect.mutate(!autoCollect)}
              title={autoCollect ? '自动采集已开：收发往来地址自动入册' : '自动采集已关：不再自动入册，已入册保留'}
            />
            <span className="t-xs text-gray-500">自动采集</span>
            {!autoCollect && <span className="t-xs text-amber-600">已关</span>}
          </div>

          <div className="mt-3 space-y-0.5">
            {CONTACT_VIEWS.map((v) => (
              <button key={v.kind} className={viewItemCls(view.kind === v.kind)} onClick={() => { setView({ kind: v.kind }); setDetailId(null); setSelected(new Set()) }}>
                <UsersRound className="h-3.5 w-3.5 shrink-0 text-gray-400" />
                <span className="min-w-0 flex-1 truncate text-left">{v.label}</span>
                <span className="t-xs text-gray-400">{counts?.[v.kind] ?? ''}</span>
              </button>
            ))}
          </div>

          <div className="mt-4 flex items-center justify-between px-2.5">
            <span className="t-xs font-medium uppercase tracking-wide text-gray-400">联系组</span>
          </div>
          <div className="mt-1 flex-1 space-y-0.5 overflow-y-auto">
            {groups.map((g) =>
              renaming?.id === g.id ? (
                <div key={g.id} className="flex items-center gap-1 px-1.5 py-0.5">
                  <input
                    className="min-w-0 flex-1 rounded border border-indigo-300 px-1.5 py-0.5 t-xs outline-none focus:border-indigo-500"
                    value={renaming.name}
                    onChange={(e) => setRenaming({ id: g.id, name: e.target.value })}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && renaming.name.trim())
                        renameGroupMutation.mutate({ id: g.id, name: renaming.name.trim() })
                      if (e.key === 'Escape') setRenaming(null)
                    }}
                    autoFocus
                  />
                </div>
              ) : (
                <button
                  key={g.id}
                  className={viewItemCls(view.kind === 'group' && view.id === g.id)}
                  onClick={() => { setView({ kind: 'group', id: g.id, name: g.name }); setDetailId(null); setSelected(new Set()) }}
                  onContextMenu={(e) => {
                    e.preventDefault()
                    setMenu({ x: e.clientX, y: e.clientY, group: g })
                  }}
                  title="右键重命名/删除"
                >
                  <BookUser className="h-3.5 w-3.5 shrink-0 text-gray-400" />
                  <span className="min-w-0 flex-1 truncate text-left">{g.name}</span>
                  <span className="t-xs text-gray-400">{g.member_count}</span>
                </button>
              ),
            )}
            {newGroupName !== null && (
              <div className="flex items-center gap-1 px-1.5 py-0.5">
                <input
                  className="min-w-0 flex-1 rounded border border-indigo-300 px-1.5 py-0.5 t-xs outline-none focus:border-indigo-500"
                  placeholder="组名"
                  value={newGroupName}
                  onChange={(e) => setNewGroupName(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && newGroupName.trim()) createGroupMutation.mutate(newGroupName.trim())
                    if (e.key === 'Escape') setNewGroupName(null)
                  }}
                  autoFocus
                />
              </div>
            )}
          </div>
          <button
            className="mt-2 flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 t-xs text-gray-500 hover:bg-gray-50"
            onClick={() => setNewGroupName('')}
          >
            <Plus className="h-3.5 w-3.5" /> 新建联系组
          </button>
        </div>

        {/* 右侧：列表 或 详情 */}
        <div className="min-w-0 flex-1 p-4 pl-4 pr-6">
          {detailId != null ? (
            <ContactDetailView
              id={detailId}
              groups={groups}
              onBack={() => setDetailId(null)}
              onChanged={invalidate}
              onDeleted={() => { setDetailId(null); invalidate() }}
              onCompose={(c) => openNew({ to: c.name ? `${c.name} <${c.email}>` : c.email })}
              onError={(label) => (err: Error) => setMessage(`${label}：${err.message}`)}
            />
          ) : (
            <>
              <div className="flex items-center gap-2">
                <input
                  className="min-w-0 flex-1 rounded-lg border border-gray-300 px-3 py-1.5 t-md outline-none focus:border-indigo-500"
                  placeholder="搜索姓名或邮箱"
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                />
                <button
                  className="inline-flex shrink-0 items-center gap-1 whitespace-nowrap rounded-lg bg-indigo-600 px-3 py-1.5 t-sm font-medium text-white hover:bg-indigo-700"
                  onClick={() => setAdding(!adding)}
                >
                  <UserPlus className="h-3.5 w-3.5" /> 新增联系人
                </button>
                <button
                  className="shrink-0 cursor-not-allowed whitespace-nowrap rounded-lg border border-gray-200 px-3 py-1.5 t-sm text-gray-300"
                  title="v0.5 提供 CSV/vCard 导入导出"
                  disabled
                >
                  导入/导出
                </button>
                {selected.size > 0 && (
                  <button
                    className="shrink-0 whitespace-nowrap rounded-lg border border-red-200 bg-red-50 px-3 py-1.5 t-sm font-medium text-red-600 hover:bg-red-100"
                    onClick={() => deleteContacts.mutate([...selected])}
                    disabled={deleteContacts.isPending}
                  >
                    删除所选（{selected.size}）
                  </button>
                )}
              </div>

              {adding && (
                <div className="mt-3 flex flex-wrap items-center gap-2 rounded-xl border border-indigo-100 bg-indigo-50/50 px-3 py-2">
                  <input
                    className="min-w-44 flex-1 rounded-lg border border-gray-300 px-2.5 py-1 t-sm outline-none focus:border-indigo-500"
                    placeholder="邮箱地址（必填）"
                    value={form.email}
                    onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
                    autoFocus
                  />
                  <input
                    className="w-32 shrink-0 rounded-lg border border-gray-300 px-2.5 py-1 t-sm outline-none focus:border-indigo-500"
                    placeholder="姓名（可选）"
                    value={form.name}
                    onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                  />
                  <input
                    className="w-32 shrink-0 rounded-lg border border-gray-300 px-2.5 py-1 t-sm outline-none focus:border-indigo-500"
                    placeholder="手机（可选）"
                    value={form.phone}
                    onChange={(e) => setForm((f) => ({ ...f, phone: e.target.value }))}
                  />
                  <button
                    className="shrink-0 rounded-lg bg-indigo-600 px-3 py-1 t-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
                    disabled={!form.email.trim() || addMutation.isPending}
                    onClick={() => addMutation.mutate()}
                  >
                    保存
                  </button>
                  <button
                    className="shrink-0 rounded-lg border border-gray-300 px-3 py-1 t-sm text-gray-500 hover:bg-gray-50"
                    onClick={() => setAdding(false)}
                  >
                    取消
                  </button>
                </div>
              )}
              {message && <p className="mt-2 t-sm text-red-600">{message}</p>}

              <div className="mt-3 max-h-[520px] overflow-auto rounded-xl border border-gray-100">
                <table className="w-full min-w-[640px] text-left">
                  <thead className="sticky top-0 bg-gray-50 t-xs text-gray-400">
                    <tr>
                      <th className="w-8 px-3 py-2" />
                      <th className="whitespace-nowrap px-3 py-2 font-medium">姓名</th>
                      <th className="whitespace-nowrap px-3 py-2 font-medium">邮件地址</th>
                      <th className="whitespace-nowrap px-3 py-2 font-medium">手机</th>
                      <th className="whitespace-nowrap px-3 py-2 font-medium">来源</th>
                      <th className="whitespace-nowrap px-3 py-2 text-right font-medium">往来次数</th>
                      <th className="whitespace-nowrap px-3 py-2 font-medium">最近联系</th>
                    </tr>
                  </thead>
                  <tbody>
                    {listQuery.isLoading && (
                      <tr><td colSpan={7} className="px-3 py-6 text-center t-sm text-gray-400">加载中…</td></tr>
                    )}
                    {!listQuery.isLoading && contacts.length === 0 && (
                      <tr>
                        <td colSpan={7} className="px-3 py-6 text-center t-sm text-gray-300">
                          {view.kind === 'group' ? '这个组还没有联系人——在详情页用「加入组」添加' : '还没有联系人——收发过邮件后会自动出现'}
                        </td>
                      </tr>
                    )}
                    {contacts.map((c) => (
                      <tr
                        key={c.id}
                        className="cursor-pointer border-t border-gray-50 hover:bg-indigo-50/40"
                        onClick={() => { setDetailId(c.id); setSelected(new Set()) }}
                      >
                        <td className="px-3 py-2" onClick={(e) => e.stopPropagation()}>
                          <input
                            type="checkbox"
                            className="h-3.5 w-3.5 accent-indigo-600"
                            checked={selected.has(c.id)}
                            onChange={() => toggleRow(c.id)}
                          />
                        </td>
                        <td className="px-3 py-2 t-md">
                          <span className="flex items-center gap-2">
                            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-indigo-100 t-xs font-medium text-indigo-600">
                              {(c.name || c.email)[0]?.toUpperCase()}
                            </span>
                            <span className="min-w-0 truncate">{c.name || <span className="text-gray-300">（未命名）</span>}</span>
                          </span>
                        </td>
                        <td className="px-3 py-2 t-md text-gray-600">{c.email}</td>
                        <td className="px-3 py-2 t-sm text-gray-500">{c.phone || '—'}</td>
                        <td className="px-3 py-2"><SourceBadges sources={c.sources} /></td>
                        <td className="px-3 py-2 text-right t-md text-gray-500">{c.use_count}</td>
                        <td className="px-3 py-2 t-sm text-gray-400">
                          {c.last_seen_at ? backendLocalDate(c.last_seen_at) : '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      </div>

      {menu && <ContextMenu x={menu.x} y={menu.y} items={groupMenuItems} onClose={() => setMenu(null)} />}
    </section>
  )
}

/** 联系人详情（点击行进入，替代列表；对应 REDESIGN_PLAN §5.4 详情视图） */
function ContactDetailView({
  id,
  groups,
  onBack,
  onChanged,
  onDeleted,
  onCompose,
  onError,
}: {
  id: number
  groups: ContactGroup[]
  onBack: () => void
  onChanged: () => void
  onDeleted: () => void
  onCompose: (c: ContactItem) => void
  onError: (label: string) => (err: Error) => void
}) {
  const queryClient = useQueryClient()
  const detailQuery = useQuery({ queryKey: ['contact-detail', id], queryFn: () => api.getContactDetail(id) })
  const accountsQuery = useQuery({ queryKey: ['accounts'], queryFn: api.getAccounts })
  const c = detailQuery.data?.contact
  const rows = detailQuery.data?.rows ?? []
  const accountEmail = (aid: number | null) =>
    aid == null ? '全局（手动添加）' : accountsQuery.data?.accounts.find((a) => a.id === aid)?.email ?? `账号 #${aid}`

  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState({ name: '', email: '', phone: '', notes: '' })
  const [memberOf, setMemberOf] = useState<ContactGroup[] | null>(null) // 「加入组」菜单展开时算
  const [menu, setMenu] = useState<{ x: number; y: number } | null>(null)

  useEffect(() => {
    if (c) setForm({ name: c.name, email: c.email, phone: c.phone, notes: c.notes })
  }, [c])

  const saveMutation = useMutation({
    mutationFn: () =>
      api.updateContact(id, {
        name: form.name.trim(),
        email: form.email.trim(),
        phone: form.phone.trim(),
        notes: form.notes,
      }),
    onSuccess: () => {
      setEditing(false)
      onChanged()
      void queryClient.invalidateQueries({ queryKey: ['contact-detail', id] })
    },
    onError: onError('保存失败'),
  })
  const removeMember = useMutation({
    mutationFn: ({ gid, email }: { gid: number; email: string }) => api.removeGroupMembers(gid, [email]),
    onSuccess: onChanged,
    onError: onError('移出组失败'),
  })
  const addMember = useMutation({
    mutationFn: ({ gid, email }: { gid: number; email: string }) => api.addGroupMembers(gid, [email]),
    onSuccess: onChanged,
    onError: onError('加入组失败'),
  })
  const deleteMutation = useMutation({
    mutationFn: () => api.deleteContact(id),
    onSuccess: onDeleted,
    onError: onError('删除失败'),
  })

  if (detailQuery.isLoading || !c) {
    return <p className="px-3 py-6 text-center t-sm text-gray-400">加载中…</p>
  }
  const myGroups = groups.filter((g) => g.members.includes(c.email))
  const joinable = groups.filter((g) => !g.members.includes(c.email))

  const moreItems: ContextMenuItem[] = [
    {
      label: '加入组…',
      icon: UsersRound,
      disabled: joinable.length === 0,
      children: joinable.map((g) => ({
        label: g.name,
        onSelect: () => addMember.mutate({ gid: g.id, email: c.email }),
      })),
    },
    {
      label: '复制邮箱地址',
      icon: Copy,
      onSelect: () => void navigator.clipboard.writeText(c.email),
    },
    { label: '删除联系人', icon: Trash2, danger: true, onSelect: () => deleteMutation.mutate() },
  ]

  return (
    <div>
      <div className="flex items-center gap-2">
        <button
          className="inline-flex items-center gap-1 rounded-lg border border-gray-200 bg-white px-2.5 py-1.5 t-sm text-gray-600 hover:bg-gray-50"
          onClick={onBack}
        >
          <ChevronLeft className="h-3.5 w-3.5" /> 返回列表
        </button>
        <span className="flex-1" />
        <button
          className="rounded-lg bg-indigo-600 px-3 py-1.5 t-sm font-medium text-white hover:bg-indigo-700"
          onClick={() => onCompose(c)}
        >
          写信
        </button>
        <button
          className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 t-sm font-medium text-gray-600 hover:bg-gray-50"
          onClick={() => setEditing(!editing)}
        >
          {editing ? '取消编辑' : '编辑'}
        </button>
        <button
          className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 t-sm font-medium text-gray-600 hover:bg-gray-50"
          onClick={(e) => { setMemberOf(myGroups); setMenu({ x: e.clientX, y: e.clientY }) }}
        >
          更多
        </button>
      </div>
      {menu && (
        <ContextMenu
          x={menu.x}
          y={menu.y}
          items={[
            ...(memberOf && memberOf.length > 0
              ? [{
                  label: '移出组…',
                  icon: UsersRound,
                  children: memberOf.map((g) => ({
                    label: g.name,
                    onSelect: () => removeMember.mutate({ gid: g.id, email: c.email }),
                  })),
                } satisfies ContextMenuItem]
              : []),
            ...moreItems,
          ]}
          onClose={() => setMenu(null)}
        />
      )}

      <div className="mt-5 flex items-start gap-5">
        <span className="flex h-20 w-20 shrink-0 items-center justify-center rounded-full bg-sky-100 t-lg font-semibold text-sky-600">
          {(c.name || c.email)[0]?.toUpperCase()}
        </span>
        {editing ? (
          <div className="min-w-0 flex-1 space-y-2">
            <div className="grid grid-cols-2 gap-2">
              <label className="block">
                <span className="t-xs text-gray-400">姓名</span>
                <input
                  className="mt-0.5 w-full rounded-lg border border-gray-300 px-2.5 py-1.5 t-sm outline-none focus:border-indigo-500"
                  value={form.name}
                  onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                />
              </label>
              <label className="block">
                <span className="t-xs text-gray-400">邮件地址</span>
                <input
                  className="mt-0.5 w-full rounded-lg border border-gray-300 px-2.5 py-1.5 t-sm outline-none focus:border-indigo-500"
                  value={form.email}
                  onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
                />
              </label>
              <label className="block">
                <span className="t-xs text-gray-400">手机</span>
                <input
                  className="mt-0.5 w-full rounded-lg border border-gray-300 px-2.5 py-1.5 t-sm outline-none focus:border-indigo-500"
                  value={form.phone}
                  onChange={(e) => setForm((f) => ({ ...f, phone: e.target.value }))}
                />
              </label>
            </div>
            <label className="block">
              <span className="t-xs text-gray-400">备注</span>
              <textarea
                className="mt-0.5 w-full rounded-lg border border-gray-300 px-2.5 py-1.5 t-sm outline-none focus:border-indigo-500"
                rows={2}
                value={form.notes}
                onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
              />
            </label>
            <div className="flex items-center gap-2">
              <button
                className="rounded-lg bg-indigo-600 px-3 py-1.5 t-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
                disabled={saveMutation.isPending || !form.email.trim()}
                onClick={() => saveMutation.mutate()}
              >
                {saveMutation.isPending ? '保存中…' : '保存'}
              </button>
              <button
                className="rounded-lg border border-gray-300 px-3 py-1.5 t-sm text-gray-500 hover:bg-gray-50"
                onClick={() => setEditing(false)}
              >
                取消
              </button>
              <span className="t-xs text-gray-400">改过姓名的联系人不会被自动采集覆盖</span>
            </div>
            {saveMutation.isError && (
              <p className="t-sm text-red-600">保存失败：{(saveMutation.error as Error).message}</p>
            )}
          </div>
        ) : (
          <div className="min-w-0 flex-1">
            <p className="t-lg font-semibold">{c.name || '（未命名）'}</p>
            <p className="mt-0.5 t-md text-gray-600">{c.email}</p>
            {c.phone && <p className="mt-0.5 t-md text-gray-600">📱 {c.phone}</p>}
            {c.notes && <p className="mt-2 whitespace-pre-wrap t-sm text-gray-500">{c.notes}</p>}
            <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 t-sm text-gray-400">
              <span className="inline-flex items-center gap-1.5">
                来源 <SourceBadges sources={c.sources} />
              </span>
              <span>往来 {c.use_count} 次</span>
              <span>最近联系 {c.last_seen_at ? backendLocalDate(c.last_seen_at) : '—'}</span>
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-1.5">
              {myGroups.length > 0 ? (
                myGroups.map((g) => (
                  <span key={g.id} className="inline-flex items-center gap-1 rounded-full bg-indigo-50 px-2 py-0.5 t-xs text-indigo-600">
                    {g.name}
                    <button
                      className="text-indigo-300 hover:text-indigo-600"
                      title="移出组"
                      onClick={() => removeMember.mutate({ gid: g.id, email: c.email })}
                    >
                      ×
                    </button>
                  </span>
                ))
              ) : (
                <span className="t-xs text-gray-300">未分组</span>
              )}
            </div>
          </div>
        )}
      </div>

      {rows.length > 1 && (
        <div className="mt-5 rounded-xl border border-gray-100 bg-gray-50/60 px-4 py-3">
          <p className="t-xs font-medium text-gray-400">该地址在 {rows.length} 个账号下有往来</p>
          <ul className="mt-1.5 space-y-1">
            {rows.map((r) => (
              <li key={r.id} className="flex items-center gap-2 t-sm text-gray-500">
                <span className="min-w-0 flex-1 truncate">{accountEmail(r.account_id)}</span>
                <SourceBadges sources={[r.source]} />
                <span className="text-gray-400">{r.use_count} 次</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

// ── 账号 AI 细粒度授权面板（v0.4 P6，REDESIGN_PLAN §6.4）────────
const GRANT_LABELS: { key: 'read' | 'draft' | 'organize' | 'send' | 'delete'; label: string; hint: string }[] = [
  { key: 'read', label: '读取', hint: '搜索/查看邮件、通讯录与统计' },
  { key: 'draft', label: '起草', hint: '生成待审草稿（不会直接发出）' },
  { key: 'organize', label: '整理', hint: '标记、移动、归档、建文件夹' },
  { key: 'send', label: '发送', hint: '发送草稿（仍受模式与安全约束）' },
  { key: 'delete', label: '删除', hint: '移入废纸篓（高危）' },
]

function AccountAiPanel({ account, onClose }: { account: Account; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [grants, setGrants] = useState(account.ai_grants ?? {
    read: true, draft: account.ai_permission !== 'readonly', organize: account.ai_permission !== 'readonly',
    send: false, delete: false,
  })
  const [isAiMailbox, setIsAiMailbox] = useState(account.is_ai_mailbox)
  const [message, setMessage] = useState('')
  const saveMutation = useMutation({
    mutationFn: () => api.updateAiGrants(account.id, { ...grants, is_ai_mailbox: isAiMailbox }),
    onSuccess: () => {
      setMessage('已保存')
      setTimeout(onClose, 600)
      void queryClient.invalidateQueries({ queryKey: ['accounts'] })
    },
    onError: (err: Error) => setMessage(`保存失败：${err.message}`),
  })

  return (
    <div className="mt-2 rounded-xl border border-indigo-100 bg-indigo-50/40 px-4 py-3">
      <div className="flex items-center justify-between">
        <span className="t-sm font-medium text-indigo-900">AI 权限（总管家在该账号上可做什么）</span>
        <button className="t-xs text-gray-400 hover:text-gray-600" onClick={onClose}>收起</button>
      </div>
      <div className="mt-2 grid gap-1.5">
        {GRANT_LABELS.map((g) => (
          <label key={g.key} className="flex items-center gap-2 t-sm text-gray-700">
            <input
              type="checkbox"
              className="h-4 w-4 accent-indigo-600"
              checked={!!grants[g.key]}
              onChange={(e) => setGrants((prev) => ({ ...prev, [g.key]: e.target.checked }))}
            />
            <b className="font-medium">{g.label}</b>
            <span className="t-xs text-gray-400">{g.hint}</span>
          </label>
        ))}
        <label className="mt-1 flex items-center gap-2 border-t border-indigo-100 pt-2 t-sm text-gray-700">
          <input
            type="checkbox"
            className="h-4 w-4 accent-amber-500"
            checked={isAiMailbox}
            onChange={(e) => {
              if (e.target.checked && !confirm(
                '设为 AI 专属邮箱？该账号将默认以自动模式工作（低风险草稿可直接发送），适合专门注册一个纯 AI 用的邮箱。确认？',
              )) {
                e.target.checked = false
                return
              }
              setIsAiMailbox(e.target.checked)
            }}
          />
          <b className="font-medium text-amber-700">AI 专属邮箱</b>
          <span className="t-xs text-gray-400">默认自动模式、低风险草稿直发（树中带徽章）</span>
        </label>
      </div>
      <div className="mt-2 flex items-center gap-2">
        <button
          className="rounded-lg bg-indigo-600 px-3 py-1.5 t-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          disabled={saveMutation.isPending}
          onClick={() => saveMutation.mutate()}
        >
          {saveMutation.isPending ? '保存中…' : '保存'}
        </button>
        {message && <span className="t-xs text-indigo-600">{message}</span>}
      </div>
    </div>
  )
}

// ── AI 操作记录查看器（v0.4 P6，REDESIGN_PLAN §6.8）：Agent 写动作全量审计 ──
function AgentActionsList() {
  const queryClient = useQueryClient()
  const [status, setStatus] = useState('')
  const listQuery = useQuery({
    queryKey: ['ai-actions', status],
    queryFn: () => api.getAgentActions(status || undefined),
  })
  const actions = listQuery.data?.actions ?? []
  const undoMutation = useMutation({
    mutationFn: (id: number) => api.agentUndo(id),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['ai-actions'] }),
  })
  const delMutation = useMutation({
    mutationFn: (id: number) => api.deleteAgentAction(id),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['ai-actions'] }),
  })
  const [clearScope, setClearScope] = useState('')
  const clearMutation = useMutation({
    mutationFn: (scope: 'old' | 'failed' | 'all') => api.clearAgentActions(scope),
    onSuccess: () => {
      setClearScope('')
      void queryClient.invalidateQueries({ queryKey: ['ai-actions'] })
    },
  })
  const onClear = (scope: string) => {
    if (!scope) return
    if (scope === 'all' && !window.confirm('确定清空全部操作记录？已发送记录也会删除，不可恢复。')) {
      setClearScope('')
      return
    }
    clearMutation.mutate(scope as 'old' | 'failed' | 'all')
  }

  return (
    <div className="mt-4 rounded-xl border border-gray-100 bg-gray-50/60 px-4 py-3">
      <div className="flex items-center gap-2">
        <span className="t-sm font-medium text-gray-700">操作记录</span>
        <span className="t-xs text-gray-400">总管家写动作全量留痕，支持撤销与删除追溯</span>
        <span className="flex-1" />
        <select
          className="rounded-lg border border-gray-200 px-2 py-1 t-xs text-gray-600 outline-none"
          value={clearScope}
          onChange={(e) => onClear(e.target.value)}
        >
          <option value="">清理…</option>
          <option value="old">90 天前记录</option>
          <option value="failed">失败与拒绝</option>
          <option value="all">全部记录</option>
        </select>
        <select
          className="rounded-lg border border-gray-200 px-2 py-1 t-xs text-gray-600 outline-none"
          value={status}
          onChange={(e) => setStatus(e.target.value)}
        >
          <option value="">全部状态</option>
          <option value="executed">已执行</option>
          <option value="pending">待批准</option>
          <option value="rejected">已拒绝</option>
          <option value="failed">失败</option>
          <option value="undone">已撤销</option>
        </select>
      </div>
      <div className="mt-2 max-h-72 space-y-1 overflow-y-auto">
        {listQuery.isLoading && <div className="py-3 t-sm text-gray-400">加载中…</div>}
        {!listQuery.isLoading && actions.length === 0 && (
          <div className="py-3 t-sm text-gray-300">还没有记录</div>
        )}
        {actions.map((a) => (
          <div
            key={a.id}
            title={a.status === 'executed' && !a.undoable ? '该类型不支持撤销' : undefined}
            className="flex items-center gap-2 rounded-lg bg-white px-2.5 py-1.5 t-xs"
          >
            <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${
              a.status === 'executed' ? 'bg-emerald-500'
                : a.status === 'pending' ? 'bg-amber-400'
                  : a.status === 'failed' || a.status === 'rejected' ? 'bg-red-400' : 'bg-gray-300'
            }`} />
            <span className="w-24 shrink-0 truncate font-medium text-gray-700">{a.tool}</span>
            <span className="w-36 shrink-0 truncate text-gray-400">{a.account_email ?? '—'}</span>
            <span className="min-w-0 flex-1 truncate text-gray-500">
              {a.error ?? JSON.stringify(a.result ?? a.params ?? {}).slice(0, 80)}
            </span>
            <span
              className="shrink-0 text-gray-300"
              title={a.mode === 'auto' ? '自动模式：授权约束内直接执行' : '审批模式：写操作经你批准后执行'}
            >
              {a.mode === 'auto' ? '自动' : '审批'}
            </span>
            <span className="w-24 shrink-0 text-right text-gray-300">{a.created_at.slice(5, 16)}</span>
            {a.status === 'executed' && a.undoable && (
              <button
                className="shrink-0 rounded border border-gray-200 px-1.5 py-0.5 text-gray-500 hover:text-indigo-600"
                title="撤销该操作"
                onClick={() => undoMutation.mutate(a.id)}
              >
                撤销
              </button>
            )}
            <button
              className="shrink-0 text-gray-300 hover:text-red-500"
              title="删除该记录"
              onClick={() => delMutation.mutate(a.id)}
            >
              <Trash2 className="h-3 w-3" />
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── AI 记忆（REDESIGN_PLAN §18.5）：跨会话用户偏好，查看/逐条清除 ──
function AgentMemoryList() {
  const queryClient = useQueryClient()
  const listQuery = useQuery({ queryKey: ['ai-memory'], queryFn: api.getAgentMemory })
  const memories = listQuery.data?.memories ?? []
  const delMutation = useMutation({
    mutationFn: (id: number) => api.deleteAgentMemory(id),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['ai-memory'] }),
  })

  return (
    <div className="mt-3 rounded-xl border border-gray-100 bg-gray-50/60 px-4 py-3">
      <div className="flex items-center gap-2">
        <span className="t-sm font-medium text-gray-700">AI 记忆</span>
        <span className="t-xs text-gray-400">总管家跨对话记住的你的偏好，只来自你说的话，可随时删除</span>
      </div>
      <div className="mt-2 max-h-48 space-y-1 overflow-y-auto">
        {listQuery.isLoading && <div className="py-2 t-sm text-gray-400">加载中…</div>}
        {!listQuery.isLoading && memories.length === 0 && (
          <div className="py-2 t-xs text-gray-300">还没有记忆。对话里说「记住…」即可让总管家长期记住</div>
        )}
        {memories.map((m) => (
          <div key={m.id} className="flex items-start gap-2 rounded-lg bg-white px-2.5 py-1.5 t-xs">
            <span className="min-w-0 flex-1 text-gray-700">
              {m.content}
              <span className="ml-1 text-gray-400">（原话：「{m.evidence}」）</span>
            </span>
            <span className="shrink-0 text-gray-300">{m.updated_at.slice(5, 10)}</span>
            <button
              className="shrink-0 text-gray-300 hover:text-red-500"
              title="删除该记忆"
              onClick={() => delMutation.mutate(m.id)}
            >
              <Trash2 className="h-3 w-3" />
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── 本机路径行（关于页）：路径 select-all 可复制 ──
function PathRow({ label, path, hint }: { label: string; path?: string; hint: string }) {
  const [copied, setCopied] = useState(false)
  const copy = () => {
    if (!path) return
    void navigator.clipboard.writeText(path).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    })
  }
  return (
    <div className="mt-2.5 flex items-start gap-2" title={hint}>
      <span className="w-16 shrink-0 t-sm text-gray-500">{label}</span>
      <code className="min-w-0 flex-1 break-all rounded bg-white px-2 py-1 t-xs text-gray-700 select-all">
        {path ?? '…'}
      </code>
      <button
        className="shrink-0 rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-indigo-600"
        title={copied ? '已复制' : `复制${label}路径`}
        onClick={copy}
        disabled={!path}
      >
        {copied ? <Check className="h-3.5 w-3.5 text-emerald-500" /> : <Copy className="h-3.5 w-3.5" />}
      </button>
    </div>
  )
}

// ── 发件人白/黑名单管理（通用页）：查看/添加/移除，与邮件右键菜单同一份 API ──
const SENDER_LIST_COLUMNS: {
  type: SenderListEntry['list_type']
  label: string
  icon: typeof UserCheck
  chipCls: string
  hint: string
  placeholder: string
}[] = [
  {
    type: 'whitelist',
    label: '白名单',
    icon: UserCheck,
    chipCls: 'border-emerald-200 text-emerald-700',
    hint: '永远留在收件箱并跳过 AI',
    placeholder: '邮箱或 @域名，回车加入',
  },
  {
    type: 'blacklist',
    label: '黑名单',
    icon: Ban,
    chipCls: 'border-red-200 text-red-600',
    hint: '直接归档并跳过 AI',
    placeholder: '邮箱或 @域名，回车加入',
  },
  {
    type: 'image_trust',
    label: '图片信任',
    icon: Eye,
    chipCls: 'border-sky-200 text-sky-600',
    hint: '始终显示该发件人的外部图片',
    placeholder: '邮箱或 @域名，回车加入',
  },
]

function SenderListsPanel() {
  const queryClient = useQueryClient()
  const listsQuery = useQuery({ queryKey: ['sender-lists'], queryFn: api.getSenderLists })
  const [drafts, setDrafts] = useState<Record<string, string>>({})
  const [error, setError] = useState('')

  const invalidate = () => void queryClient.invalidateQueries({ queryKey: ['sender-lists'] })
  const addMutation = useMutation({
    mutationFn: ({ pattern, list_type }: { pattern: string; list_type: SenderListEntry['list_type'] }) =>
      api.addSenderList(pattern, list_type),
    onSuccess: invalidate,
    onError: (err: Error) => setError(err.message),
  })
  const removeMutation = useMutation({
    mutationFn: (id: number) => api.removeSenderList(id),
    onSuccess: invalidate,
    onError: (err: Error) => setError(err.message),
  })

  const entries = listsQuery.data?.entries ?? []
  const submit = (type: SenderListEntry['list_type']) => {
    const pattern = (drafts[type] ?? '').trim()
    if (!pattern) return
    setError('')
    addMutation.mutate({ pattern, list_type: type })
    setDrafts((d) => ({ ...d, [type]: '' }))
  }

  return (
    <div className="mt-4 rounded-xl border border-gray-100 bg-gray-50/60 px-4 py-3">
      <div className="flex flex-wrap items-baseline gap-2">
        <span className="t-md font-medium text-gray-700">发件人白/黑名单</span>
        <span className="t-xs text-gray-400">
          规则先于 AI 生效、零成本；也可在邮件列表右键发件人快速加入。条目为完整邮箱或以 @ 开头的域名。
        </span>
      </div>
      <div className="mt-2 grid grid-cols-1 gap-3 md:grid-cols-3">
        {SENDER_LIST_COLUMNS.map(({ type, label, icon: Icon, chipCls, hint, placeholder }) => {
          const items = entries.filter((e) => e.list_type === type)
          return (
            <div key={type} className="rounded-lg border border-gray-100 bg-white px-3 py-2">
              <div className="flex items-center gap-1.5">
                <Icon className="h-3.5 w-3.5 text-gray-400" />
                <span className="t-sm font-medium text-gray-700">{label}</span>
                <span className="t-xs text-gray-300">{items.length}</span>
              </div>
              <p className="mt-0.5 t-xs text-gray-400">{hint}</p>
              <div className="mt-1.5 flex max-h-28 flex-wrap gap-1 overflow-y-auto">
                {items.length === 0 && <span className="t-xs text-gray-300">暂无条目</span>}
                {items.map((e) => (
                  <span
                    key={e.id}
                    className={`inline-flex max-w-full items-center gap-1 rounded-full border px-2 py-0.5 t-xs ${chipCls}`}
                  >
                    <span className="truncate" title={e.pattern}>{e.pattern}</span>
                    <button
                      className="shrink-0 text-gray-300 hover:text-red-500"
                      title={`从${label}移除 ${e.pattern}`}
                      onClick={() => removeMutation.mutate(e.id)}
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>
              <input
                className="mt-1.5 w-full rounded-lg border border-gray-200 px-2 py-1 t-xs outline-none focus:border-indigo-400"
                placeholder={placeholder}
                value={drafts[type] ?? ''}
                onChange={(e) => setDrafts((d) => ({ ...d, [type]: e.target.value }))}
                onKeyDown={(e) => e.key === 'Enter' && submit(type)}
              />
            </div>
          )
        })}
      </div>
      {(error || addMutation.isError) && (
        <p className="mt-1.5 t-xs text-red-500">{error || (addMutation.error as Error).message}</p>
      )}
    </div>
  )
}

// ── 写信（设置页）：自动签名开关 + 签名/模板管理入口（复用写信台的管理弹窗，数据同源）──
function ComposeSection({
  accounts,
  autoSig,
  onAutoSig,
}: {
  accounts: Account[]
  autoSig: boolean
  onAutoSig: (v: boolean) => void
}) {
  const { data: extras } = useQuery({ queryKey: ['compose-extras'], queryFn: api.getComposeExtras })
  const [tplOpen, setTplOpen] = useState(false)
  const [sigOpen, setSigOpen] = useState(false)
  const sigMap = new Map((extras?.signatures ?? []).map((s) => [s.account_id, s.content]))
  const templates = extras?.templates ?? []

  return (
    <section className="rounded-2xl border border-gray-200 bg-white p-6 shadow-sm">
      <h2 className="t-lg font-semibold">写信</h2>

      <div className="mt-4 rounded-xl border border-gray-100 bg-gray-50/60 px-4 py-3">
        <label className="flex items-center gap-2 t-md font-medium text-gray-700">
          <input
            type="checkbox"
            className="h-4 w-4 accent-indigo-600"
            checked={autoSig}
            disabled={accounts.length === 0}
            onChange={(e) => onAutoSig(e.target.checked)}
          />
          自动插入签名
        </label>
        <p className="mt-1.5 t-sm leading-relaxed text-gray-400">
          开启后，新邮件与回复/转发自动带上发件账号的签名（回复时插在引用块之前）；
          仅在打开写信标签时注入一次，草稿恢复不会重复添加，AI 拟稿由「文风提示词」负责。
        </p>
      </div>

      <div className="mt-3 rounded-xl border border-gray-100 bg-gray-50/60 px-4 py-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="t-md font-medium text-gray-700">签名</span>
          <span className="t-xs text-gray-400">按账号各存一段 Markdown，写信工具栏「签名」可手动插入</span>
          <span className="flex-1" />
          <button
            className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 t-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50"
            onClick={() => setSigOpen(true)}
            disabled={accounts.length === 0}
          >
            <PenLine className="mr-1 inline h-3.5 w-3.5" />
            编辑签名…
          </button>
        </div>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {accounts.length === 0 && <span className="t-xs text-gray-300">先在「邮箱账号」添加账号</span>}
          {accounts.map((a) => (
            <span
              key={a.id}
              className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 t-xs ${
                sigMap.get(a.id)?.trim()
                  ? 'border-emerald-200 text-emerald-700'
                  : 'border-gray-200 text-gray-400'
              }`}
            >
              {a.email}
              {sigMap.get(a.id)?.trim() ? '✓' : '（未设置）'}
            </span>
          ))}
        </div>
      </div>

      <div className="mt-3 rounded-xl border border-gray-100 bg-gray-50/60 px-4 py-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="t-md font-medium text-gray-700">模板</span>
          <span className="t-xs text-gray-400">
            {templates.length > 0 ? `已存 ${templates.length} 个常用文案模板` : '还没有模板'}
            ，写信工具栏「插入模板」选择即插入光标处
          </span>
          <span className="flex-1" />
          <button
            className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 t-sm text-gray-700 hover:bg-gray-50"
            onClick={() => setTplOpen(true)}
          >
            管理模板…
          </button>
        </div>
        {templates.length > 0 && (
          <div className="mt-2 flex max-h-24 flex-wrap gap-1 overflow-y-auto">
            {templates.map((t) => (
              <span
                key={t.id}
                className="max-w-72 truncate rounded-full border border-gray-200 bg-white px-2 py-0.5 t-xs text-gray-500"
                title={t.content.slice(0, 120)}
              >
                {t.name}
              </span>
            ))}
          </div>
        )}
      </div>

      {tplOpen && <TemplateManager onClose={() => setTplOpen(false)} />}
      {sigOpen && <SignatureEditor accounts={accounts} onClose={() => setSigOpen(false)} />}
    </section>
  )
}
