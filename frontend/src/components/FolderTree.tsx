import { useQuery } from '@tanstack/react-query'
import { Archive, ChevronDown, ChevronRight, FilePenLine, FileText, Inbox } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api } from '../api/client'
import { useAIEnabled } from '../api/useAI'
import type { Account } from '../types'

/** 邮件基座的树选中项（v0.4 P1 只读骨架：智能视图 + 账号收件箱；P2 扩展服务器文件夹节点）。 */
export type TreeSelection =
  | { type: 'inbox'; accountId: number | null }
  | { type: 'review' }
  | { type: 'mydrafts' }
  | { type: 'archived' }

function statusDotCls(status: Account['status']): string {
  switch (status) {
    case 'ok':
      return 'bg-emerald-500'
    case 'syncing':
      return 'animate-pulse bg-amber-400'
    case 'auth_error':
    case 'connection_error':
      return 'bg-red-500'
    default:
      return 'bg-gray-300'
  }
}

/** 文件夹树（VSCode 资源管理器式）：智能视图分区固定在顶部，账号可折叠、INBOX 子节点。 */
export default function FolderTree({
  selection,
  onSelect,
}: {
  selection: TreeSelection
  onSelect: (sel: TreeSelection) => void
}) {
  const accountsQuery = useQuery({ queryKey: ['accounts'], queryFn: api.getAccounts })
  const accounts: Account[] = accountsQuery.data?.accounts ?? []
  // 待审草稿是 AI 产物，AI 停用时隐藏（对齐旧导航 AI_ONLY_TABS 语义）
  const aiEnabled = useAIEnabled()

  // 账号折叠状态记忆在本地；选中某账号时自动确保展开
  const [expanded, setExpanded] = useState<number[]>(() => {
    try {
      const saved: unknown = JSON.parse(localStorage.getItem('nmail_tree_expanded') ?? '[]')
      return Array.isArray(saved) ? saved.filter((v): v is number => typeof v === 'number') : []
    } catch {
      return []
    }
  })
  useEffect(() => {
    localStorage.setItem('nmail_tree_expanded', JSON.stringify(expanded))
  }, [expanded])
  useEffect(() => {
    if (selection.type === 'inbox' && selection.accountId != null) {
      const id = selection.accountId
      setExpanded((prev) => (prev.includes(id) ? prev : [...prev, id]))
    }
  }, [selection])

  const toggleExpand = (id: number) =>
    setExpanded((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))

  const rowCls = (active: boolean) =>
    `flex w-full cursor-pointer items-center gap-1.5 rounded-md px-2 py-[5px] t-md text-left transition-colors ${
      active
        ? 'bg-indigo-50 font-medium text-indigo-700'
        : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
    }`
  const isInboxActive = (accountId: number | null) =>
    selection.type === 'inbox' && selection.accountId === accountId

  return (
    <aside className="flex w-48 shrink-0 flex-col overflow-y-auto border-r border-gray-200 bg-white px-1.5 py-2">
      <div className="px-2 pb-1 pt-1 t-xs font-medium text-gray-400">智能视图</div>
      <button className={rowCls(isInboxActive(null))} onClick={() => onSelect({ type: 'inbox', accountId: null })}>
        <Inbox className="h-3.5 w-3.5 shrink-0" />
        <span className="truncate">聚合收件箱</span>
      </button>
      {aiEnabled && (
        <button className={rowCls(selection.type === 'review')} onClick={() => onSelect({ type: 'review' })}>
          <FilePenLine className="h-3.5 w-3.5 shrink-0" />
          <span className="truncate">待审草稿</span>
        </button>
      )}
      <button className={rowCls(selection.type === 'mydrafts')} onClick={() => onSelect({ type: 'mydrafts' })}>
        <FileText className="h-3.5 w-3.5 shrink-0" />
        <span className="truncate">草稿箱</span>
      </button>
      <button className={rowCls(selection.type === 'archived')} onClick={() => onSelect({ type: 'archived' })}>
        <Archive className="h-3.5 w-3.5 shrink-0" />
        <span className="truncate">已归档</span>
      </button>

      <div className="px-2 pb-1 pt-3 t-xs font-medium text-gray-400">账号</div>
      {accountsQuery.isLoading && <div className="px-2 py-2 t-sm text-gray-400">加载中…</div>}
      {accounts.map((a) => {
        const open = expanded.includes(a.id)
        const active = isInboxActive(a.id)
        return (
          <div key={a.id}>
            {/* 账号行：点击 = 选中其收件箱并展开；chevron 单独负责折叠 */}
            <div
              className={rowCls(active)}
              onClick={() => onSelect({ type: 'inbox', accountId: a.id })}
              title={a.status_detail ?? a.email}
            >
              <button
                className="flex shrink-0 items-center rounded p-0.5 text-gray-400 hover:text-gray-700"
                onClick={(e) => {
                  e.stopPropagation()
                  toggleExpand(a.id)
                }}
                title={open ? '折叠账号' : '展开账号'}
              >
                {open ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
              </button>
              <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${statusDotCls(a.status)}`} />
              <span className="truncate">{a.email}</span>
            </div>
            {open && (
              <div className="ml-5 border-l border-gray-100 pl-1.5">
                <button className={rowCls(active)} onClick={() => onSelect({ type: 'inbox', accountId: a.id })}>
                  <Inbox className="h-3.5 w-3.5 shrink-0" />
                  <span className="truncate">收件箱</span>
                </button>
              </div>
            )}
          </div>
        )
      })}
    </aside>
  )
}
