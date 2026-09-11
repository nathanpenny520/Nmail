import { useQuery, useQueryClient } from '@tanstack/react-query'
import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { api } from '../../api/client'
import type { Account, EmailDetail, UserDraft } from '../../types'
import { buildComposeInit } from './quote'

export interface ComposeTab {
  /** 标签稳定标识：懒持久化创建真实草稿后 tabId 不变、仅换绑 draftId，表单不重挂 */
  tabId: string
  draftId: number
  mode: string
  title: string
  dirty: boolean
  /** 尚未落库的空白新邮件：点写信即开，首次编辑/显式保存才创建记录 */
  ephemeral: boolean
}

interface ComposeContextValue {
  tabs: ComposeTab[]
  /** 各标签对应的草稿数据（新建/恢复时缓存，表单初始化用） */
  drafts: Record<number, UserDraft>
  accounts: Account[]
  /** 当前激活写信标签的 tabId；null = 显示底层页面（收件箱等） */
  activeTabId: string | null
  setActiveTab: (tabId: string | null) => void
  openNew: () => void
  openReply: (mode: 'reply' | 'replyAll' | 'forward', base: EmailDetail) => Promise<void>
  /** 从草稿箱打开已存草稿：已在工作台则仅激活标签 */
  openDraft: (draft: UserDraft) => void
  updateTab: (tabId: string, patch: Partial<Omit<ComposeTab, 'tabId'>>) => void
  /** 表单拿到服务端最新草稿（附件/定时状态变化）后回写缓存 */
  cacheDraft: (draft: UserDraft) => void
  /** 自动保存成功后同步字段到缓存，保证空稿判断等基于最新内容 */
  patchDraft: (draftId: number, patch: Partial<UserDraft>) => void
  /** 表单挂载时登记 flush（立即保存）入口，关闭决策前先冲掉防抖窗口里的未保存内容 */
  registerFlush: (tabId: string, fn: (() => Promise<void>) | null) => void
  /** 懒持久化完成：临时 id 换绑真实草稿（tabId 不变，表单无感） */
  onEphemeralPersisted: (tempId: number, real: UserDraft) => void
  /** 关闭标签：有未保存改动时先弹确认，否则直接关闭（草稿已自动保存，保留在服务端） */
  requestClose: (tabId: string) => void
  /** 关闭确认弹窗里的标签 id；null 表示无待确认 */
  pendingCloseTabId: string | null
  /** confirmed=true 丢弃草稿；false 保留草稿仅关标签 */
  settleClose: (tabId: string, discard: boolean) => Promise<void>
  /** 发送完成：移除标签、刷新邮件列表 */
  finishSent: (tabId: string) => void
}

const ComposeContext = createContext<ComposeContextValue | null>(null)

export function useCompose(): ComposeContextValue {
  const ctx = useContext(ComposeContext)
  if (!ctx) throw new Error('useCompose 必须在 ComposeProvider 内使用')
  return ctx
}

function tabTitle(d: Pick<UserDraft, 'subject' | 'to_addrs'>): string {
  return d.subject.trim() || d.to_addrs.split(',')[0]?.trim() || '新邮件'
}

/** 空白草稿：各字段与正文（剥标签后）全空。仅用于关闭决策——用户显式保存的空稿是合法数据。 */
export function isDraftEmpty(d: UserDraft): boolean {
  const text = d.body_html
    .replace(/<[^>]*>/g, ' ')
    .replace(/&nbsp;/g, ' ')
    .trim()
  return (
    !d.to_addrs.trim() && !d.cc_addrs.trim() && !d.bcc_addrs.trim() && !d.subject.trim() && !text
  )
}

function newTabId(): string {
  return `t-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`
}

/**
 * 写信工作台状态中枢（挂 App 级）。写信不走路由：打开标签只是在
 * Layout 主区上方盖一层工作台，收件箱等页面保持挂载（keep-alive）。
 * 草稿懒持久化：「写信」只开本地空白标签，首次编辑/显式保存才落库——
 * 随手点开的空标签不污染数据库，用户主动存的空稿则合法保留。
 */
export function ComposeProvider({ children }: { children: ReactNode }) {
  const [tabs, setTabs] = useState<ComposeTab[]>([])
  const [activeTabId, setActiveTab] = useState<string | null>(null)
  const [drafts, setDrafts] = useState<Record<number, UserDraft>>({})
  const [pendingCloseTabId, setPendingCloseTabId] = useState<string | null>(null)
  const restoredRef = useRef(false)
  const queryClient = useQueryClient()

  const accountsQuery = useQuery({ queryKey: ['accounts'], queryFn: api.getAccounts })
  const accounts = accountsQuery.data?.accounts ?? []
  const accountsRef = useRef(accounts)
  accountsRef.current = accounts

  // 应用启动恢复：editing/scheduled 的草稿都是未关完的标签（含用户显式保存的空稿）
  useEffect(() => {
    if (restoredRef.current) return
    restoredRef.current = true
    Promise.all([api.getUserDrafts('editing'), api.getUserDrafts('scheduled')])
      .then(([editing, scheduled]) => {
        const list = [...scheduled.drafts, ...editing.drafts]
        setDrafts((prev) => {
          const next = { ...prev }
          for (const d of list) next[d.id] = d
          return next
        })
        setTabs(
          list.map((d) => ({
            tabId: newTabId(),
            draftId: d.id,
            mode: d.mode,
            title: tabTitle(d),
            dirty: false,
            ephemeral: false,
          })),
        )
      })
      .catch(() => {}) // 恢复失败不打断应用启动
  }, [])

  const addTab = useCallback((draft: UserDraft, ephemeral = false) => {
    const tabId = newTabId()
    setDrafts((prev) => ({ ...prev, [draft.id]: draft }))
    setTabs((prev) => [
      ...prev,
      { tabId, draftId: draft.id, mode: draft.mode, title: tabTitle(draft), dirty: false, ephemeral },
    ])
    setActiveTab(tabId)
  }, [])

  const openNew = useCallback(() => {
    const account = accountsRef.current[0]
    if (!account) return
    // 已有未落库的空白标签 → 直接复用，避免连点攒一排「新邮件」
    const existing = tabsRef.current.find((t) => t.ephemeral)
    if (existing) {
      setActiveTab(existing.tabId)
      return
    }
    const temp: UserDraft = {
      id: -Date.now(),
      account_id: account.id,
      mode: 'new',
      in_reply_to: null,
      to_addrs: '',
      cc_addrs: '',
      bcc_addrs: '',
      subject: '',
      body_html: '',
      status: 'editing',
      send_at: null,
      attachments: [],
      created_at: '',
      updated_at: '',
    }
    addTab(temp, true)
  }, [addTab])

  // 防连点：创建请求在途时忽略再次点击
  const creatingRef = useRef(false)

  const openReply = useCallback(
    async (mode: 'reply' | 'replyAll' | 'forward', base: EmailDetail) => {
      const account = accountsRef.current.find((a) => a.id === base.account_id) ?? accountsRef.current[0]
      if (!account || creatingRef.current) return
      creatingRef.current = true
      try {
        const prefill = buildComposeInit(mode, base)
        const { draft } = await api.createUserDraft({
          account_id: account.id,
          mode,
          in_reply_to: base.id,
          ...prefill,
        })
        addTab(draft)
      } finally {
        creatingRef.current = false
      }
    },
    [addTab],
  )

  const updateTab = useCallback((tabId: string, patch: Partial<Omit<ComposeTab, 'tabId'>>) => {
    setTabs((prev) => prev.map((t) => (t.tabId === tabId ? { ...t, ...patch } : t)))
  }, [])

  const cacheDraft = useCallback((draft: UserDraft) => {
    setDrafts((prev) => ({ ...prev, [draft.id]: draft }))
  }, [])

  const patchDraft = useCallback((draftId: number, patch: Partial<UserDraft>) => {
    setDrafts((prev) => {
      const cur = prev[draftId]
      if (!cur) return prev
      return { ...prev, [draftId]: { ...cur, ...patch } }
    })
  }, [])

  const flushMapRef = useRef<Map<string, () => Promise<void>>>(new Map())
  const registerFlush = useCallback((tabId: string, fn: (() => Promise<void>) | null) => {
    if (fn) flushMapRef.current.set(tabId, fn)
    else flushMapRef.current.delete(tabId)
  }, [])

  const onEphemeralPersisted = useCallback((tempId: number, real: UserDraft) => {
    setDrafts((prev) => {
      if (!(tempId in prev)) return prev
      const next = { ...prev }
      delete next[tempId]
      next[real.id] = real
      return next
    })
    // tabId 不变只换绑 draftId：激活态与挂载中的表单均无需变动
    setTabs((prev) => prev.map((t) => (t.draftId === tempId ? { ...t, draftId: real.id, ephemeral: false } : t)))
  }, [])

  const openDraft = useCallback((draft: UserDraft) => {
    setDrafts((prev) => ({ ...prev, [draft.id]: draft }))
    const existing = tabsRef.current.find((t) => t.draftId === draft.id)
    if (existing) {
      setActiveTab(existing.tabId)
      return
    }
    const tabId = newTabId()
    setTabs((prev) => [
      ...prev,
      { tabId, draftId: draft.id, mode: draft.mode, title: tabTitle(draft), dirty: false, ephemeral: false },
    ])
    setActiveTab(tabId)
  }, [])

  const tabsRef = useRef(tabs)
  tabsRef.current = tabs

  const removeTab = useCallback(
    (tabId: string) => {
      const idx = tabsRef.current.findIndex((t) => t.tabId === tabId)
      const next = tabsRef.current.filter((t) => t.tabId !== tabId)
      setTabs(next)
      setActiveTab((cur) => (cur === tabId ? (next[Math.min(idx, next.length - 1)]?.tabId ?? null) : cur))
      setPendingCloseTabId(null)
      // 草稿箱列表同步失效（标签关闭/发送后状态可能变化）
      void queryClient.invalidateQueries({ queryKey: ['user-drafts'] })
    },
    [queryClient],
  )

  const requestClose = useCallback(
    (tabId: string) => {
      // 读 tabsRef 而非闭包：存草稿按钮保存完成后立刻关闭时，状态刚更新
      const tab = tabsRef.current.find((t) => t.tabId === tabId)
      if (tab?.dirty) setPendingCloseTabId(tabId)
      else removeTab(tabId)
    },
    [removeTab],
  )

  const settleClose = useCallback(
    async (tabId: string, discard: boolean) => {
      // 保留路径：先冲掉防抖窗口内未保存的内容（空白新邮件此时尚未落库，flush 即创建），
      // 再以服务端最新内容判空——空稿「保留」仍保留（用户显式行为），此处仅放弃无主数据
      if (!discard) await flushMapRef.current.get(tabId)?.().catch(() => {})
      const tab = tabsRef.current.find((t) => t.tabId === tabId)
      const draftId = tab?.draftId ?? 0
      if (draftId > 0) {
        if (discard) {
          try {
            await api.deleteUserDraft(draftId)
          } catch {
            // 草稿可能已被其他入口删除；照常关标签
          }
        }
      }
      removeTab(tabId)
    },
    [removeTab],
  )

  const finishSent = useCallback(
    (tabId: string) => {
      removeTab(tabId)
      void queryClient.invalidateQueries({ queryKey: ['emails'] })
      void queryClient.invalidateQueries({ queryKey: ['folders'] })
    },
    [removeTab, queryClient],
  )

  // 有未保存草稿时拦截页面刷新/关闭
  useEffect(() => {
    const handler = (e: BeforeUnloadEvent) => {
      if (tabs.some((t) => t.dirty)) {
        e.preventDefault()
        e.returnValue = ''
      }
    }
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [tabs])

  const value: ComposeContextValue = {
    tabs,
    drafts,
    accounts,
    activeTabId,
    setActiveTab,
    openNew,
    openReply,
    openDraft,
    updateTab,
    cacheDraft,
    patchDraft,
    registerFlush,
    onEphemeralPersisted,
    requestClose,
    pendingCloseTabId,
    settleClose,
    finishSent,
  }
  return <ComposeContext.Provider value={value}>{children}</ComposeContext.Provider>
}
