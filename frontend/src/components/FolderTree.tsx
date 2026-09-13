import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Archive, BarChart3, Ban, ChevronDown, ChevronRight, FilePenLine, FileText, Folder, FolderPlus,
  Inbox, Mail, Pencil, RefreshCw, Send, Sparkles, Trash2,
} from 'lucide-react'
import { useEffect, useState, type MouseEvent as ReactMouseEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { useAIEnabled } from '../api/useAI'
import { useTreeCollapsed } from '../hooks/useSidebar'
import type { Account, FolderCacheItem } from '../types'
import ContextMenu, { type ContextMenuItem } from './ContextMenu'
import { useCompose } from './compose/ComposeContext'
import { Modal } from './compose/ui'

/** 邮件基座的树选中项（v0.4：智能视图 + 账号收件箱 + 服务器文件夹；草稿升级为页面页签后不在树选中态内）。 */
export type TreeSelection =
  | { type: 'inbox'; accountId: number | null }
  | { type: 'folder'; accountId: number; name: string }

const SPECIAL_META: Record<string, { icon: typeof Inbox }> = {
  sent: { icon: Send },
  drafts: { icon: FileText },
  junk: { icon: Ban },
  trash: { icon: Trash2 },
  flagged: { icon: Mail },
}

const rowCls = (active: boolean) =>
  `flex w-full cursor-pointer items-center gap-1.5 rounded-md px-2 py-[5px] t-md text-left transition-colors ${
    active
      ? 'bg-indigo-50 font-medium text-indigo-700'
      : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
  }`

/** 折叠态（w-14 图标栏）按钮：激活=树选中项正在前台。 */
const railBtnCls = (active: boolean) =>
  `flex h-8 w-8 shrink-0 cursor-pointer items-center justify-center rounded-lg transition-colors ${
    active ? 'bg-indigo-50 text-indigo-700' : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
  }`

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

/** 按 IMAP 分隔符把平铺文件夹名组装成层级树。 */
interface FolderNode {
  name: string   // 完整名（IMAP 实名）
  label: string  // 显示名（最后一段）
  item: FolderCacheItem
  children: FolderNode[]
}

function buildForest(items: FolderCacheItem[]): FolderNode[] {
  const map = new Map<string, FolderNode>()
  for (const it of items) {
    map.set(it.name, { name: it.name, label: it.name, item: it, children: [] })
  }
  const roots: FolderNode[] = []
  for (const node of map.values()) {
    const d = node.item.delim || '/'
    const idx = node.name.lastIndexOf(d)
    let parentName: string | null = null
    if (idx > 0) {
      parentName = node.name.slice(0, idx)
      node.label = node.name.slice(idx + d.length)
      // 父级不在缓存（部分服务器不下发容器）→ 逐段上溯挂到最近存在的祖先，否则顶层
      while (parentName && !map.has(parentName)) {
        const pIdx = parentName.lastIndexOf(d)
        parentName = pIdx > 0 ? parentName.slice(0, pIdx) : null
      }
    }
    if (parentName) map.get(parentName)!.children.push(node)
    else roots.push(node)
  }
  const sortRec = (nodes: FolderNode[]) => {
    // 大小写不敏感排序（v0.4 验收反馈：小写命名的文件夹不应沉底）
    nodes.sort((a, b) => a.name.localeCompare(b.name, 'zh-Hans-CN', { sensitivity: 'base', numeric: true }))
    nodes.forEach((n) => sortRec(n.children))
  }
  sortRec(roots)
  return roots
}

// 节点排序权重：INBOX → Archived → 系统文件夹 → 自定义
const nodeRank = (n: FolderNode) =>
  n.name.toUpperCase() === 'INBOX' ? 0 : n.item.is_archive ? 1 : n.item.is_system ? 2 : 3

/** 文件夹树（VSCode 资源管理器式，v0.4 P2 完整版）：
 * 智能视图 + 账号折叠组（服务器文件夹层级、右键 CRUD、拖拽落点、All Mail 守卫）。 */
export default function FolderTree({
  selection,
  onSelect,
  onDropEmails,
}: {
  selection: TreeSelection
  onSelect: (sel: TreeSelection) => void
  onDropEmails: (ids: number[], accountId: number, folder: string) => void
}) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const { setActiveTab } = useCompose()
  const aiEnabled = useAIEnabled()
  const accountsQuery = useQuery({ queryKey: ['accounts'], queryFn: api.getAccounts })
  const accounts: Account[] = accountsQuery.data?.accounts ?? []

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
    const id = selection.accountId
    if (id != null) setExpanded((prev) => (prev.includes(id) ? prev : [...prev, id]))
  }, [selection])

  // 树内的页面入口（AI 总管家/每日摘要）：跳转路由即产生页签（Layout 的 PAGE_TABS 机制）
  const openPage = (path: string) => {
    navigate(path)
    setActiveTab(null)
  }

  // 草稿入口徽章：AI 待审草稿数（v0.4 审查 U3：树此前完全没有计数徽章）
  const pendingDraftsQuery = useQuery({
    queryKey: ['user-drafts', 'pending_review'],
    queryFn: () => api.getUserDrafts('pending_review'),
    staleTime: 30_000,
    refetchInterval: 60_000,
  })
  const pendingDraftCount = pendingDraftsQuery.data?.drafts.length ?? 0

  // 右键菜单与 CRUD 对话框
  const [menu, setMenu] = useState<{ x: number; y: number; items: ContextMenuItem[] } | null>(null)
  const [dialog, setDialog] = useState<
    | { mode: 'create'; accountId: number; parent?: string }
    | { mode: 'rename'; accountId: number; name: string }
    | { mode: 'delete'; accountId: number; name: string }
    | null
  >(null)
  const [dialogText, setDialogText] = useState('')
  const [dialogError, setDialogError] = useState('')
  const [busy, setBusy] = useState(false)

  const runFolderAction = async (fn: () => Promise<unknown>) => {
    setBusy(true)
    setDialogError('')
    try {
      await fn()
      void queryClient.invalidateQueries({ queryKey: ['folder-cache'] })
      void queryClient.invalidateQueries({ queryKey: ['emails'] })
      setDialog(null)
      setDialogText('')
    } catch (err) {
      setDialogError((err as Error).message || '操作失败')
    } finally {
      setBusy(false)
    }
  }

  const submitDialog = async () => {
    if (!dialog || !dialogText.trim()) return
    if (dialog.mode === 'create') {
      const name = dialog.parent ? `${dialog.parent}/${dialogText.trim()}` : dialogText.trim()
      await runFolderAction(() => api.createFolder(dialog.accountId, name))
    } else if (dialog.mode === 'rename') {
      const prefix = dialog.name.includes('/')
        ? `${dialog.name.slice(0, dialog.name.lastIndexOf('/'))}/`
        : ''
      await runFolderAction(() => api.renameFolder(dialog.accountId, dialog.name, prefix + dialogText.trim()))
    }
  }

  const openMenu = (e: ReactMouseEvent, account: Account, node: FolderNode | null) => {
    e.preventDefault()
    e.stopPropagation()
    const items: ContextMenuItem[] = []
    if (node == null || (!node.item.is_system && !node.item.is_archive)) {
      items.push({
        label: node ? '新建子文件夹' : '新建文件夹',
        icon: FolderPlus,
        onSelect: () => {
          setDialogText('')
          setDialogError('')
          setDialog({ mode: 'create', accountId: account.id, parent: node?.name })
        },
      })
    }
    if (node && !node.item.is_system && !node.item.is_archive) {
      items.push(
        {
          label: '重命名',
          icon: Pencil,
          onSelect: () => {
            setDialogText(node.label)
            setDialogError('')
            setDialog({ mode: 'rename', accountId: account.id, name: node.name })
          },
        },
        {
          label: '删除文件夹',
          icon: Trash2,
          danger: true,
          onSelect: () => setDialog({ mode: 'delete', accountId: account.id, name: node.name }),
        },
      )
    }
    if (node == null) {
      items.push({
        label: '刷新文件夹列表',
        icon: RefreshCw,
        onSelect: async () => {
          await api.refreshFolders(account.id).catch(() => undefined)
          void queryClient.invalidateQueries({ queryKey: ['folder-cache', account.id] })
        },
      })
    }
    if (items.length > 0) setMenu({ x: e.clientX, y: e.clientY, items })
  }

  const isInboxActive = (accountId: number | null) =>
    selection.type === 'inbox' && selection.accountId === accountId
  const isFolderActive = (accountId: number, name: string) =>
    selection.type === 'folder' && selection.accountId === accountId && selection.name === name

  const collapsed = useTreeCollapsed()

  // 折叠态（v0.4 汉堡主菜单，Gmail 式）：纯图标 + tooltip，徽章缩成角标圆点，分组标题隐藏；
  // 账号变首字母头像（状态色角标），点击直达该账号收件箱——文件夹层级收起态不展示，拖拽落点需展开后使用。
  // 两分支根元素同为 <aside>，React 原地复用 DOM 节点，宽度变化由 transition 平滑过渡。
  if (collapsed) {
    return (
      <aside className="flex w-14 shrink-0 flex-col items-center overflow-y-auto border-r border-gray-200 bg-white px-1.5 py-2 transition-[width] duration-200">
        <button
          className={railBtnCls(isInboxActive(null))}
          onClick={() => onSelect({ type: 'inbox', accountId: null })}
          title="聚合收件箱"
          aria-label="聚合收件箱"
        >
          <Inbox className="h-4 w-4" />
        </button>
        <button
          className={`relative ${railBtnCls(false)}`}
          onClick={() => openPage('/drafts')}
          title={pendingDraftCount > 0 ? `草稿 · ${pendingDraftCount} 条待审` : '草稿'}
          aria-label="草稿"
        >
          <FilePenLine className="h-4 w-4" />
          {pendingDraftCount > 0 && (
            <span className="absolute right-1 top-1 h-1.5 w-1.5 rounded-full bg-violet-500" />
          )}
        </button>
        {aiEnabled && (
          <>
            <button
              className={railBtnCls(false)}
              onClick={() => openPage('/assistant')}
              title="AI 总管家"
              aria-label="AI 总管家"
            >
              <Sparkles className="h-4 w-4 text-violet-500" />
            </button>
            <button
              className={railBtnCls(false)}
              onClick={() => openPage('/digest')}
              title="每日摘要"
              aria-label="每日摘要"
            >
              <BarChart3 className="h-4 w-4" />
            </button>
          </>
        )}

        <div className="my-2 h-px w-8 shrink-0 bg-gray-200" />

        {accounts.map((a) => (
          <button
            key={a.id}
            className={`relative mb-1 flex h-8 w-8 shrink-0 cursor-pointer items-center justify-center rounded-full t-sm font-medium transition-colors ${
              isInboxActive(a.id) ? 'bg-indigo-100 text-indigo-700' : 'bg-gray-100 text-gray-600 hover:bg-gray-200/70'
            }`}
            onClick={() => onSelect({ type: 'inbox', accountId: a.id })}
            title={`${a.email}（收件箱）${a.status_detail ? `：${a.status_detail}` : ''}`}
            aria-label={`${a.email} 收件箱`}
          >
            {a.email.charAt(0).toUpperCase()}
            <span className={`absolute -right-0.5 -top-0.5 h-2.5 w-2.5 rounded-full border-2 border-white ${statusDotCls(a.status)}`} />
          </button>
        ))}
      </aside>
    )
  }

  return (
    <aside className="flex w-48 shrink-0 flex-col overflow-y-auto overflow-x-hidden border-r border-gray-200 bg-white px-1.5 py-2 transition-[width] duration-200">
      <div className="px-2 pb-1 pt-1 t-xs font-medium text-gray-400">智能视图</div>
      <button className={rowCls(isInboxActive(null))} onClick={() => onSelect({ type: 'inbox', accountId: null })}>
        <Inbox className="h-3.5 w-3.5 shrink-0" />
        <span className="truncate">聚合收件箱</span>
      </button>
      {/* v0.4 P3：待审草稿+草稿箱合并为「草稿」单一视图（AI 停用时手写稿仍可见）；v0.4.x 升级为页面页签，激活时树隐藏（同 AI 总管家） */}
      <button className={rowCls(false)} onClick={() => openPage('/drafts')}>
        <FilePenLine className="h-3.5 w-3.5 shrink-0" />
        <span className="truncate">草稿</span>
        {pendingDraftCount > 0 && (
          <span
            className="ml-auto shrink-0 rounded-full bg-violet-100 px-1.5 t-xs font-medium text-violet-600"
            title={`${pendingDraftCount} 条草稿待审`}
          >
            {pendingDraftCount > 99 ? '99+' : pendingDraftCount}
          </span>
        )}
      </button>
      {/* v0.4 审核意见：AI 总管家/每日摘要从右上角按钮移入树（点开为页签，离开邮件基座时树隐藏） */}
      {aiEnabled && (
        <>
          <button
            className={rowCls(false)}
            onClick={() => openPage('/assistant')}
            title="对话式 AI 助理：搜索、整理、起草、发送"
          >
            <Sparkles className="h-3.5 w-3.5 shrink-0 text-violet-500" />
            <span className="truncate">AI 总管家</span>
          </button>
          <button
            className={rowCls(false)}
            onClick={() => openPage('/digest')}
            title="每日邮件摘要与统计"
          >
            <BarChart3 className="h-3.5 w-3.5 shrink-0" />
            <span className="truncate">每日摘要</span>
          </button>
        </>
      )}

      <div className="px-2 pb-1 pt-3 t-xs font-medium text-gray-400">账号</div>
      {accountsQuery.isLoading && <div className="px-2 py-2 t-sm text-gray-400">加载中…</div>}
      {accounts.map((a) => (
        <AccountBranch
          key={a.id}
          account={a}
          open={expanded.includes(a.id)}
          activeInbox={isInboxActive(a.id)}
          isFolderActive={(name) => isFolderActive(a.id, name)}
          onToggle={() =>
            setExpanded((prev) => (prev.includes(a.id) ? prev.filter((x) => x !== a.id) : [...prev, a.id]))
          }
          onSelectInbox={() => onSelect({ type: 'inbox', accountId: a.id })}
          onSelectFolder={(name) => onSelect({ type: 'folder', accountId: a.id, name })}
          onContextMenu={openMenu}
          onDropEmails={onDropEmails}
        />
      ))}

      {menu && <ContextMenu x={menu.x} y={menu.y} items={menu.items} onClose={() => setMenu(null)} />}

      {dialog && (
        <Modal
          title={
            dialog.mode === 'create'
              ? dialog.parent
                ? `在「${dialog.parent.split('/').pop()}」下新建文件夹`
                : '新建文件夹'
              : dialog.mode === 'rename'
                ? '重命名文件夹'
                : '删除文件夹'
          }
          onClose={() => setDialog(null)}
          width="max-w-sm"
        >
          <div className="space-y-3 px-5 pb-5 pt-4">
            {dialog.mode === 'delete' ? (
              <p className="t-md text-gray-600">
                确认删除文件夹「{dialog.name.split('/').pop()}」？服务器上该文件夹（含其中邮件）将被删除，
                本地对应邮件与同步断点一并清理。<b className="text-red-600">此操作不可撤销。</b>
              </p>
            ) : (
              <div>
                <input
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 t-md outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100"
                  placeholder="文件夹名称"
                  value={dialogText}
                  onChange={(e) => setDialogText(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') void submitDialog()
                    if (e.key === 'Escape') setDialog(null)
                  }}
                  autoFocus
                />
                {dialog.mode === 'create' && dialog.parent && (
                  <p className="mt-1.5 t-xs text-gray-400">
                    将创建为「{dialog.parent.split('/').pop()}」的子文件夹
                  </p>
                )}
              </div>
            )}
            {dialogError && <p className="t-sm text-red-600">{dialogError}</p>}
            <div className="flex justify-end gap-2">
              <button
                className="rounded-lg border border-gray-300 px-3 py-1.5 t-sm text-gray-600 hover:bg-gray-50"
                onClick={() => setDialog(null)}
              >
                取消
              </button>
              {dialog.mode === 'delete' ? (
                <button
                  className="rounded-lg bg-red-600 px-3 py-1.5 t-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
                  disabled={busy}
                  onClick={() => void runFolderAction(() => api.deleteFolder(dialog.accountId, dialog.name))}
                >
                  {busy ? '删除中…' : '删除'}
                </button>
              ) : (
                <button
                  className="rounded-lg bg-indigo-600 px-3 py-1.5 t-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
                  disabled={busy || !dialogText.trim()}
                  onClick={() => void submitDialog()}
                >
                  {busy ? '保存中…' : dialog.mode === 'create' ? '创建' : '重命名'}
                </button>
              )}
            </div>
          </div>
        </Modal>
      )}
    </aside>
  )
}

/** 单个账号分支：折叠头（=INBOX 落点）+ 展开时的服务器文件夹层级（缓存懒加载）。 */
function AccountBranch({
  account,
  open,
  activeInbox,
  isFolderActive,
  onToggle,
  onSelectInbox,
  onSelectFolder,
  onContextMenu,
  onDropEmails,
}: {
  account: Account
  open: boolean
  activeInbox: boolean
  isFolderActive: (name: string) => boolean
  onToggle: () => void
  onSelectInbox: () => void
  onSelectFolder: (name: string) => void
  onContextMenu: (e: ReactMouseEvent, account: Account, node: FolderNode | null) => void
  onDropEmails: (ids: number[], accountId: number, folder: string) => void
}) {
  // 展开时懒加载缓存；缓存为空时后端自动连服务器 LIST
  const cacheQuery = useQuery({
    queryKey: ['folder-cache', account.id],
    queryFn: () => api.getFolders(account.id),
    enabled: open,
    staleTime: 5 * 60 * 1000,
  })
  const items = cacheQuery.data?.folders ?? []
  const forest = buildForest(items).sort(
    (x, y) => nodeRank(x) - nodeRank(y)
      || x.name.localeCompare(y.name, 'zh-Hans-CN', { sensitivity: 'base', numeric: true }),
  )

  return (
    <div>
      <div
        className={rowCls(activeInbox)}
        onClick={onSelectInbox}
        onContextMenu={(e) => onContextMenu(e, account, null)}
        onDragOver={(e) => {
          e.preventDefault()
          e.dataTransfer.dropEffect = 'move'
        }}
        onDrop={(e) => {
          e.preventDefault()
          try {
            const data = JSON.parse(e.dataTransfer.getData('application/x-nmail-ids') || 'null')
            if (data && Array.isArray(data.ids) && data.accountId === account.id) {
              onDropEmails(data.ids as number[], account.id, 'INBOX')
            }
          } catch { /* 忽略外部拖拽数据 */ }
        }}
        title={account.status_detail ?? account.email}
      >
        <button
          className="flex shrink-0 items-center rounded p-0.5 text-gray-400 hover:text-gray-700"
          onClick={(e) => {
            e.stopPropagation()
            onToggle()
          }}
          title={open ? '折叠账号' : '展开账号'}
        >
          {open ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
        </button>
        <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${statusDotCls(account.status)}`} />
        <span className="truncate">{account.email}</span>
      </div>
      {open && (
        <div className="ml-4 border-l border-gray-100">
          {cacheQuery.isLoading && <div className="px-2 py-1 t-xs text-gray-400">读取文件夹…</div>}
          {!cacheQuery.isLoading && items.length === 0 && (
            <div className="px-2 py-1 t-xs text-gray-400">暂无文件夹</div>
          )}
          {forest.map((node) => (
            <FolderNodeRow
              key={node.name}
              node={node}
              account={account}
              depth={0}
              isFolderActive={isFolderActive}
              onSelectFolder={onSelectFolder}
              onContextMenu={onContextMenu}
              onDropEmails={onDropEmails}
            />
          ))}
        </div>
      )}
    </div>
  )
}

/** 文件夹树节点行：层级缩进 + 拖拽落点 + 右键菜单 + All Mail 守卫。 */
function FolderNodeRow({
  node,
  account,
  depth,
  isFolderActive,
  onSelectFolder,
  onContextMenu,
  onDropEmails,
}: {
  node: FolderNode
  account: Account
  depth: number
  isFolderActive: (name: string) => boolean
  onSelectFolder: (name: string) => void
  onContextMenu: (e: ReactMouseEvent, account: Account, node: FolderNode | null) => void
  onDropEmails: (ids: number[], accountId: number, folder: string) => void
}) {
  const { item } = node
  const meta = item.is_archive
    ? { icon: Archive }
    : item.special_use
      ? (SPECIAL_META[item.special_use] ?? null)
      : null
  const isAllMail = item.special_use === 'all'
  const active = isFolderActive(node.name)
  return (
    <div>
      <div
        className={`${rowCls(active)} ${isAllMail ? 'cursor-not-allowed opacity-45' : ''}`}
        style={{ paddingLeft: 6 + depth * 12 }}
        onClick={() => {
          if (isAllMail) return // All Mail 守卫：容量过大不同步（REDESIGN_PLAN §4.4）
          onSelectFolder(node.name)
        }}
        onContextMenu={(e) => onContextMenu(e, account, node)}
        onDragOver={(e) => {
          if (isAllMail) return
          e.preventDefault()
          e.dataTransfer.dropEffect = 'move'
        }}
        onDrop={(e) => {
          if (isAllMail) return
          e.preventDefault()
          try {
            const data = JSON.parse(e.dataTransfer.getData('application/x-nmail-ids') || 'null')
            if (data && Array.isArray(data.ids) && data.accountId === account.id) {
              onDropEmails(data.ids as number[], account.id, node.name)
            }
          } catch { /* 忽略外部拖拽数据 */ }
        }}
        title={isAllMail ? '「全部邮件」容量过大，Nmail 不同步（避免误点全量拉取）' : node.name}
      >
        {meta ? (
          <meta.icon className="h-3.5 w-3.5 shrink-0" />
        ) : (
          <Folder className="h-3.5 w-3.5 shrink-0 text-gray-400" />
        )}
        {/* 归档夹显示服务器实名（账号可自定义 archive_folder 名，硬编码「Archived」会显示错，审查 C2） */}
        <span className="truncate">{node.label}</span>
        {item.unread > 0 && (
          <span
            className="ml-auto shrink-0 rounded-full bg-indigo-100 px-1.5 t-xs font-medium text-indigo-600"
            title={`${item.unread} 封未读`}
          >
            {item.unread > 99 ? '99+' : item.unread}
          </span>
        )}
      </div>
      {node.children.map((child) => (
        <FolderNodeRow
          key={child.name}
          node={child}
          account={account}
          depth={depth + 1}
          isFolderActive={isFolderActive}
          onSelectFolder={onSelectFolder}
          onContextMenu={onContextMenu}
          onDropEmails={onDropEmails}
        />
      ))}
    </div>
  )
}
