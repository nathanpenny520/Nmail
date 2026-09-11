import { useQuery, useQueryClient } from '@tanstack/react-query'
import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../../api/client'
import type { EmailDetail, UserDraft } from '../../types'
import { buildComposeInit } from './quote'

export interface ComposeTab {
  draftId: number
  mode: string
  title: string
  dirty: boolean
}

interface ComposeContextValue {
  tabs: ComposeTab[]
  activeId: number | null
  /** 各标签对应的草稿数据（新建/恢复时缓存，表单初始化用） */
  drafts: Record<number, UserDraft>
  openNew: () => Promise<void>
  openReply: (mode: 'reply' | 'replyAll' | 'forward', base: EmailDetail) => Promise<void>
  setActive: (draftId: number) => void
  updateTab: (draftId: number, patch: Partial<ComposeTab>) => void
  /** 关闭标签：有未保存改动时先弹确认，否则直接关闭（草稿已自动保存，保留在服务端） */
  requestClose: (draftId: number) => void
  /** 关闭确认弹窗里的草稿 id；null 表示无待确认 */
  pendingCloseId: number | null
  /** confirmed=true 丢弃草稿；false 保留草稿仅关标签 */
  settleClose: (draftId: number, discard: boolean) => Promise<void>
  /** 发送完成：移除标签、刷新邮件列表 */
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

/**
 * 写信工作台状态中枢：挂在 Layout 之外（App 级），在收件箱与写信页之间
 * 来回切换不丢标签。草稿本身实时落库（user_drafts），刷新页面后自动恢复。
 */
export function ComposeProvider({ children }: { children: ReactNode }) {
  const [tabs, setTabs] = useState<ComposeTab[]>([])
  const [activeId, setActiveId] = useState<number | null>(null)
  const [drafts, setDrafts] = useState<Record<number, UserDraft>>({})
  const [pendingCloseId, setPendingCloseId] = useState<number | null>(null)
  const restoredRef = useRef(false)
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const accountsQuery = useQuery({ queryKey: ['accounts'], queryFn: api.getAccounts })
  const accountsRef = useRef(accountsQuery.data?.accounts ?? [])
  accountsRef.current = accountsQuery.data?.accounts ?? []

  // 应用启动恢复：服务端仍处于 editing 的草稿即未关完的标签
  useEffect(() => {
    if (restoredRef.current) return
    restoredRef.current = true
    api
      .getUserDrafts('editing')
      .then(({ drafts: list }) => {
        setDrafts((prev) => {
          const next = { ...prev }
          for (const d of list) next[d.id] = d
          return next
        })
        setTabs(list.map((d) => ({ draftId: d.id, mode: d.mode, title: tabTitle(d), dirty: false })))
      })
      .catch(() => {}) // 恢复失败不打断应用启动
  }, [])

  const addTab = useCallback(
    (draft: UserDraft) => {
      setDrafts((prev) => ({ ...prev, [draft.id]: draft }))
      setTabs((prev) => [...prev, { draftId: draft.id, mode: draft.mode, title: tabTitle(draft), dirty: false }])
      setActiveId(draft.id)
      navigate('/compose')
    },
    [navigate],
  )

  // 防连点：创建请求在途时忽略再次点击
  const creatingRef = useRef(false)

  const openNew = useCallback(async () => {
    const account = accountsRef.current[0]
    if (!account || creatingRef.current) return
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

  const tabsRef = useRef(tabs)
  tabsRef.current = tabs

  const removeTab = useCallback((draftId: number) => {
    const idx = tabsRef.current.findIndex((t) => t.draftId === draftId)
    const next = tabsRef.current.filter((t) => t.draftId !== draftId)
    setTabs(next)
    setActiveId((cur) =>
      cur === draftId ? (next[Math.min(idx, next.length - 1)]?.draftId ?? null) : cur,
    )
    setPendingCloseId(null)
  }, [])

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
      if (discard) {
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
      const wasLast = tabsRef.current.length <= 1
      removeTab(draftId)
      void queryClient.invalidateQueries({ queryKey: ['emails'] })
      void queryClient.invalidateQueries({ queryKey: ['folders'] })
      // 最后一个标签发完 → 回收件箱
      if (wasLast) navigate('/')
    },
    [removeTab, queryClient, navigate],
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
    activeId,
    drafts,
    openNew,
    openReply,
    setActive: setActiveId,
    updateTab,
    requestClose,
    pendingCloseId,
    settleClose,
    finishSent,
  }
  return <ComposeContext.Provider value={value}>{children}</ComposeContext.Provider>
}
