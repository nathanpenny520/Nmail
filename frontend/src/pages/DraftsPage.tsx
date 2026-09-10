import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { FilePenLine, Loader2, Send, Sparkles, Trash2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { Draft } from '../types'

type Tab = 'pending' | 'sent' | 'discarded'

const TABS: { key: Tab; label: string }[] = [
  { key: 'pending', label: '待审' },
  { key: 'sent', label: '已发送' },
  { key: 'discarded', label: '已丢弃' },
]

export default function DraftsPage() {
  const [tab, setTab] = useState<Tab>('pending')
  const { data, isLoading, error } = useQuery({
    queryKey: ['drafts', tab],
    queryFn: () => api.getDrafts(tab),
    refetchInterval: tab === 'pending' ? 20000 : undefined,
  })
  const drafts = data?.drafts ?? []
  const pendingCount = useQuery({
    queryKey: ['drafts', 'pending'],
    queryFn: () => api.getDrafts('pending'),
    refetchInterval: 20000,
  }).data?.drafts.length ?? 0

  return (
    <div className="mx-auto max-w-3xl p-8">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">
          待审草稿
          {pendingCount > 0 && (
            <span className="ml-2 rounded-full bg-red-500 px-2 py-0.5 text-xs font-bold text-white">
              {pendingCount}
            </span>
          )}
        </h1>
        <div className="flex gap-1 rounded-lg bg-gray-100 p-1">
          {TABS.map((t) => (
            <button
              key={t.key}
              className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                tab === t.key ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-800'
              }`}
              onClick={() => setTab(t.key)}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-5 space-y-4">
        {isLoading && <div className="text-sm text-gray-400">加载中…</div>}
        {error && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {(error as Error).message}
          </div>
        )}
        {!isLoading && drafts.length === 0 && (
          <div className="rounded-2xl border border-dashed border-gray-200 px-6 py-12 text-center">
            <FilePenLine className="mx-auto h-8 w-8 text-gray-200" />
            <p className="mt-3 text-sm text-gray-400">
              {tab === 'pending'
                ? '暂无待审草稿。AI 会在新邮件需要回复时自动起草，也会在这里等你。'
                : tab === 'sent'
                  ? '还没有通过审核发出的草稿。'
                  : '没有已丢弃的草稿。'}
            </p>
          </div>
        )}
        {drafts.map((draft) => (
          <DraftCard key={draft.id} draft={draft} pending={tab === 'pending'} />
        ))}
      </div>
    </div>
  )
}

function DraftCard({ draft, pending }: { draft: Draft; pending: boolean }) {
  const queryClient = useQueryClient()
  const [content, setContent] = useState(draft.content)
  const [instruction, setInstruction] = useState('')
  const [showInstruction, setShowInstruction] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

  useEffect(() => setContent(draft.content), [draft.content, draft.id])

  const invalidate = () => void queryClient.invalidateQueries({ queryKey: ['drafts'] })

  const actionMutation = useMutation({
    mutationFn: ({ action, text }: { action: 'approve' | 'discard'; text?: string }) =>
      api.draftAction(draft.id, action, text),
    onSuccess: (_d, v) => {
      setMessage(v.action === 'approve' ? '已发送' : '已丢弃')
      invalidate()
    },
    onError: (err: Error) => {
      setMessage(`失败：${err.message}`)
      setTimeout(() => setMessage(null), 6000)
    },
  })

  const saveMutation = useMutation({
    mutationFn: () => api.updateDraft(draft.id, content),
    onSuccess: () => {
      setMessage('已保存修改')
      invalidate()
      setTimeout(() => setMessage(null), 4000)
    },
  })

  const regenMutation = useMutation({
    mutationFn: () => api.regenerateDraft(draft.email_id, instruction.trim() || undefined),
    onSuccess: (result) => {
      setContent(result.content)
      setShowInstruction(false)
      setInstruction('')
      invalidate()
    },
    onError: (err: Error) => {
      setMessage(`重新生成失败：${err.message}`)
      setTimeout(() => setMessage(null), 6000)
    },
  })

  const busy = actionMutation.isPending || saveMutation.isPending || regenMutation.isPending

  return (
    <div className="rounded-2xl border border-gray-200 bg-white shadow-sm">
      <div className="flex items-start justify-between gap-3 border-b border-gray-100 px-5 py-3">
        <div className="min-w-0">
          <div className="truncate text-sm font-medium text-gray-800">
            回复：{draft.email.subject || '（无主题）'}
          </div>
          <div className="mt-0.5 text-xs text-gray-400">
            给 {draft.email.sender_name} &lt;{draft.email.sender_email}&gt;
            {draft.email.date && ` · ${new Date(draft.email.date).toLocaleString('zh-CN', { hour12: false })}`}
          </div>
        </div>
        {draft.origin === 'ai' && (
          <span className="shrink-0 rounded-full bg-violet-100 px-2 py-0.5 text-[10px] font-medium text-violet-700">
            AI 起草
          </span>
        )}
      </div>

      <div className="px-5 py-3">
        <p className="line-clamp-2 text-xs text-gray-400">{draft.email.snippet}</p>
        <textarea
          className="mt-3 w-full resize-y rounded-lg border border-gray-200 bg-gray-50/50 px-3 py-2.5 font-mono text-[13px] leading-relaxed outline-none focus:border-violet-400 focus:bg-white focus:ring-2 focus:ring-violet-100"
          rows={8}
          value={content}
          onChange={(e) => setContent(e.target.value)}
          disabled={!pending || busy}
          placeholder="草稿内容（支持 Markdown）"
        />

        {showInstruction && (
          <div className="mt-2 flex items-center gap-2">
            <input
              className="flex-1 rounded-lg border border-violet-200 px-3 py-1.5 text-xs outline-none focus:border-violet-500"
              placeholder="告诉 AI 怎么改，如：更委婉一些 / 补充下周三的时间"
              value={instruction}
              onChange={(e) => setInstruction(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && regenMutation.mutate()}
              autoFocus
            />
            <button
              className="rounded-lg bg-violet-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-violet-700"
              onClick={() => regenMutation.mutate()}
              disabled={regenMutation.isPending}
            >
              重新生成
            </button>
          </div>
        )}
      </div>

      {pending && (
        <div className="flex items-center gap-2 border-t border-gray-100 px-5 py-3">
          <button
            className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-4 py-1.5 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
            onClick={() => actionMutation.mutate({ action: 'approve', text: content })}
            disabled={busy || !content.trim()}
          >
            {actionMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />}
            发送
          </button>
          <button
            className="rounded-lg border border-gray-300 px-3 py-1.5 text-xs text-gray-700 hover:bg-gray-50 disabled:opacity-50"
            onClick={() => saveMutation.mutate()}
            disabled={busy}
          >
            保存修改
          </button>
          <button
            className="inline-flex items-center gap-1.5 rounded-lg border border-violet-200 px-3 py-1.5 text-xs text-violet-700 hover:bg-violet-50 disabled:opacity-50"
            onClick={() => setShowInstruction((v) => !v)}
            disabled={busy}
          >
            <Sparkles className={`h-3.5 w-3.5 ${regenMutation.isPending ? 'animate-spin' : ''}`} />
            重新生成
          </button>
          <span className="flex-1" />
          <button
            className="inline-flex items-center gap-1.5 rounded-lg border border-gray-200 px-3 py-1.5 text-xs text-gray-500 hover:text-red-600 disabled:opacity-50"
            onClick={() => actionMutation.mutate({ action: 'discard' })}
            disabled={busy}
          >
            <Trash2 className="h-3.5 w-3.5" /> 丢弃
          </button>
        </div>
      )}
      {message && (
        <div className="border-t border-gray-100 px-5 py-2 text-xs text-indigo-600">{message}</div>
      )}
    </div>
  )
}
