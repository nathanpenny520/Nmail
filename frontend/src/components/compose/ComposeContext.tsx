import { useQuery, useQueryClient } from '@tanstack/react-query'
import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { api } from '../../api/client'
import type { Account, EmailDetail, UserDraft } from '../../types'
import { buildComposeInit } from './quote'

export interface ComposeTab {
  draftId: number
  mode: string
  title: string
  dirty: boolean
}

interface ComposeContextValue {
  tabs: ComposeTab[]
  /** 各标签对应的草稿数据（新建/恢复时缓存，表单初始化用） */
  drafts: Record<number, UserDraft>
  accounts: Account[]
  /** 当前激活的写信标签 id；null = 显示底层页面（收件箱等） */
  activeComposeId: number | null
  setActiveCompose: (id: number | null) => void
  openNew: () => Promise<void>
  openReply: (mode: 'reply' | 'replyAll' | 'forward', base: EmailDetail) => Promise<void>
  /** 从草稿箱打开已存草稿：已在工作台则仅激活标签 */
  openDraft: (draft: UserDraft) => void
  updateTab: (draftId: number, patch: Partial<ComposeTab>) => void
  /** 表单拿到服务端最新草稿（附件/定时状态变化）后回写缓存 */
  cacheDraft: (draft: UserDraft) => void
  /** 自动保存成功后同步字段到缓存，保证 openNew 复用/settleClose 判断基于最新内容 */
  patchDraft: (draftId: number, patch: Partial<UserDraft>) => void
  /** 表单挂载时登记 flush（立即保存）入口，关闭决策前先冲掉防抖窗口里的未保存内容 */
  registerFlush: (draftId: number, fn: (() => Promise<void>) | null) => void
  /** 关闭标签：有未保存改动时先弹确认，否则直接关闭（草稿已自动保存，保留在服务端） */
  requestClose: (draftId: number) => void
  /** 关闭确认弹窗里的草稿 id；null 表示无待确认 */
  pendingCloseId: number | null
  /** confirmed=true 丢弃草稿；false 保留草稿仅关标签 */
  settleClose: (draftId: number, discard: boolean) => Promise<void>
  /** 发送/定时完成：移除标签、刷新邮件列表 */
  finishSent: (draftId: number) => void
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

/** 空白草稿：各字段与正文（剥标签后）全空。空稿不值得保留，见 restore/openNew/settleClose。 */
export function isDraftEmpty(d: UserDraft): boolean {
  const text = d.body_html
    .replace(/<[^>]*>/g, ' ')
    .replace(/&nbsp;/g, ' ')
    .trim()
  return (
    !d.to_addrs.trim() && !d.cc_addrs.trim() && !d.bcc_addrs.trim() && !d.subject.trim() && !text
  )
}

/**
 * 写信工作台状态中枢（挂 App 级）。写信不走路由：打开标签只是在
 * Layout 主区上方盖一层工作台，收件箱等页面保持挂载（keep-alive），
 * 标签条一键互切。草稿实时落库（user_drafts），刷新后自动恢复标签。
 */
export function ComposeProvider({ children }: { children: ReactNode }) {
  const [tabs, setTabs] = useState<ComposeTab[]>([])
  const [activeComposeId, setActiveCompose] = useState<number | null>(null)
  const [drafts, setDrafts] = useState<Record<number, UserDraft>>({})
  const [pendingCloseId, setPendingCloseId] = useState<number | null>(null)
  const restoredRef = useRef(false)
  const queryClient = useQueryClient()

  const accountsQuery = useQuery({ queryKey: ['accounts'], queryFn: api.getAccounts })
  const accounts = accountsQuery.data?.accounts ?? []
  const accountsRef = useRef(accounts)
  accountsRef.current = accounts

  // 应用启动恢复：editing/scheduled 的草稿即未关完的标签；
  // 空白草稿（点了写信没写任何内容）不恢复并顺手清掉，避免刷新后攒一排「新邮件」
  useEffect(() => {
    if (restoredRef.current) return
    restoredRef.current = true
    Promise.all([api.getUserDrafts('editing'), api.getUserDrafts('scheduled')])
      .then(([editing, scheduled]) => {
        const junk = editing.drafts.filter(isDraftEmpty)
        const keep = editing.drafts.filter((d) => !isDraftEmpty(d))
        for (const d of junk) void api.deleteUserDraft(d.id).catch(() => {})
        const list = [...scheduled.drafts, ...keep]
        setDrafts((prev) => {
          const next = { ...prev }
          for (const d of list) next[d.id] = d
          return next
        })
        setTabs(list.map((d) => ({ draftId: d.id, mode: d.mode, title: tabTitle(d), dirty: false })))
      })
      .catch(() => {}) // 恢复失败不打断应用启动
  }, [])

  const addTab = useCallback((draft: UserDraft) => {
    setDrafts((prev) => ({ ...prev, [draft.id]: draft }))
    setTabs((prev) => [...prev, { draftId: draft.id, mode: draft.mode, title: tabTitle(draft), dirty: false }])
    setActiveCompose(draft.id)
  }, [])

  // 防连点：创建请求在途时忽略再次点击
  const creatingRef = useRef(false)
  const draftsRef = useRef(drafts)
  draftsRef.current = drafts

  const openNew = useCallback(async () => {
    const account = accountsRef.current[0]
    if (!account || creatingRef.current) return
    // 已有空白草稿标签（点了写信还没写）→ 直接复用，避免连点攒出一排空标签
    const emptyTab = tabsRef.current.find((t) => {
      const d = draftsRef.current[t.draftId]
      return d ? isDraftEmpty(d) : false
    })
    if (emptyTab) {
      setActiveCompose(emptyTab.draftId)
      return
    }
    creatingRef.current = true
    try {
      const { draft } = await api.createUserDraft({ account_id: account.id, mode: 'new' })
      addTab(draft)
    } finally {
      creatingRef.current = false
    }
  }, [addTab])

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

  const updateTab = useCallback((draftId: number, patch: Partial<ComposeTab>) => {
    setTabs((prev) => prev.map((t) => (t.draftId === draftId ? { ...t, ...patch } : t)))
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

  const flushMapRef = useRef<Map<number, () => Promise<void>>>(new Map())
  const registerFlush = useCallback((draftId: number, fn: (() => Promise<void>) | null) => {
    if (fn) flushMapRef.current.set(draftId, fn)
    else flushMapRef.current.delete(draftId)
  }, [])

  const openDraft = useCallback(
    (draft: UserDraft) => {
      setDrafts((prev) => ({ ...prev, [draft.id]: draft }))
      setTabs((prev) =>
        prev.some((t) => t.draftId === draft.id)
          ? prev
          : [...prev, { draftId: draft.id, mode: draft.mode, title: tabTitle(draft), dirty: false }],
      )
      setActiveCompose(draft.id)
    },
    [],
  )

  const tabsRef = useRef(tabs)
  tabsRef.current = tabs

  const removeTab = useCallback((draftId: number) => {
    const idx = tabsRef.current.findIndex((t) => t.draftId === draftId)
    const next = tabsRef.current.filter((t) => t.draftId !== draftId)
    setTabs(next)
    setActiveCompose((cur) =>
      cur === draftId ? (next[Math.min(idx, next.length - 1)]?.draftId ?? null) : cur,
    )
    setPendingCloseId(null)
    // 草稿箱列表同步失效（标签关闭/发送后状态可能变化）
    void queryClient.invalidateQueries({ queryKey: ['user-drafts'] })
  }, [queryClient])

  const requestClose = useCallback(
    (draftId: number) => {
      // 读 tabsRef 而非闭包：存草稿按钮保存完成后立刻关闭时，状态刚更新
      const tab = tabsRef.current.find((t) => t.draftId === draftId)
      if (tab?.dirty) setPendingCloseId(draftId)
      else removeTab(draftId)
    },
    [removeTab],
  )

  const settleClose = useCallback(
    async (draftId: number, discard: boolean) => {
      // 先冲掉防抖窗口内未保存的内容，再以服务端最新内容为准判断是否空稿
      // （空稿「保留」没有意义，草稿箱里只会多一行空白，按丢弃处理）
      await flushMapRef.current.get(draftId)?.().catch(() => {})
      let isEmpty = false
      if (!discard) {
        try {
          const { draft } = await api.getUserDraft(draftId)
          isEmpty = isDraftEmpty(draft)
        } catch {
          // 草稿已不存在（他处删除），关标签即可
        }
      }
      if (discard || isEmpty) {
        try {
          await api.deleteUserDraft(draftId)
        } catch {
          // 草稿可能已被其他入口删除；照常关标签
        }
      }
      removeTab(draftId)
    },
    [removeTab],
  )

  const finishSent = useCallback(
    (draftId: number) => {
      removeTab(draftId)
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
    activeComposeId,
    setActiveCompose,
    openNew,
    openReply,
    openDraft,
    updateTab,
    cacheDraft,
    patchDraft,
    registerFlush,
    requestClose,
    pendingCloseId,
    settleClose,
    finishSent,
  }
  return <ComposeContext.Provider value={value}>{children}</ComposeContext.Provider>
}
