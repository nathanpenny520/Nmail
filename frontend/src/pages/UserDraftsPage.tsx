import { useQuery, useQueryClient } from '@tanstack/react-query'
import { AlarmClock, FileText, Loader2, Paperclip, Trash2 } from 'lucide-react'
import { api } from '../api/client'
import type { UserDraft } from '../types'
import { useCompose } from '../components/compose/ComposeContext'

function fmtTime(iso: string): string {
  return new Date(iso).toLocaleString('zh-CN', {
    month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false,
  })
}

/**
 * 草稿箱：写信台已保存的手写草稿（editing + scheduled，含用户显式保存的空稿）。
 * 点击整行回到写信台继续编辑；行尾可彻底删除。
 */
export default function UserDraftsPage() {
  const { openDraft } = useCompose()
  const queryClient = useQueryClient()
  const listQuery = useQuery({
    queryKey: ['user-drafts'],
    queryFn: async () => {
      const [editing, scheduled] = await Promise.all([
        api.getUserDrafts('editing'),
        api.getUserDrafts('scheduled'),
      ])
      return [...scheduled.drafts, ...editing.drafts]
    },
  })

  const drafts = listQuery.data ?? []

  const remove = async (id: number) => {
    await api.deleteUserDraft(id)
    void queryClient.invalidateQueries({ queryKey: ['user-drafts'] })
  }

  return (
    <div className="mx-auto max-w-3xl space-y-2 p-4">
      <h1 className="flex items-center gap-2 px-1 pb-1 t-lg font-semibold">
        <FileText className="h-4 w-4 text-indigo-500" />
        草稿箱
        <span className="t-sm font-normal text-gray-400">写信台保存的草稿，点击继续编辑</span>
      </h1>
      {listQuery.isLoading && (
        <div className="flex items-center gap-2 p-6 t-sm text-gray-400">
          <Loader2 className="h-4 w-4 animate-spin" /> 加载中…
        </div>
      )}
      {!listQuery.isLoading && drafts.length === 0 && (
        <div className="rounded-2xl border border-gray-200 bg-white p-10 text-center t-sm text-gray-400">
          暂无草稿——写信时点「存草稿」或直接关标签保留，都会出现在这里
        </div>
      )}
      {drafts.map((d: UserDraft) => (
        <div
          key={d.id}
          onClick={() => openDraft(d)}
          className="flex cursor-pointer items-center gap-3 rounded-xl border border-gray-200 bg-white px-4 py-2.5 transition-colors hover:border-indigo-300 hover:bg-indigo-50/40"
        >
          {d.status === 'scheduled' ? (
            <span
              className="inline-flex shrink-0 items-center gap-1 rounded-md bg-amber-100 px-1.5 py-0.5 t-xs font-medium text-amber-700"
              title={`到点自动发送：${fmtTime(d.send_at!)}`}
            >
              <AlarmClock className="h-3 w-3" />
              定时 {fmtTime(d.send_at!)}
            </span>
          ) : (
            <span className="shrink-0 rounded-md bg-gray-100 px-1.5 py-0.5 t-xs text-gray-500">草稿</span>
          )}
          <span className="w-56 shrink-0 truncate t-sm font-medium text-gray-800">
            {d.subject.trim() || '（无主题）'}
          </span>
          <span className="min-w-0 flex-1 truncate t-sm text-gray-500">
            {d.to_addrs || <span className="text-gray-300">未填收件人</span>}
          </span>
          {d.attachments.length > 0 && (
            <span className="inline-flex shrink-0 items-center gap-1 t-xs text-gray-400" title={`${d.attachments.length} 个附件`}>
              <Paperclip className="h-3 w-3" />
              {d.attachments.length}
            </span>
          )}
          <span className="shrink-0 t-xs text-gray-400">{fmtTime(d.updated_at)}</span>
          <button
            className="shrink-0 rounded-md p-1 text-gray-300 transition-colors hover:bg-red-50 hover:text-red-500"
            title="删除草稿"
            onClick={(e) => {
              e.stopPropagation()
              void remove(d.id)
            }}
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      ))}
    </div>
  )
}
