import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ChevronLeft, ChevronRight, Inbox, Loader2, Paperclip, Pencil, RefreshCw, Search, Sparkles, Star,
} from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, type EmailQuery } from '../api/client'
import { useAIEnabled } from '../api/useAI'
import { useFlash } from '../hooks/useFlash'
import { useJob } from '../api/useJob'
import { categoryBadgeMap, useCategories } from '../api/useMeta'
import { shortDate } from '../utils/format'
import {
  type EmailDetail, type EmailListResp, type EmailSummary, type FolderCacheItem, type JobInfo,
  type OrganizeResult,
} from '../types'
import { useCompose } from './compose/ComposeContext'
import ContextMenu, { type ContextMenuItem } from './ContextMenu'
import EmailReader from './EmailReader'
import SplitDivider from './SplitDivider'
import { appZoom, usePanelWidth } from '../hooks/usePanelWidth'

const PAGE_SIZE = 50

const batchBtn =
  'rounded-md border border-indigo-200 bg-white px-1.5 py-0.5 t-sm text-gray-600 transition-colors hover:text-indigo-700 disabled:opacity-50'

/** 后台任务进度条（列表工具条内联显示；job 为 null 或已终态时不渲染）。 */
function JobProgressBar({ job, label }: { job: JobInfo | null; label: string }) {
  if (!job || job.status !== 'running') return null
  return (
    <span className="flex items-center gap-1.5">
      <span className="h-1.5 w-28 overflow-hidden rounded-full bg-indigo-100">
        <span
          className="block h-full rounded-full bg-indigo-500 transition-all duration-500"
          style={{ width: `${Math.max(5, Math.round(job.progress * 100))}%` }}
        />
      </span>
      <span className="t-xs text-indigo-500">
        {label} {Math.round(job.progress * 100)}%{job.detail ? ` · ${job.detail}` : ''}
      </span>
    </span>
  )
}

/**
 * 邮件浏览主界面（聚合收件箱 / 按账号收件箱 / 任意服务器文件夹共用）。
 * 账号与文件夹由 MailPage 的文件夹树下发（initialAccountId/initialFolder），
 * 树换 key 重挂即切换视图；行可拖拽（多选集合一起拖），支持键盘导航。
 */
export default function MailBrowser({
  initialAccountId,
  initialFolder = 'INBOX',
}: {
  initialAccountId?: number | null
  initialFolder?: string
}) {
  const queryClient = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()
  const compose = useCompose()
  const aiEnabled = useAIEnabled()
  const categoryMeta = categoryBadgeMap(useCategories())

  const [accountId, setAccountId] = useState<number | null>(() => {
    if (initialAccountId !== undefined) return initialAccountId
    const v = Number(localStorage.getItem('nmail_sel_account'))
    return Number.isFinite(v) && v > 0 ? v : null
  })
  // 文件夹由树决定（重挂换视图），组件内不自行切换
  const [folder] = useState(initialFolder)
  const [q, setQ] = useState('')
  const [qInput, setQInput] = useState('')
  const [starredOnly, setStarredOnly] = useState(false)
  const [category, setCategory] = useState('')
  const [page, setPage] = useState(0)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [selectedIds, setSelectedIds] = useState<number[]>([])
  const [showImages, setShowImages] = useState(false)
  const [syncMessage, setSyncMessage] = useFlash(5000)

  // 分屏布局：列表宽度可拖拽（SplitDivider + usePanelWidth），阅读区可全屏，均记忆在本地
  const { width: listWidth, setWidth: setListWidth, persist: persistListWidth, reset: resetListWidth } =
    usePanelWidth('nmail_list_width', { min: 240, max: 640, fallback: 340 })
  const [readerFull, setReaderFull] = useState(() => localStorage.getItem('nmail_reader_full') === '1')
  const listRef = useRef<HTMLElement>(null)

  const moveListWidth = (e: MouseEvent) => {
    if (!listRef.current) return
    setListWidth((e.clientX - listRef.current.getBoundingClientRect().left) / appZoom())
  }

  const toggleFull = () => {
    setReaderFull((v) => {
      localStorage.setItem('nmail_reader_full', v ? '0' : '1')
      return !v
    })
  }

  const accountsQuery = useQuery({
    queryKey: ['accounts'],
    queryFn: api.getAccounts,
    // 后台同步进行中时轮询账号状态；检测到某账号从同步中恢复即刷新邮件列表
    refetchInterval: (query) =>
      query.state.data?.accounts.some((a) => a.status === 'syncing') ? 2000 : false,
  })
  const accounts = accountsQuery.data?.accounts ?? []
  const hasAccounts = accounts.length > 0

  // 持久化选择；持久化的账号已被删除时回落「全部邮箱」
  useEffect(() => {
    localStorage.setItem('nmail_sel_account', accountId === null ? '' : String(accountId))
    localStorage.setItem('nmail_sel_folder', folder)
  }, [accountId, folder])
  useEffect(() => {
    if (accountsQuery.data && accountId !== null && !accounts.some((a) => a.id === accountId)) {
      setAccountId(null)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accountsQuery.data, accountId])
  const prevSyncing = useRef<Set<number>>(new Set())
  useEffect(() => {
    const now = new Set(accounts.filter((a) => a.status === 'syncing').map((a) => a.id))
    let finished = false
    for (const id of prevSyncing.current) {
      if (!now.has(id)) finished = true
    }
    prevSyncing.current = now
    if (finished) invalidateMail()
  })

  // 批量栏「移动到…」下拉的文件夹清单（与树共用缓存；仅选了账号时有意义）
  const foldersCacheQuery = useQuery({
    queryKey: ['folder-cache', accountId],
    queryFn: () => api.getFolders(accountId!),
    enabled: accountId != null,
    staleTime: 5 * 60 * 1000,
  })
  const folders: FolderCacheItem[] = foldersCacheQuery.data?.folders ?? []

  const listQueryKey = ['emails', { accountId, folder, q, starredOnly, category, page }]
  const listQuery = useQuery({
    queryKey: listQueryKey,
    queryFn: () =>
      api.getEmails({
        account_id: accountId,
        folder: q ? undefined : folder,
        q: q || undefined,
        starred: starredOnly ? true : null,
        category: category || null,
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      } satisfies EmailQuery),
    enabled: hasAccounts,
    refetchInterval: 20000,
    placeholderData: (prev) => prev,
  })
  const items: EmailSummary[] = listQuery.data?.items ?? []
  const total = listQuery.data?.total ?? 0

  const detailQuery = useQuery({
    queryKey: ['email', selectedId, showImages],
    queryFn: () => api.getEmail(selectedId!, showImages),
    enabled: selectedId != null,
  })
  const detail: EmailDetail | null = detailQuery.data ?? null

  // 摘要页「查看」跳转：/?focus=<email_id> 直接打开对应邮件（保留其余参数）
  const focusId = searchParams.get('focus')
  useEffect(() => {
    if (focusId) {
      setSelectedId(Number(focusId))
      setShowImages(false)
      setSearchParams(
        (prev) => {
          prev.delete('focus')
          return prev
        },
        { replace: true },
      )
    }
  }, [focusId, setSearchParams])

  const invalidateMail = () => {
    void queryClient.invalidateQueries({ queryKey: ['emails'] })
    void queryClient.invalidateQueries({ queryKey: ['email'] })
    void queryClient.invalidateQueries({ queryKey: ['notifications'] })
    void queryClient.invalidateQueries({ queryKey: ['folder-cache'] }) // 树未读徽章跟随
  }

  // 筛选/翻页变化时清空批量选择
  useEffect(() => {
    setSelectedIds([])
  }, [accountId, folder, q, starredOnly, category, page])

  // 全文模式下 Esc 返回列表
  useEffect(() => {
    if (selectedId == null) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setSelectedId(null)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [selectedId])

  // ── 键盘导航（VSCode/Gmail 风，REDESIGN_PLAN §4.3）──
  const [cursorId, setCursorId] = useState<number | null>(null)
  const searchRef = useRef<HTMLInputElement>(null)
  // 邮件行右键菜单（§4.3；系统右键已在应用层全局屏蔽）
  const [rowMenu, setRowMenu] = useState<{ x: number; y: number; item: EmailSummary } | null>(null)
  // 右键「移动到…」的文件夹清单：按被右键邮件所属账号取（聚合视图下与当前筛选账号不同）
  const moveFoldersQuery = useQuery({
    queryKey: ['folder-cache', rowMenu?.item.account_id ?? accountId],
    queryFn: () => api.getFolders((rowMenu?.item.account_id ?? accountId)!),
    enabled: rowMenu != null,
    staleTime: 5 * 60 * 1000,
  })
  useEffect(() => {
    // 列表变化时光标跟随选中，无选中则落在第一封
    if (selectedId != null && items.some((i) => i.id === selectedId)) {
      setCursorId(selectedId)
    } else if (cursorId == null || !items.some((i) => i.id === cursorId)) {
      setCursorId(items[0]?.id ?? null)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items, selectedId])
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (items.length === 0) return
      const target = e.target as HTMLElement | null
      if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA'
        || target.tagName === 'SELECT' || target.isContentEditable)) return
      if (e.metaKey || e.ctrlKey || e.altKey) return
      const idx = items.findIndex((i) => i.id === cursorId)
      const move = (delta: number) => {
        const next = items[Math.min(items.length - 1, Math.max(0, (idx === -1 ? 0 : idx) + delta))]
        if (next) {
          setCursorId(next.id)
          document.querySelector(`[data-email-id="${next.id}"]`)?.scrollIntoView({ block: 'nearest' })
        }
      }
      switch (e.key) {
        case 'j': case 'ArrowDown': e.preventDefault(); move(1); break
        case 'k': case 'ArrowUp': e.preventDefault(); move(-1); break
        case 'x': {
          e.preventDefault()
          if (cursorId != null) toggleRow(cursorId)
          break
        }
        case 'o': case 'Enter': {
          e.preventDefault()
          const mail = items.find((i) => i.id === cursorId)
          if (mail) selectEmail(mail)
          break
        }
        case 'e': {
          e.preventDefault()
          if (cursorId != null) actionMutation.mutate({ id: cursorId, action: 'archive' })
          break
        }
        case '#': {
          e.preventDefault()
          if (cursorId != null) actionMutation.mutate({ id: cursorId, action: 'trash' })
          break
        }
        case 'c': e.preventDefault(); compose.openNew(); break
        case '/': e.preventDefault(); searchRef.current?.focus(); break
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items, cursorId, selectedIds])

  const actionMutation = useMutation({
    mutationFn: ({ id, action, folder: dest }: { id: number; action: string; folder?: string }) =>
      api.emailAction(id, action, dest),
    onSuccess: (_data, variables) => {
      invalidateMail()
      // 归档/删除/移动后当前邮件会离开当前视图，清除选中
      if (['archive', 'unarchive', 'trash', 'move'].includes(variables.action)) {
        setSelectedId(null)
      }
    },
  })

  const syncMutation = useMutation({
    // 同步为后台任务：触发即返回，新邮件经通知/轮询自动刷新列表
    mutationFn: async () => {
      const targets = accountId != null ? [accountId] : accounts.map((a) => a.id)
      let started = 0
      for (const id of targets) {
        const r = await api.syncAccount(id)
        if (r.started) started += 1
      }
      return { targets: targets.length, started }
    },
    onSuccess: ({ targets, started }) => {
      void queryClient.invalidateQueries({ queryKey: ['accounts'] })
      setSyncMessage(
        started === 0
          ? '同步已在进行中，请稍候'
          : targets > 1
            ? `已在后台开始同步 ${started} 个账号，新邮件到达后会自动刷新`
            : '已在后台开始同步，新邮件到达后会自动刷新',
      )
    },
    onError: (error: Error) => setSyncMessage(`同步触发失败：${error.message}`),
  })

  // AI 整理：提交后台 job（HTTP 立即返回），轮询进度，终态展示结果
  const { job: organizeJob, start: startOrganizeJob } = useJob((finished) => {
    if (finished.status === 'failed') {
      setSyncMessage(`AI 整理失败：${finished.detail || '未知错误'}`, 6000)
      return
    }
    const result = (finished.result ?? {}) as Partial<OrganizeResult>
    invalidateMail()
    if (result.skipped_no_ai) {
      setSyncMessage('AI 未配置或已停用，请到设置 - AI 配置检查', 6000)
    } else {
      setSyncMessage(
        `AI 整理完成：分类 ${result.classified ?? 0} 封${(result.archived ?? 0) > 0 ? `，归档营销 ${result.archived} 封` : ''}`,
        6000,
      )
    }
  })

  const organizeMutation = useMutation({
    mutationFn: () => api.aiOrganize({ account_id: accountId ?? undefined, folder: 'INBOX', limit: 200 }),
    onSuccess: ({ job_id }) => startOrganizeJob(job_id),
    onError: (error: Error) => {
      setSyncMessage(`AI 整理提交失败：${error.message}`, 6000)
    },
  })
  const organizing = organizeMutation.isPending || organizeJob?.status === 'running'

  // 已读合并写（v0.4 审查 U4）：点击先本地置已读（乐观），800ms 内连续点击
  // 合并为一次批量请求；快速浏览不再逐封直发 IMAP SEEN。失败仅提示，20s 轮询会校正；
  // 成功后失效 folder-cache——树未读徽章即时跟随，不等下次同步。
  const readQueueRef = useRef<Set<number>>(new Set())
  const readTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const markReadLocal = (ids: number[]) => {
    const data = queryClient.getQueryData<EmailListResp>(listQueryKey)
    if (!data) return
    const idSet = new Set(ids)
    queryClient.setQueryData(listQueryKey, {
      ...data,
      items: data.items.map((it) => (idSet.has(it.id) ? { ...it, is_read: true } : it)),
    })
  }
  const flushReadQueue = () => {
    readTimerRef.current = null
    const ids = [...readQueueRef.current]
    readQueueRef.current.clear()
    if (ids.length === 0) return
    void api
      .batchAction(ids, 'read')
      .then((res) => {
        // 后端「服务器成功才动本地」：打标失败仍返回 HTTP 200 + ok:false——必须出声
        if (!res.ok || res.failed > 0) {
          setSyncMessage('已读标记失败：账号连接异常，列表稍后恢复真实状态', 6000)
          return
        }
        queryClient.invalidateQueries({ queryKey: ['folder-cache'] })
      })
      .catch(() => {
        setSyncMessage('已读标记失败，列表刷新后会恢复真实状态', 5000)
      })
  }
  useEffect(() => () => {
    // 卸载前把未落地的已读直接发出（fire-and-forget）
    if (readTimerRef.current) clearTimeout(readTimerRef.current)
    const ids = [...readQueueRef.current]
    readQueueRef.current.clear()
    if (ids.length > 0) void api.batchAction(ids, 'read').catch(() => undefined)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const selectEmail = (item: EmailSummary) => {
    setSelectedId(item.id)
    setShowImages(false)
    if (!item.is_read) {
      markReadLocal([item.id])
      readQueueRef.current.add(item.id)
      if (readTimerRef.current) clearTimeout(readTimerRef.current)
      readTimerRef.current = setTimeout(flushReadQueue, 800)
    }
  }

  const openCompose = (mode: 'reply' | 'replyAll' | 'forward') => {
    if (!detail) return
    void compose.openReply(mode, detail)
  }

  const applyQ = () => {
    setQ(qInput.trim())
    setPage(0)
    setSelectedId(null)
  }

  const actionBusy = actionMutation.isPending

  // ── 批量选择与操作 ──
  const toggleRow = (id: number) =>
    setSelectedIds((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]))
  const allSelected = items.length > 0 && items.every((i) => selectedIds.includes(i.id))
  const toggleAll = () =>
    setSelectedIds(allSelected ? [] : [...new Set([...selectedIds, ...items.map((i) => i.id)])])

  // 批量 trash/move：后端转后台 job（打标/归档类仍同步返回）
  const { job: batchJob, start: startBatchJob } = useJob((finished) => {
    invalidateMail()
    if (finished.status === 'failed') {
      setSyncMessage(`批量操作失败：${finished.detail || '未知错误'}`)
    } else {
      const r = (finished.result ?? {}) as { updated?: number; failed?: number }
      const failedNote = (r.failed ?? 0) > 0 ? `，${r.failed} 封失败` : ''
      setSyncMessage(`批量操作完成：${r.updated ?? 0} 封${failedNote}`)
    }
  })

  const batchMutation = useMutation({
    mutationFn: ({ action, folder: dest }: { action: string; folder?: string }) =>
      api.batchAction(selectedIds, action, dest),
    onSuccess: (result) => {
      setSelectedIds([])
      if (result.job_id != null) {
        startBatchJob(result.job_id)
        return
      }
      invalidateMail()
      const failedNote = result.failed > 0 ? `，${result.failed} 封失败` : ''
      setSyncMessage(`批量操作完成：${result.updated} 封${failedNote}`)
    },
    onError: (error: Error) => {
      setSyncMessage(`批量操作失败：${error.message}`, 6000)
    },
  })
  const batchBusy = batchMutation.isPending || batchJob?.status === 'running'
  const runBatch = (action: string, folder?: string) =>
    batchMutation.mutate({ action, folder })

  // ── 空账号引导 ──
  if (!accountsQuery.isLoading && !hasAccounts) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="max-w-md rounded-2xl border border-gray-200 bg-white p-8 text-center shadow-sm">
          <Inbox className="mx-auto h-10 w-10 text-indigo-200" />
          <h2 className="mt-3 t-lg font-semibold">添加你的第一个邮箱</h2>
          <p className="mt-2 t-md text-gray-500">
            Nmail 支持 QQ、163、Gmail、Outlook 等 19+ 服务商，填入邮箱和授权码即可。
          </p>
          <Link
            to="/settings"
            className="mt-4 inline-block rounded-lg bg-indigo-600 px-4 py-2 t-md font-medium text-white hover:bg-indigo-700"
          >
            前往设置添加账号
          </Link>
        </div>
      </div>
    )
  }

  const inFullRead = selectedId != null && readerFull

  return (
    <div className="flex h-full flex-col">
      {/* 页眉：全局搜索 + 收信 / AI 整理 / 写信（全屏阅读时隐藏） */}
      {!inFullRead && (
        <header className="zoom-compact flex shrink-0 items-center gap-1.5 border-b border-gray-200 bg-white px-3 py-2">
          <div className="relative min-w-0 max-w-2xl flex-1">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
            <input
              ref={searchRef}
              className="w-full rounded-lg border border-gray-300 py-1.5 pl-8 pr-2 t-md outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100"
              placeholder="搜索邮件，回车确认（覆盖所有文件夹）"
              value={qInput}
              onChange={(e) => setQInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && applyQ()}
            />
          </div>
          <span className="min-w-2 flex-1" />
          <button
            className="inline-flex shrink-0 items-center whitespace-nowrap rounded-lg bg-indigo-600 px-2.5 py-1.5 t-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
            onClick={() => syncMutation.mutate()}
            disabled={syncMutation.isPending}
            title="立即从服务器收信"
          >
            <RefreshCw className={`mr-1 h-3.5 w-3.5 ${syncMutation.isPending ? 'animate-spin' : ''}`} />
            收信
          </button>
          {aiEnabled && (
            <button
              className="inline-flex shrink-0 items-center whitespace-nowrap rounded-lg border border-violet-200 bg-violet-50 px-2.5 py-1.5 t-sm font-medium text-violet-700 hover:bg-violet-100 disabled:opacity-50"
              onClick={() => organizeMutation.mutate()}
              disabled={organizing}
              title="让 AI 为收件箱中未分类的邮件补跑分类，营销邮件自动归档"
            >
              <Sparkles className={`mr-1 h-3.5 w-3.5 ${organizing ? 'animate-pulse' : ''}`} />
              {organizing ? '整理中…' : 'AI 整理'}
            </button>
          )}
          <button
            className="inline-flex shrink-0 items-center whitespace-nowrap rounded-lg border border-gray-300 px-2.5 py-1.5 t-sm font-medium text-gray-700 hover:bg-gray-50"
            onClick={() => void compose.openNew()}
          >
            <Pencil className="mr-1 h-3.5 w-3.5" /> 写信
          </button>
        </header>
      )}
      <div className="flex min-h-0 flex-1">
      {/* 邮件列表（分屏左栏；全屏阅读时隐藏） */}
      {!inFullRead && (
      <>
      <section ref={listRef} style={{ width: listWidth }} className="flex shrink-0 flex-col overflow-hidden border-r border-gray-200 bg-white">
        <div className="space-y-1.5 border-b border-gray-100 p-2">
          <div className="flex items-center gap-1.5">
            {/* 账号/文件夹切换在左侧文件夹树（v0.4）；此处只留筛选与星标 */}
            <span
              className="min-w-0 flex-1 truncate rounded-lg bg-gray-50 px-2 py-1 t-sm font-medium text-gray-500"
              title={accountId == null ? '全部账号' : accounts.find((a) => a.id === accountId)?.email}
            >
              {accountId == null
                ? '全部账号'
                : accounts.find((a) => a.id === accountId)?.email ?? '已删除账号'}
              <span className="mx-1 text-gray-300">/</span>
              {q ? `搜索「${q}」` : folder === 'INBOX' ? '收件箱' : folder}
            </span>
            <button
              className={`inline-flex shrink-0 items-center gap-1 whitespace-nowrap rounded-lg border px-1.5 py-1 t-sm ${
                starredOnly ? 'border-amber-300 bg-amber-50 text-amber-600' : 'border-gray-300 text-gray-500'
              }`}
              onClick={() => {
                setStarredOnly((v) => !v)
                setPage(0)
                setSelectedId(null)
              }}
              title="只看星标"
            >
              <Star className={`h-3 w-3 ${starredOnly ? 'fill-amber-400 text-amber-400' : ''}`} />
              星标
            </button>
            <select
              className="min-w-0 flex-1 rounded-lg border border-gray-300 px-1 py-1 t-sm outline-none focus:border-indigo-500"
              value={category}
              onChange={(e) => {
                setCategory(e.target.value)
                setPage(0)
                setSelectedId(null)
              }}
              title="按 AI 分类筛选"
            >
              <option value="">全部分类</option>
              {Object.entries(categoryMeta).map(([key, meta]) => (
                <option key={key} value={key}>
                  {meta.label}
                </option>
              ))}
            </select>
          </div>

          {/* 批量操作栏：勾选后浮现 */}
          {selectedIds.length > 0 && (
            <div className="flex flex-wrap items-center gap-1 rounded-lg border border-indigo-200 bg-indigo-50/70 px-2 py-1.5">
              <span className="t-sm font-medium text-indigo-700">已选 {selectedIds.length} 封</span>
              <span className="flex-1" />
              <button className={batchBtn} onClick={() => runBatch('read')} disabled={batchBusy}>已读</button>
              <button className={batchBtn} onClick={() => runBatch('unread')} disabled={batchBusy}>未读</button>
              <button className={batchBtn} onClick={() => runBatch('star')} disabled={batchBusy}>星标</button>
              <button className={batchBtn} onClick={() => runBatch('archive')} disabled={batchBusy}>归档</button>
              {accountId != null && (
                <select
                  className="rounded-md border border-gray-300 bg-white px-1.5 py-1 t-sm text-gray-600 outline-none focus:border-indigo-400 disabled:opacity-50"
                  value=""
                  onChange={(e) => e.target.value && runBatch('move', e.target.value)}
                  disabled={batchBusy}
                  title="移动到文件夹"
                >
                  <option value="">移动到…</option>
                  {folders.map((f) => (
                    <option key={f.name} value={f.name}>
                      {f.name}
                    </option>
                  ))}
                </select>
              )}
              <button
                className={`${batchBtn} hover:text-red-600`}
                onClick={() => runBatch('trash')}
                disabled={batchBusy}
              >
                删除
              </button>
              <button className={batchBtn} onClick={() => setSelectedIds([])} disabled={batchBusy}>
                取消
              </button>
              {batchMutation.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin text-indigo-500" />}
            </div>
          )}
          <div className="flex items-center justify-between px-0.5 t-xs text-gray-400">
            <label className="flex items-center gap-1.5">
              <input
                type="checkbox"
                className="accent-indigo-600"
                checked={allSelected}
                onChange={toggleAll}
                title="全选本页"
              />
              全选本页
            </label>
            <span>
              {q ? `搜索「${q}」` : folder !== 'INBOX' ? folder : '收件箱'} · 共 {total} 封
            </span>
            {syncMessage && <span className="text-indigo-500">{syncMessage}</span>}
            <JobProgressBar job={organizeJob} label="AI 整理" />
            <JobProgressBar job={batchJob} label="批量操作" />
          </div>
        </div>

        <div className="flex-1 overflow-y-auto overflow-x-hidden">
          {listQuery.isLoading && <div className="p-6 t-sm text-gray-400">加载中…</div>}
          {!listQuery.isLoading && items.length === 0 && (
            <div className="p-8 text-center t-sm text-gray-400">此视图暂无邮件</div>
          )}
          {items.map((item) => (
            <div
              key={item.id}
              data-email-id={item.id}
              draggable
              onDragStart={(e) => {
                const ids = selectedIds.includes(item.id) ? selectedIds : [item.id]
                e.dataTransfer.setData(
                  'application/x-nmail-ids',
                  JSON.stringify({ accountId, ids }),
                )
                e.dataTransfer.effectAllowed = 'move'
              }}
              onContextMenu={(e) => {
                e.preventDefault()
                setRowMenu({ x: e.clientX, y: e.clientY, item })
              }}
              onClick={() => selectEmail(item)}
              className={`block w-full cursor-pointer border-b border-l-2 border-gray-50 px-3 py-1 text-left transition-colors hover:bg-gray-50 ${
                selectedId === item.id
                  ? 'border-l-indigo-500 bg-indigo-50'
                  : item.is_read
                    ? 'border-l-transparent'
                    : 'border-l-indigo-400 bg-blue-50/40'
              }`}
            >
              <div className="flex items-center gap-1.5">
                <input
                  type="checkbox"
                  className="shrink-0 accent-indigo-600"
                  checked={selectedIds.includes(item.id)}
                  onClick={(e) => e.stopPropagation()}
                  onChange={() => toggleRow(item.id)}
                />
                <span
                  className="h-1.5 w-1.5 shrink-0 rounded-full"
                  style={{ backgroundColor: item.account_color }}
                  title={item.account_email}
                />
                <span className={`w-32 shrink-0 truncate t-sm ${item.is_read ? 'text-gray-600' : 'font-semibold text-gray-900'}`}>
                  {item.sender_name || item.sender_email}
                </span>
                <span className={`min-w-0 flex-1 truncate t-sm ${item.is_read ? 'text-gray-700' : 'font-medium text-gray-900'}`}>
                  {item.subject || '（无主题）'}
                  <span className="ml-1.5 font-normal text-gray-400">{item.snippet}</span>
                </span>
                {item.category && categoryMeta[item.category] && (
                  <span
                    className={`shrink-0 rounded px-1 py-0.5 t-xs font-medium ${categoryMeta[item.category].cls}`}
                  >
                    {categoryMeta[item.category].label}
                  </span>
                )}
                {item.has_attachments && <Paperclip className="h-3 w-3 shrink-0 text-gray-400" />}
                {item.starred && <Star className="h-3 w-3 shrink-0 fill-amber-400 text-amber-400" />}
                <span className="w-11 shrink-0 text-right t-xs text-gray-400">
                  {shortDate(item.date)}
                </span>
              </div>
            </div>
          ))}
          {items.length < total && (
            <div className="flex items-center justify-center gap-3 p-3">
              <button
                className="inline-flex items-center gap-1 rounded-lg border border-gray-200 px-3 py-1.5 t-sm text-gray-600 hover:bg-gray-50 disabled:opacity-40"
                onClick={() => setPage((p) => Math.max(0, p - 1))}
                disabled={page === 0 || listQuery.isFetching}
              >
                <ChevronLeft className="h-3 w-3" /> 上一页
              </button>
              <span className="t-sm text-gray-400">
                {page + 1} / {Math.ceil(total / PAGE_SIZE)}
              </span>
              <button
                className="inline-flex items-center gap-1 rounded-lg border border-gray-200 px-3 py-1.5 t-sm text-gray-600 hover:bg-gray-50 disabled:opacity-40"
                onClick={() => setPage((p) => p + 1)}
                disabled={(page + 1) * PAGE_SIZE >= total || listQuery.isFetching}
              >
                下一页 <ChevronRight className="h-3 w-3" />
              </button>
            </div>
          )}
        </div>
      </section>
      {/* 拖拽分隔条：悬停高亮，双击复位 */}
      <SplitDivider
        onMove={moveListWidth}
        onReset={resetListWidth}
        onDragEnd={persistListWidth}
        title="拖拽调整列表宽度（双击复位）"
      />
      </>
      )}

      {/* 阅读区（分屏右栏；全屏模式占满） */}
      <section className="min-w-0 flex-1 bg-gray-50">
        {selectedId != null ? (
          detail ? (
            <EmailReader
              detail={detail}
              archived={false}
              actionBusy={actionBusy}
              onAction={(action, dest) =>
                actionMutation.mutate({ id: detail.id, action, folder: dest })
              }
              onCompose={openCompose}
              onShowImages={() => setShowImages(true)}
              full={readerFull}
              onToggleFull={toggleFull}
              onClose={() => setSelectedId(null)}
            />
          ) : (
            <div className="flex h-full items-center justify-center">
              <Loader2 className="h-5 w-5 animate-spin text-gray-300" />
            </div>
          )
        ) : (
          <div className="flex h-full items-center justify-center t-sm text-gray-300">
            选择一封邮件阅读
          </div>
        )}
      </section>
      </div>
      {/* 邮件行右键菜单（§4.3；系统右键已在应用层屏蔽） */}
      {rowMenu && (() => {
        const item = rowMenu.item
        const multi = selectedIds.includes(item.id) && selectedIds.length > 1
        const runSingle = (action: string) => actionMutation.mutate({ id: item.id, action })
        const runBatch = (action: string) => batchMutation.mutate({ action })
        const addList = (type: 'whitelist' | 'blacklist', label: string) => {
          void api.addSenderList(item.sender_email, type).then(() => {
            setSyncMessage(`${label}成功：${item.sender_email}`)
            invalidateMail()
          }).catch((err: Error) => setSyncMessage(`${label}失败：${err.message}`))
        }
        // 「移动到…」二级菜单（§4.3）：列该邮件所属账号的文件夹，排除其当前所在
        const moveTargets = (moveFoldersQuery.data?.folders ?? [])
          .filter((f) => f.name !== item.folder)
          .map((f) => ({
            label: f.name,
            onSelect: () => (multi
              ? batchMutation.mutate({ action: 'move', folder: f.name })
              : actionMutation.mutate({ id: item.id, action: 'move', folder: f.name })),
          }))
        const items: ContextMenuItem[] = [
          { label: '打开', onSelect: () => selectEmail(item) },
          { label: item.is_read ? '标为未读' : '标为已读',
            onSelect: () => (multi ? runBatch(item.is_read ? 'unread' : 'read') : runSingle(item.is_read ? 'unread' : 'read')) },
          { label: item.starred ? '取消星标' : '加星标',
            onSelect: () => (multi ? runBatch(item.starred ? 'unstar' : 'star') : runSingle(item.starred ? 'unstar' : 'star')) },
          { label: '移动到…', children: moveTargets },
          { label: '归档', onSelect: () => (multi ? runBatch('archive') : runSingle('archive')) },
          { label: '删除', danger: true, onSelect: () => (multi ? runBatch('trash') : runSingle('trash')) },
          { label: `发件人加入白名单`, onSelect: () => addList('whitelist', '加入白名单') },
          { label: `发件人加入黑名单`, onSelect: () => addList('blacklist', '加入黑名单') },
        ]
        return <ContextMenu x={rowMenu.x} y={rowMenu.y} items={items} onClose={() => setRowMenu(null)} />
      })()}
    </div>
  )
}
