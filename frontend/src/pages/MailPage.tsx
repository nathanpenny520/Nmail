import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Archive } from 'lucide-react'
import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../api/client'
import { useJob } from '../api/useJob'
import FolderTree, { type TreeSelection } from '../components/FolderTree'
import MailBrowser from '../components/MailBrowser'
import { Modal } from '../components/compose/ui'
import DraftsHubPage from './DraftsHubPage'

function selectionFromParams(view: string | null): TreeSelection {
  switch (view) {
    case 'drafts':
      return { type: 'drafts' }
    default:
      return { type: 'inbox', accountId: null }
  }
}

/**
 * 邮件基座页（v0.4，REDESIGN_PLAN §3/§4）：左侧文件夹树 + 内容区。
 * - 视图初值取 URL（承接旧路由重定向深链），之后由树驱动；
 * - 选中服务器文件夹 = 按需同步（后台轮询只拉 INBOX）；
 * - 本地归档存量一次性迁移弹窗（§4.6：归档语义改服务器移动）。
 */
export default function MailPage() {
  const queryClient = useQueryClient()
  const [searchParams] = useSearchParams()
  const [sel, setSel] = useState<TreeSelection>(() => selectionFromParams(searchParams.get('view')))

  // 选中服务器文件夹 → 触发按需同步（先出本地缓存，增量补齐后列表自动刷新）
  const select = (next: TreeSelection) => {
    setSel(next)
    if (next.type === 'folder' && next.name !== 'INBOX') {
      void api.syncAccount(next.accountId, next.name).catch(() => undefined)
    }
  }

  const onDropEmails = (ids: number[], _accountId: number, folder: string) => {
    if (ids.length === 0) return
    void api.batchAction(ids, 'move', folder).catch(() => undefined)
    void queryClient.invalidateQueries({ queryKey: ['accounts'] })
  }

  return (
    <div className="flex h-full min-w-0">
      <FolderTree selection={sel} onSelect={select} onDropEmails={onDropEmails} />
      <div className="min-w-0 flex-1">
        {sel.type === 'inbox' && (
          <MailBrowser key={`inbox-${sel.accountId ?? 'all'}`} initialAccountId={sel.accountId} />
        )}
        {sel.type === 'folder' && (
          <MailBrowser key={`folder-${sel.accountId}-${sel.name}`} initialAccountId={sel.accountId} initialFolder={sel.name} />
        )}
        {sel.type === 'drafts' && <DraftsHubPage />}
      </div>
      <ArchivedMigratePrompt />
    </div>
  )
}

/** 存量本地归档一次性迁移提示（REDESIGN_PLAN §4.6）：迁移到服务器 Archived 或跳过。 */
function ArchivedMigratePrompt() {
  const queryClient = useQueryClient()
  const pendingQuery = useQuery({
    queryKey: ['archived-pending'],
    queryFn: api.archivedPending,
    staleTime: Infinity,
  })
  const [migrating, setMigrating] = useState(false)
  const { job, start } = useJob((finished) => {
    if (finished.status !== 'running') {
      setMigrating(false)
      void queryClient.invalidateQueries({ queryKey: ['archived-pending'] })
      void queryClient.invalidateQueries({ queryKey: ['folder-cache'] })
      void queryClient.invalidateQueries({ queryKey: ['emails'] })
      void queryClient.invalidateQueries({ queryKey: ['accounts'] })
    }
  })
  const migrateMutation = useMutation({
    mutationFn: api.migrateArchived,
    onSuccess: (result) => {
      if (result.job_id != null) {
        setMigrating(true)
        start(result.job_id) // 进度经 useJob 1s 轮询，完成后统一失效
      } else {
        void queryClient.invalidateQueries({ queryKey: ['archived-pending'] })
      }
    },
  })

  const data = pendingQuery.data
  if (!data || data.done || data.count === 0) return null
  const running = migrating || job?.status === 'running'

  return (
    <Modal title="迁移本地归档邮件" onClose={running ? () => undefined : () => void api.dismissArchivedMigrate()} width="max-w-md">
      <div className="space-y-3 px-5 pb-5 pt-4">
        <div className="flex items-start gap-2.5">
          <Archive className="mt-0.5 h-5 w-5 shrink-0 text-indigo-500" />
          <p className="t-md text-gray-600">
            检测到 <b>{data.count}</b> 封旧版本地归档的邮件。v0.4 起归档改为每账号服务器端的
            <b> Archived</b> 文件夹（网页端同步可见）。可现在把它们移到各自账号的 Archived 文件夹，
            或保留原地（这些邮件不会出现在收件箱，但也不再展示）。
          </p>
        </div>
        <div className="flex justify-end gap-2">
          <button
            className="rounded-lg border border-gray-300 px-3 py-1.5 t-sm text-gray-600 hover:bg-gray-50 disabled:opacity-50"
            disabled={running}
            onClick={() => void api.dismissArchivedMigrate().then(() =>
              queryClient.invalidateQueries({ queryKey: ['archived-pending'] }),
            )}
          >
            保留原地
          </button>
          <button
            className="rounded-lg bg-indigo-600 px-3 py-1.5 t-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
            disabled={running}
            onClick={() => migrateMutation.mutate()}
          >
            {running ? '迁移中…（可继续使用）' : `迁移 ${data.count} 封`}
          </button>
        </div>
      </div>
    </Modal>
  )
}
