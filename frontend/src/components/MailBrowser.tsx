import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ChevronLeft, ChevronRight, Inbox, Loader2, Paperclip, Pencil, Plus, RefreshCw, Search, Sparkles, Star,
} from 'lucide-react'
import { useEffect, useRef, useState, type MouseEvent as ReactMouseEvent } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, type EmailQuery } from '../api/client'
import {
  CATEGORY_META, type EmailDetail, type EmailSummary, type FolderInfo, type SyncResult,
} from '../types'
import ComposeModal, { type ComposeInit } from './ComposeModal'
import EmailReader from './EmailReader'

const PAGE_SIZE = 50

const batchBtn =
  'rounded-md border border-indigo-200 bg-white px-1.5 py-0.5 t-sm text-gray-600 transition-colors hover:text-indigo-700 disabled:opacity-50'

export interface ComposeContext {
  mode: 'reply' | 'replyAll' | 'forward' | 'new'
  base?: EmailDetail | null
}

/**
 * 邮件浏览主界面（聚合收件箱 / 已归档 共用）。
 * archived=true 时列出本地归档邮件，操作栏提供"恢复到收件箱"。
 */
export default function MailBrowser({ archived }: { archived: boolean }) {
  const queryClient = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()

  const [accountId, setAccountId] = useState<number | null>(null)
  const [folder, setFolder] = useState('INBOX')
  const [q, setQ] = useState('')
  const [qInput, setQInput] = useState('')
  const [starredOnly, setStarredOnly] = useState(false)
  const [category, setCategory] = useState('')
  const [page, setPage] = useState(0)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [selectedIds, setSelectedIds] = useState<number[]>([])
  const [showImages, setShowImages] = useState(false)
  const [compose, setCompose] = useState<ComposeInit | null>(null)
  const [syncMessage, setSyncMessage] = useState<string | null>(null)

  // 分屏布局：列表宽度可拖拽，阅读区可全屏，均记忆在本地
  const [listWidth, setListWidth] = useState(() => {
    const saved = Number(localStorage.getItem('nmail_list_width'))
    return saved >= 240 && saved <= 640 ? saved : 340
  })
  const [readerFull, setReaderFull] = useState(() => localStorage.getItem('nmail_reader_full') === '1')
  const listRef = useRef<HTMLElement>(null)
  const dragging = useRef(false)
  const widthRef = useRef(listWidth)
  widthRef.current = listWidth

  const startDrag = (e: ReactMouseEvent) => {
    e.preventDefault()
    dragging.current = true
    document.body.classList.add('dragging-col')
  }

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!dragging.current || !listRef.current) return
      // 全局 zoom 会缩放视觉坐标，换算回布局 px
      const zoom = Number(getComputedStyle(document.documentElement).getPropertyValue('--app-zoom')) || 1
      const w = Math.min(640, Math.max(240, (e.clientX - listRef.current.getBoundingClientRect().left) / zoom))
      widthRef.current = w
      setListWidth(w)
    }
    const onUp = () => {
      if (!dragging.current) return
      dragging.current = false
      document.body.classList.remove('dragging-col')
      localStorage.setItem('nmail_list_width', String(widthRef.current))
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
    return () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
  }, [])

  const toggleFull = () => {
    setReaderFull((v) => {
      localStorage.setItem('nmail_reader_full', v ? '0' : '1')
      return !v
    })
  }

  const accountsQuery = useQuery({ queryKey: ['accounts'], queryFn: api.getAccounts })
  const accounts = accountsQuery.data?.accounts ?? []
  const hasAccounts = accounts.length > 0

  const foldersQuery = useQuery({
    queryKey: ['folders', accountId],
    queryFn: () => api.getFolders(accountId!),
    enabled: accountId != null && !archived && !q,
    staleTime: 5 * 60 * 1000,
  })
  const folders: FolderInfo[] = foldersQuery.data?.folders ?? []

  // 切换文件夹 = 按需同步该文件夹（后台轮询只拉 INBOX），同步完成列表自动刷新
  const [folderSyncing, setFolderSyncing] = useState(false)
  const syncFolderThenList = async (target: string) => {
    if (accountId == null) return
    setFolderSyncing(true)
    setSyncMessage(`正在同步文件夹 ${target}…`)
    try {
      await api.syncAccount(accountId, target)
    } catch (err) {
      setSyncMessage(`同步失败：${(err as Error).message}`)
      setTimeout(() => setSyncMessage(null), 6000)
    } finally {
      setFolderSyncing(false)
      invalidateMail()
    }
  }

  // 自建文件夹（VSCode 资源管理器式）
  const [creatingFolder, setCreatingFolder] = useState(false)
  const [newFolderName, setNewFolderName] = useState('')
  const createFolderMutation = useMutation({
    mutationFn: () => api.createFolder(accountId!, newFolderName.trim()),
    onSuccess: (result) => {
      void queryClient.invalidateQueries({ queryKey: ['folders', accountId] })
      setFolder(result.name)
      setPage(0)
      setSelectedId(null)
      setCreatingFolder(false)
      setNewFolderName('')
      void syncFolderThenList(result.name)
    },
    onError: (error: Error) => {
      setSyncMessage(`创建失败：${error.message}`)
      setTimeout(() => setSyncMessage(null), 6000)
    },
  })

  const listQueryKey = ['emails', { archived, accountId, folder, q, starredOnly, category, page }]
  const listQuery = useQuery({
    queryKey: listQueryKey,
    queryFn: () =>
      api.getEmails({
        archived,
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

  // 摘要页「查看」跳转：/?focus=<email_id> 直接打开对应邮件
  const focusId = searchParams.get('focus')
  useEffect(() => {
    if (focusId && !archived) {
      setSelectedId(Number(focusId))
      setShowImages(false)
      setSearchParams({}, { replace: true })
    }
  }, [focusId, archived, setSearchParams])

  const invalidateMail = () => {
    void queryClient.invalidateQueries({ queryKey: ['emails'] })
    void queryClient.invalidateQueries({ queryKey: ['email'] })
    void queryClient.invalidateQueries({ queryKey: ['notifications'] })
  }

  // 筛选/翻页变化时清空批量选择
  useEffect(() => {
    setSelectedIds([])
  }, [archived, accountId, folder, q, starredOnly, category, page])

  // 全文模式下 Esc 返回列表
  useEffect(() => {
    if (selectedId == null) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setSelectedId(null)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [selectedId])

  const actionMutation = useMutation({
    mutationFn: ({ id, action, folder: dest }: { id: number; action: string; folder?: string }) =>
      api.emailAction(id, action, dest),
    onSuccess: (_data, variables) => {
      invalidateMail()
      // 归档/删除/移动后当前邮件会离开当前视图，清除选中
      if (['archive', 'unarchive', 'trash', 'move'].includes(variables.action)) {
        if (archived ? variables.action === 'unarchive' : true) {
          setSelectedId(null)
        }
      }
    },
  })

  const syncMutation = useMutation({
    mutationFn: async (): Promise<SyncResult[]> => {
      if (accountId != null) return [await api.syncAccount(accountId)]
      const results: SyncResult[] = []
      for (const account of accounts) {
        results.push(await api.syncAccount(account.id))
      }
      return results
    },
    onSuccess: (results) => {
      invalidateMail()
      const newCount = results.reduce(
        (sum, r) => sum + (r.folders?.reduce((s, f) => s + f.new_count, 0) ?? 0), 0,
      )
      const failed = results.filter((r) => !r.ok)
      if (failed.length > 0) {
        setSyncMessage(`同步失败：${failed[0].error ?? '未知错误'}`)
      } else if (newCount > 0) {
        setSyncMessage(`同步完成，新邮件 ${newCount} 封`)
      } else {
        setSyncMessage('同步完成，暂无新邮件')
      }
      setTimeout(() => setSyncMessage(null), 5000)
    },
    onError: (error: Error) => setSyncMessage(`同步失败：${error.message}`),
  })

  const organizeMutation = useMutation({
    mutationFn: () => api.aiOrganize({ account_id: accountId ?? undefined, folder: 'INBOX', limit: 200 }),
    onSuccess: (result) => {
      invalidateMail()
      if (result.skipped_no_ai) {
        setSyncMessage('未配置 AI 端点，请到设置中填写')
      } else {
        setSyncMessage(
          `AI 整理完成：分类 ${result.classified} 封${result.archived > 0 ? `，归档营销 ${result.archived} 封` : ''}`,
        )
      }
      setTimeout(() => setSyncMessage(null), 6000)
    },
    onError: (error: Error) => {
      setSyncMessage(`AI 整理失败：${error.message}`)
      setTimeout(() => setSyncMessage(null), 6000)
    },
  })

  const selectEmail = (item: EmailSummary) => {
    setSelectedId(item.id)
    setShowImages(false)
    if (!item.is_read) {
      actionMutation.mutate({ id: item.id, action: 'read' })
    }
  }

  const openCompose = (mode: 'reply' | 'replyAll' | 'forward') => {
    if (!detail) return
    setCompose({ mode, base: detail })
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

  const batchMutation = useMutation({
    mutationFn: ({ action, folder: dest }: { action: string; folder?: string }) =>
      api.batchAction(selectedIds, action, dest),
    onSuccess: (result) => {
      invalidateMail()
      setSelectedIds([])
      const failedNote = result.failed > 0 ? `，${result.failed} 封失败` : ''
      setSyncMessage(`批量操作完成：${result.updated} 封${failedNote}`)
      setTimeout(() => setSyncMessage(null), 5000)
    },
    onError: (error: Error) => {
      setSyncMessage(`批量操作失败：${error.message}`)
      setTimeout(() => setSyncMessage(null), 6000)
    },
  })
  const runBatch = (action: string, folder?: string) =>
    batchMutation.mutate({ action, folder })

  // ── 空账号引导 ──
  if (!accountsQuery.isLoading && !hasAccounts) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="max-w-md rounded-2xl border border-gray-200 bg-white p-8 text-center shadow-sm">
          <Inbox className="mx-auto h-10 w-10 text-indigo-200" />
          <h2 className="mt-3 text-lg font-semibold">添加你的第一个邮箱</h2>
          <p className="mt-2 text-sm text-gray-500">
            Nmail 支持 QQ、163、Gmail、Outlook 等 19+ 服务商，填入邮箱和授权码即可。
          </p>
          <Link
            to="/settings"
            className="mt-4 inline-block rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700"
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
          {!archived && (
            <button
              className="inline-flex shrink-0 items-center whitespace-nowrap rounded-lg border border-violet-200 bg-violet-50 px-2.5 py-1.5 t-sm font-medium text-violet-700 hover:bg-violet-100 disabled:opacity-50"
              onClick={() => organizeMutation.mutate()}
              disabled={organizeMutation.isPending}
              title="让 AI 为收件箱中未分类的邮件补跑分类，营销邮件自动归档"
            >
              <Sparkles className={`mr-1 h-3.5 w-3.5 ${organizeMutation.isPending ? 'animate-pulse' : ''}`} />
              {organizeMutation.isPending ? '整理中…' : 'AI 整理'}
            </button>
          )}
          <button
            className="inline-flex shrink-0 items-center whitespace-nowrap rounded-lg border border-gray-300 px-2.5 py-1.5 t-sm font-medium text-gray-700 hover:bg-gray-50"
            onClick={() => setCompose({ mode: 'new' })}
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
            <select
              className="min-w-0 flex-1 rounded-lg border border-gray-300 px-1.5 py-1 t-sm outline-none focus:border-indigo-500"
              value={accountId ?? ''}
              onChange={(e) => {
                setAccountId(e.target.value ? Number(e.target.value) : null)
                setPage(0)
                setSelectedId(null)
              }}
            >
              <option value="">全部账号</option>
              {accounts.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.email}
                </option>
              ))}
            </select>
            {!archived && !q && accountId != null && (
              <>
                <select
                  className="min-w-0 flex-1 rounded-lg border border-gray-300 px-1.5 py-1 t-sm outline-none focus:border-indigo-500"
                  value={folder}
                  onChange={(e) => {
                    setFolder(e.target.value)
                    setPage(0)
                    setSelectedId(null)
                    void syncFolderThenList(e.target.value)
                  }}
                >
                  {folders.map((f) => (
                    <option key={f.name} value={f.name}>
                      {f.name}
                    </option>
                  ))}
                </select>
                <button
                  className="inline-flex shrink-0 items-center rounded-md border border-gray-300 p-1 t-sm text-gray-500 hover:border-indigo-400 hover:text-indigo-600"
                  title="在服务器上新建文件夹"
                  onClick={() => setCreatingFolder((v) => !v)}
                >
                  <Plus className="h-3 w-3" />
                </button>
              </>
            )}
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
              {Object.entries(CATEGORY_META).map(([key, meta]) => (
                <option key={key} value={key}>
                  {meta.label}
                </option>
              ))}
            </select>
          </div>
          {/* 新建文件夹输入行 */}
          {creatingFolder && accountId != null && (
            <div className="flex items-center gap-1.5">
              <input
                className="min-w-0 flex-1 rounded-lg border border-indigo-300 px-2 py-1 t-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100"
                placeholder="新文件夹名称，回车创建"
                value={newFolderName}
                onChange={(e) => setNewFolderName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && newFolderName.trim()) createFolderMutation.mutate()
                  if (e.key === 'Escape') setCreatingFolder(false)
                }}
                autoFocus
              />
              <button
                className="shrink-0 rounded-lg bg-indigo-600 px-2 py-1 t-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
                onClick={() => createFolderMutation.mutate()}
                disabled={!newFolderName.trim() || createFolderMutation.isPending}
              >
                {createFolderMutation.isPending ? '创建中…' : '创建'}
              </button>
              <button
                className="shrink-0 rounded-lg border border-gray-300 px-2 py-1 t-sm text-gray-500 hover:bg-gray-50"
                onClick={() => setCreatingFolder(false)}
              >
                取消
              </button>
            </div>
          )}

          {/* 批量操作栏：勾选后浮现 */}
          {selectedIds.length > 0 && (
            <div className="flex flex-wrap items-center gap-1 rounded-lg border border-indigo-200 bg-indigo-50/70 px-2 py-1.5">
              <span className="t-sm font-medium text-indigo-700">已选 {selectedIds.length} 封</span>
              <span className="flex-1" />
              <button className={batchBtn} onClick={() => runBatch('read')} disabled={batchMutation.isPending}>已读</button>
              <button className={batchBtn} onClick={() => runBatch('unread')} disabled={batchMutation.isPending}>未读</button>
              <button className={batchBtn} onClick={() => runBatch('star')} disabled={batchMutation.isPending}>星标</button>
              {!archived && (
                <button className={batchBtn} onClick={() => runBatch('archive')} disabled={batchMutation.isPending}>归档</button>
              )}
              {archived && (
                <button className={batchBtn} onClick={() => runBatch('unarchive')} disabled={batchMutation.isPending}>恢复</button>
              )}
              {accountId != null && (
                <select
                  className="rounded-md border border-gray-300 bg-white px-1.5 py-1 t-sm text-gray-600 outline-none focus:border-indigo-400 disabled:opacity-50"
                  value=""
                  onChange={(e) => e.target.value && runBatch('move', e.target.value)}
                  disabled={batchMutation.isPending}
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
                disabled={batchMutation.isPending}
              >
                删除
              </button>
              <button className={batchBtn} onClick={() => setSelectedIds([])} disabled={batchMutation.isPending}>
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
              {archived ? '已归档' : q ? `搜索「${q}」` : folder !== 'INBOX' ? folder : '收件箱'} · 共 {total} 封
              {folderSyncing && ' · 同步中…'}
            </span>
            {syncMessage && <span className="text-indigo-500">{syncMessage}</span>}
          </div>
        </div>

        <div className="flex-1 overflow-y-auto overflow-x-hidden">
          {listQuery.isLoading && <div className="p-6 t-sm text-gray-400">加载中…</div>}
          {!listQuery.isLoading && items.length === 0 && (
            <div className="p-8 text-center t-sm text-gray-400">
              {archived ? '还没有已归档的邮件' : '此视图暂无邮件'}
            </div>
          )}
          {items.map((item) => (
            <div
              key={item.id}
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
                {item.category && CATEGORY_META[item.category] && (
                  <span
                    className={`shrink-0 rounded px-1 py-0.5 t-xs font-medium ${CATEGORY_META[item.category].cls}`}
                  >
                    {CATEGORY_META[item.category].label}
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
                className="inline-flex items-center gap-1 rounded-lg border border-gray-200 px-3 py-1.5 text-xs text-gray-600 hover:bg-gray-50 disabled:opacity-40"
                onClick={() => setPage((p) => Math.max(0, p - 1))}
                disabled={page === 0 || listQuery.isFetching}
              >
                <ChevronLeft className="h-3 w-3" /> 上一页
              </button>
              <span className="text-xs text-gray-400">
                {page + 1} / {Math.ceil(total / PAGE_SIZE)}
              </span>
              <button
                className="inline-flex items-center gap-1 rounded-lg border border-gray-200 px-3 py-1.5 text-xs text-gray-600 hover:bg-gray-50 disabled:opacity-40"
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
      <div
        onMouseDown={startDrag}
        onDoubleClick={() => {
          setListWidth(340)
          localStorage.setItem('nmail_list_width', '340')
        }}
        className="relative w-px shrink-0 cursor-col-resize bg-gray-200 hover:bg-indigo-400"
        title="拖拽调整列表宽度（双击复位）"
      >
        <div className="absolute inset-y-0 -left-1.5 -right-1.5" />
      </div>
      </>
      )}

      {/* 阅读区（分屏右栏；全屏模式占满） */}
      <section className="min-w-0 flex-1 bg-gray-50">
        {selectedId != null ? (
          detail ? (
            <EmailReader
              detail={detail}
              archived={archived}
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

      {compose && (
        <ComposeModal
          accounts={accounts}
          init={compose}
          onClose={() => setCompose(null)}
          onSent={() => {
            setCompose(null)
            invalidateMail()
          }}
        />
      )}
    </div>
  )
}

function shortDate(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  const now = new Date()
  const sameDay = d.toDateString() === now.toDateString()
  if (sameDay) return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false })
  const sameYear = d.getFullYear() === now.getFullYear()
  return d.toLocaleDateString('zh-CN', {
    month: sameYear ? 'numeric' : undefined,
    day: 'numeric',
    year: sameYear ? undefined : 'numeric',
  })
}
