import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Archive } from 'lucide-react'
import { useState } from 'react'
import { Navigate, useSearchParams } from 'react-router-dom'
import { api } from '../api/client'
import { useJob } from '../api/useJob'
import { useFlash } from '../hooks/useFlash'
import type { EmailSummary } from '../types'
import FolderTree, { type TreeSelection } from '../components/FolderTree'
import MailBrowser from '../components/MailBrowser'
import { Modal } from '../components/compose/ui'

/**
 * 邮件基座页（v0.4，REDESIGN_PLAN §3/§4）：左侧文件夹树 + 内容区。
 * - 视图初值固定聚合收件箱（旧 /?view=drafts 深链就地重定向到草稿页签），之后由树驱动；
 * - 选中服务器文件夹 = 按需同步（后台轮询只拉 INBOX）；
 * - 本地归档存量一次性迁移弹窗（§4.6：归档语义改服务器移动）。
 */
export default function MailPage() {
  const queryClient = useQueryClient()
  const [searchParams] = useSearchParams()
  const [sel, setSel] = useState<TreeSelection>({ type: 'inbox', accountId: null })

  // 选中服务器文件夹 → 触发按需同步（先出本地缓存，增量补齐后列表自动刷新）
  const select = (next: TreeSelection) => {
    setSel(next)
    if (next.type === 'folder' && next.name !== 'INBOX') {
      void api.syncAccount(next.accountId, next.name).catch(() => undefined)
    }
  }

  // 拖拽移动（REDESIGN_PLAN §4.3，v0.4 审查 U1）：乐观更新 + job 进度 + 失败回滚提示。
  // 原实现 .catch(() => undefined) 吞掉一切错误——拖了没反应也不知道成败。
  const [moveNote, flashMove] = useFlash(5000)
  const { job: moveJob, start: startMoveJob } = useJob((finished) => {
    invalidateAfterMove()
    if (finished.status === 'failed') {
      flashMove(`移动失败：${finished.detail || '未知错误'}（列表已还原）`, 6000)
      return
    }
    const r = (finished.result ?? {}) as { updated?: number; failed?: number }
    const failedNote = (r.failed ?? 0) > 0 ? `，${r.failed} 封失败` : ''
    flashMove(`已移动 ${r.updated ?? 0} 封${failedNote}`)
  })

  const invalidateAfterMove = () => {
    void queryClient.invalidateQueries({ queryKey: ['emails'] })
    void queryClient.invalidateQueries({ queryKey: ['accounts'] })
    void queryClient.invalidateQueries({ queryKey: ['folder-cache'] })
  }

  const dropMutation = useMutation({
    mutationFn: ({ ids, folder }: { ids: number[]; folder: string }) =>
      api.batchAction(ids, 'move', folder),
    onMutate: async ({ ids }) => {
      // 乐观更新：先从本地缓存列表摘掉被拖走的邮件，失败回滚快照
      await queryClient.cancelQueries({ queryKey: ['emails'] })
      const snapshots = queryClient.getQueriesData<{ total: number; items: EmailSummary[] }>({
        queryKey: ['emails'],
      })
      for (const [key, data] of snapshots) {
        if (!data) continue
        const removed = data.items.filter((it) => ids.includes(it.id)).length
        if (removed === 0) continue
        queryClient.setQueryData(key, {
          ...data,
          total: Math.max(0, data.total - removed),
          items: data.items.filter((it) => !ids.includes(it.id)),
        })
      }
      return { snapshots }
    },
    onError: (error: Error, _vars, ctx) => {
      ctx?.snapshots.forEach(([key, data]) => queryClient.setQueryData(key, data))
      flashMove(`移动失败：${error.message}（列表已还原）`, 6000)
    },
    onSuccess: (result) => {
      if (result.job_id != null) {
        startMoveJob(result.job_id) // 大批量转后台 job，进度走 useJob 轮询
        return
      }
      const failedNote = result.failed > 0 ? `，${result.failed} 封失败` : ''
      flashMove(`已移动 ${result.updated} 封${failedNote}`)
      invalidateAfterMove()
    },
  })

  const onDropEmails = (ids: number[], _accountId: number, folder: string) => {
    if (ids.length === 0) return
    dropMutation.mutate({ ids, folder })
  }

  // 草稿页签化（v0.4.x）：旧深链 /?view=drafts 就地转跳草稿页签（hooks 须先全部执行，勿提前 return）
  if (searchParams.get('view') === 'drafts') return <Navigate to="/drafts" replace />

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
      </div>
      {(moveJob?.status === 'running' || moveNote) && (
        <div className="pointer-events-none fixed bottom-5 left-1/2 z-40 flex -translate-x-1/2 items-center gap-2 whitespace-nowrap rounded-full border border-indigo-200 bg-white px-4 py-1.5 t-sm text-indigo-600 shadow-lg">
          {moveJob?.status === 'running' ? (
            <>
              <span className="h-1.5 w-28 overflow-hidden rounded-full bg-indigo-100">
                <span
                  className="block h-full rounded-full bg-indigo-500 transition-all duration-500"
                  style={{ width: `${Math.max(5, Math.round(moveJob.progress * 100))}%` }}
                />
              </span>
              正在移动 {Math.round(moveJob.progress * 100)}%{moveJob.detail ? ` · ${moveJob.detail}` : ''}
            </>
          ) : (
            moveNote
          )}
        </div>
      )}
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
