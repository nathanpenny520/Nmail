import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { FilePenLine, Loader2, RotateCcw, Send, Sparkles, Trash2, Undo2, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import { useAIEnabled } from '../api/useAI'
import type { Draft } from '../types'

type Tab = 'pending' | 'sent' | 'discarded'

const TABS: { key: Tab; label: string }[] = [
  { key: 'pending', label: '待审' },
  { key: 'sent', label: '已发送' },
  { key: 'discarded', label: '已丢弃' },
]

/** 待审草稿：收件箱式分屏（左列表 + 右详情），支持删除/恢复/带指令重写。 */
export default function DraftsPage() {
  const [tab, setTab] = useState<Tab>('pending')
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const queryClient = useQueryClient()
  const { data, isLoading } = useQuery({
    queryKey: ['drafts', tab],
    queryFn: () => api.getDrafts(tab),
    refetchInterval: tab === 'pending' ? 20000 : undefined,
  })
  const drafts = data?.drafts ?? []
  const selected = drafts.find((d) => d.id === selectedId) ?? null

  const invalidate = () => void queryClient.invalidateQueries({ queryKey: ['drafts'] })

  return (
    <div className="flex h-full">
      {/* 草稿列表 */}
      <section className="flex w-80 shrink-0 flex-col border-r border-gray-200 bg-white">
        <div className="flex items-center justify-between border-b border-gray-100 px-3 py-2.5">
          <h1 className="t-md font-semibold">草稿箱</h1>
          <div className="flex gap-0.5 rounded-lg bg-gray-100 p-0.5">
            {TABS.map((t) => (
              <button
                key={t.key}
                className={`rounded-md px-2 py-1 t-xs transition-colors ${
                  tab === t.key ? 'bg-white font-medium text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-800'
                }`}
                onClick={() => {
                  setTab(t.key)
                  setSelectedId(null)
                }}
              >
                {t.label}
              </button>
            ))}
          </div>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto">
          {isLoading && <div className="p-5 t-sm text-gray-400">加载中…</div>}
          {!isLoading && drafts.length === 0 && (
            <div className="p-8 text-center">
              <FilePenLine className="mx-auto h-7 w-7 text-gray-200" />
              <p className="mt-2 t-xs leading-relaxed text-gray-400">
                {tab === 'pending' ? '暂无待审草稿。新邮件需要回复时 AI 会自动起草。' : tab === 'sent' ? '还没有发过的草稿。' : '没有已丢弃的草稿。'}
              </p>
            </div>
          )}
          {drafts.map((d) => (
            <DraftRow
              key={d.id}
              draft={d}
              active={d.id === selectedId}
              tab={tab}
              onClick={() => setSelectedId(d.id)}
            />
          ))}
        </div>
      </section>

      {/* 详情 */}
      <section className="min-w-0 flex-1 bg-gray-50">
        {selected ? (
          <DraftDetail key={selected.id} draft={selected} tab={tab} onChanged={invalidate} />
        ) : (
          <div className="flex h-full items-center justify-center t-sm text-gray-300">
            选择一份草稿
          </div>
        )}
      </section>
    </div>
  )
}

function DraftRow({
  draft, active, tab, onClick,
}: {
  draft: Draft
  active: boolean
  tab: Tab
  onClick: () => void
}) {
  const queryClient = useQueryClient()
  const invalidate = () => void queryClient.invalidateQueries({ queryKey: ['drafts'] })
  const quickMutation = useMutation({
    mutationFn: async (action: 'discard' | 'delete') => {
      if (action === 'discard') await api.draftAction(draft.id, 'discard')
      else await api.deleteDraft(draft.id)
    },
    onSuccess: invalidate,
  })

  return (
    <div
      className={`group relative cursor-pointer border-b border-gray-50 px-3 py-2 transition-colors hover:bg-gray-50 ${
        active ? 'bg-indigo-50' : ''
      }`}
      onClick={onClick}
    >
      <div className="flex items-baseline gap-2">
        <span className="min-w-0 flex-1 truncate t-md font-medium text-gray-900">
          {draft.email.subject || '（无主题）'}
        </span>
        <span className="shrink-0 t-xs text-gray-400">
          {draft.created_at ? new Date(draft.created_at.replace(' ', 'T')).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false }) : ''}
        </span>
      </div>
      <div className="mt-0.5 flex items-center gap-1.5">
        {draft.origin === 'ai' && (
          <span className="shrink-0 rounded bg-violet-100 px-1 py-px t-xs text-violet-700">AI</span>
        )}
        <span className="min-w-0 flex-1 truncate t-xs text-gray-400">
          给 {draft.email.sender_email}
        </span>
      </div>
      {/* 行尾快捷操作 */}
      <div className="absolute right-2 top-1/2 hidden -translate-y-1/2 items-center gap-1 group-hover:flex">
        {tab === 'discarded' ? (
          <button
            className="rounded-md border border-gray-200 bg-white p-1 text-gray-500 hover:text-emerald-600"
            title="恢复为待审"
            onClick={(e) => {
              e.stopPropagation()
              void api.reopenDraft(draft.id).then(invalidate)
            }}
          >
            <Undo2 className="h-3 w-3" />
          </button>
        ) : null}
        <button
          className="rounded-md border border-gray-200 bg-white p-1 text-gray-500 hover:text-red-600"
          title={tab === 'pending' ? '丢弃' : '彻底删除'}
          onClick={(e) => {
            e.stopPropagation()
            quickMutation.mutate(tab === 'pending' ? 'discard' : 'delete')
          }}
        >
          <X className="h-3 w-3" />
        </button>
      </div>
    </div>
  )
}

function DraftDetail({ draft, tab, onChanged }: { draft: Draft; tab: Tab; onChanged: () => void }) {
  const [content, setContent] = useState(draft.content)
  const [instruction, setInstruction] = useState('')
  const [showInstruction, setShowInstruction] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const queryClient = useQueryClient()
  const aiEnabled = useAIEnabled()

  useEffect(() => setContent(draft.content), [draft.id, draft.content])

  const flash = (msg: string, ms = 4000) => {
    setMessage(msg)
    setTimeout(() => setMessage(null), ms)
  }
  const refresh = () => {
    onChanged()
    void queryClient.invalidateQueries({ queryKey: ['drafts'] })
  }

  const sendMutation = useMutation({
    mutationFn: () => api.draftAction(draft.id, 'approve', content),
    onSuccess: () => {
      flash('已发送')
      refresh()
    },
    onError: (err: Error) => flash(`发送失败：${err.message}`, 6000),
  })
  const saveMutation = useMutation({
    mutationFn: () => api.updateDraft(draft.id, content),
    onSuccess: () => {
      flash('已保存修改')
      refresh()
    },
    onError: (err: Error) => flash(`保存失败：${err.message}`, 6000),
  })
  const regenMutation = useMutation({
    mutationFn: () => api.regenerateDraft(draft.email_id, instruction.trim() || undefined),
    onSuccess: (result) => {
      setContent(result.content)
      setShowInstruction(false)
      setInstruction('')
      refresh()
    },
    onError: (err: Error) => flash(`重写失败：${err.message}`, 6000),
  })
  const discardMutation = useMutation({
    mutationFn: () => api.draftAction(draft.id, 'discard'),
    onSuccess: () => {
      flash('已丢弃')
      refresh()
    },
  })
  const reopenMutation = useMutation({
    mutationFn: () => api.reopenDraft(draft.id),
    onSuccess: () => {
      flash('已恢复为待审')
      refresh()
    },
  })
  const deleteMutation = useMutation({
    mutationFn: () => api.deleteDraft(draft.id),
    onSuccess: refresh,
  })

  const busy =
    sendMutation.isPending || saveMutation.isPending || regenMutation.isPending ||
    discardMutation.isPending || reopenMutation.isPending || deleteMutation.isPending

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-gray-100 px-5 py-3">
        <div className="flex items-center gap-2">
          <h2 className="min-w-0 flex-1 truncate t-md font-semibold text-gray-900">
            回复：{draft.email.subject || '（无主题）'}
          </h2>
          {draft.origin === 'ai' && (
            <span className="shrink-0 rounded-full bg-violet-100 px-2 py-0.5 t-xs font-medium text-violet-700">
              AI 起草
            </span>
          )}
        </div>
        <div className="mt-0.5 t-xs text-gray-400">
          给 {draft.email.sender_name} &lt;{draft.email.sender_email}&gt;
          {draft.email.date && ` · 原信 ${new Date(draft.email.date).toLocaleString('zh-CN', { hour12: false })}`}
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
        <p className="rounded-lg bg-gray-50 px-3 py-2 t-xs leading-relaxed text-gray-500">
          <span className="font-medium text-gray-600">原信摘要：</span>
          {draft.email.snippet || '（无）'}
        </p>

        <AutoTextarea
          className="mt-3 w-full resize-none rounded-xl border border-gray-200 bg-white px-3.5 py-3 font-mono t-md leading-relaxed outline-none transition-colors focus:border-violet-400 focus:ring-2 focus:ring-violet-100"
          value={content}
          onChange={setContent}
          readOnly={tab !== 'pending' || busy}
          placeholder="草稿内容（支持 Markdown，发送时自动转 HTML）"
        />

        {showInstruction && tab === 'pending' && (
          <div className="mt-2 flex items-center gap-2">
            <input
              className="flex-1 rounded-lg border border-violet-200 px-3 py-1.5 t-sm outline-none focus:border-violet-500"
              placeholder="告诉 AI 怎么改，如：更委婉一些 / 补充下周三的时间"
              value={instruction}
              onChange={(e) => setInstruction(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && regenMutation.mutate()}
              autoFocus
            />
            <button
              className="rounded-lg bg-violet-600 px-3 py-1.5 t-sm font-medium text-white hover:bg-violet-700"
              onClick={() => regenMutation.mutate()}
              disabled={regenMutation.isPending}
            >
              重新生成
            </button>
          </div>
        )}

        {message && <div className="mt-2 t-sm text-indigo-600">{message}</div>}
      </div>

      <div className="flex flex-wrap items-center gap-2 border-t border-gray-100 px-5 py-2.5">
        {tab === 'pending' && (
          <>
            <button
              className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3.5 py-1.5 t-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
              onClick={() => sendMutation.mutate()}
              disabled={busy || !content.trim()}
            >
              {sendMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />}
              发送
            </button>
            <button
              className="rounded-lg border border-gray-300 px-2.5 py-1.5 t-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50"
              onClick={() => saveMutation.mutate()}
              disabled={busy}
            >
              保存修改
            </button>
            {aiEnabled && (
              <button
                className="inline-flex items-center gap-1.5 rounded-lg border border-violet-200 px-2.5 py-1.5 t-sm text-violet-700 hover:bg-violet-50 disabled:opacity-50"
                onClick={() => setShowInstruction((v) => !v)}
                disabled={busy}
              >
                <Sparkles className={`h-3 w-3 ${regenMutation.isPending ? 'animate-spin' : ''}`} /> AI 重写
              </button>
            )}
            <span className="flex-1" />
            <button
              className="inline-flex items-center gap-1 rounded-lg border border-gray-200 px-2 py-1.5 t-sm text-gray-500 hover:text-amber-600 disabled:opacity-50"
              onClick={() => discardMutation.mutate()}
              disabled={busy}
              title="移入已丢弃（可恢复）"
            >
              <Trash2 className="h-3 w-3" /> 丢弃
            </button>
          </>
        )}
        {tab === 'discarded' && (
          <button
            className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-200 px-2.5 py-1.5 t-sm text-emerald-700 hover:bg-emerald-50 disabled:opacity-50"
            onClick={() => reopenMutation.mutate()}
            disabled={busy}
          >
            <RotateCcw className="h-3 w-3" /> 恢复为待审
          </button>
        )}
        <button
          className="inline-flex items-center gap-1 rounded-lg border border-gray-200 px-2 py-1.5 t-sm text-gray-500 hover:text-red-600 disabled:opacity-50"
          onClick={() => {
            if (confirm('彻底删除这份草稿？不可恢复。')) deleteMutation.mutate()
          }}
          disabled={busy}
        >
          <X className="h-3 w-3" /> 彻底删除
        </button>
      </div>
    </div>
  )
}

/** 高度自适应内容的文本域（不再固定行数滚动）。 */
function AutoTextarea({
  value, onChange, className, readOnly, placeholder,
}: {
  value: string
  onChange: (v: string) => void
  className?: string
  readOnly?: boolean
  placeholder?: string
}) {
  const ref = useRef<HTMLTextAreaElement>(null)
  const resize = () => {
    const el = ref.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight + 2, 2000)}px`
  }
  useEffect(resize, [value])
  return (
    <textarea
      ref={ref}
      className={className}
      value={value}
      readOnly={readOnly}
      placeholder={placeholder}
      onInput={resize}
      onChange={(e) => onChange(e.target.value)}
    />
  )
}
