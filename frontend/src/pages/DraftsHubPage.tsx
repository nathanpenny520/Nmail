import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlarmClock, Loader2, Pencil, Send, Sparkles, Trash2, Undo2, X,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { api } from '../api/client'
import { parseBackendTime } from '../utils/format'
import { useFlash } from '../hooks/useFlash'
import type { UserDraft } from '../types'
import HtmlMail from '../components/HtmlMail'
import { useCompose } from '../components/compose/ComposeContext'

type Tab = 'pending_review' | 'editing' | 'scheduled' | 'sent' | 'discarded'

const TABS: { key: Tab; label: string }[] = [
  { key: 'pending_review', label: '待审' },
  { key: 'editing', label: '编辑中' },
  { key: 'scheduled', label: '定时中' },
  { key: 'sent', label: '已发送' },
  { key: 'discarded', label: '已丢弃' },
]

function fmtTime(iso: string | null, utcNaive = false): string {
  if (!iso) return ''
  // send_at 是特意的本地 naive（datetime-local）；updated_at 等 datetime('now') 是 UTC naive，需补 Z
  const d = utcNaive ? parseBackendTime(iso) : new Date(iso.replace(' ', 'T'))
  return d.toLocaleString('zh-CN', {
    month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false,
  })
}

/**
 * 草稿统一视图（v0.4 P3，REDESIGN_PLAN §5.1）：AI 待审 + 手写草稿合并。
 * 分段筛选 待审/编辑中/定时中/已发送/已丢弃；待审稿可批准发送、编辑后发送
 * （进写信台，同一发送通路）、带指令重写；行上徽章区分 ✦ AI / ✎ 手写。
 */
export default function DraftsHubPage() {
  const [tab, setTab] = useState<Tab>('pending_review')
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const queryClient = useQueryClient()
  const { data, isLoading } = useQuery({
    queryKey: ['user-drafts', tab],
    queryFn: () => api.getUserDrafts(tab),
    refetchInterval: tab === 'pending_review' ? 20000 : undefined,
  })
  const drafts = data?.drafts ?? []
  const selected = drafts.find((d) => d.id === selectedId) ?? drafts[0] ?? null

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['user-drafts'] })
    void queryClient.invalidateQueries({ queryKey: ['notifications'] })
  }

  return (
    <div className="flex h-full">
      {/* 草稿列表 */}
      <section className="flex w-80 shrink-0 flex-col border-r border-gray-200 bg-white">
        <div className="flex items-center justify-between border-b border-gray-100 px-3 py-2.5">
          <h1 className="t-md font-semibold">草稿</h1>
          <div className="flex gap-0.5 rounded-lg bg-gray-100 p-0.5">
            {TABS.map((t) => (
              <button
                key={t.key}
                className={`rounded-md px-2 py-0.5 t-sm transition-colors ${
                  tab === t.key ? 'bg-white font-medium text-indigo-700 shadow-sm' : 'text-gray-500 hover:text-gray-800'
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
        <div className="flex-1 overflow-y-auto">
          {isLoading && <div className="p-6 t-sm text-gray-400">加载中…</div>}
          {!isLoading && drafts.length === 0 && (
            <div className="p-8 text-center t-sm text-gray-300">
              {tab === 'pending_review' ? '暂无待审草稿。新邮件需要回复时 AI 会自动起草。' : '此视图暂无草稿'}
            </div>
          )}
          {drafts.map((d) => (
            <DraftRow key={d.id} draft={d} tab={tab} active={selected?.id === d.id} onClick={() => setSelectedId(d.id)} onChanged={invalidate} />
          ))}
        </div>
      </section>
      {/* 详情预览 */}
      <section className="min-w-0 flex-1 bg-gray-50">
        {selected ? (
          <DraftDetail draft={selected} tab={tab} onChanged={invalidate} />
        ) : (
          <div className="flex h-full items-center justify-center t-sm text-gray-300">选择一份草稿</div>
        )}
      </section>
    </div>
  )
}

function DraftRow({
  draft, tab, active, onClick, onChanged,
}: {
  draft: UserDraft
  tab: Tab
  active: boolean
  onClick: () => void
  onChanged: () => void
}) {
  const queryClient = useQueryClient()
  const quickMutation = useMutation({
    mutationFn: async (action: 'discard' | 'delete' | 'reopen') => {
      if (action === 'discard') await api.discardUserDraft(draft.id)
      else if (action === 'reopen') await api.reopenUserDraft(draft.id)
      else await api.deleteUserDraft(draft.id)
    },
    onSuccess: () => {
      onChanged()
      void queryClient.invalidateQueries({ queryKey: ['user-drafts'] })
    },
  })

  const title = draft.subject || draft.email?.subject || '（无主题）'
  const context =
    tab === 'scheduled' && draft.send_at
      ? `${fmtTime(draft.send_at)} 自动发送`
      : draft.email
        ? `回复 ${draft.email.sender_email}`
        : draft.to_addrs
          ? `给 ${draft.to_addrs}`
          : ''

  return (
    <div
      className={`group relative cursor-pointer border-b border-gray-50 px-3 py-2 transition-colors hover:bg-gray-50 ${
        active ? 'bg-indigo-50' : ''
      }`}
      onClick={onClick}
    >
      <div className="flex items-baseline gap-2">
        <span className="min-w-0 flex-1 truncate t-md font-medium text-gray-900">{title}</span>
        <span className="shrink-0 t-xs text-gray-400">{fmtTime(draft.updated_at, true)}</span>
      </div>
      <div className="mt-0.5 flex items-center gap-1.5">
        {draft.origin === 'ai' ? (
          <span className="shrink-0 rounded bg-violet-100 px-1 py-px t-xs text-violet-700">✦ AI</span>
        ) : (
          <span className="shrink-0 rounded bg-gray-100 px-1 py-px t-xs text-gray-500">✎ 手写</span>
        )}
        {draft.instruction && (
          <span className="max-w-32 shrink-0 truncate rounded bg-amber-50 px-1 py-px t-xs text-amber-600" title={`生成指令：${draft.instruction}`}>
            {draft.instruction}
          </span>
        )}
        <span className="min-w-0 flex-1 truncate t-xs text-gray-400">{context}</span>
      </div>
      {/* 行尾快捷操作 */}
      <div className="absolute right-2 top-1/2 hidden -translate-y-1/2 items-center gap-1 group-hover:flex">
        {tab === 'discarded' && (
          <button
            className="rounded-md border border-gray-200 bg-white p-1 text-gray-500 hover:text-emerald-600"
            title="恢复"
            onClick={(e) => {
              e.stopPropagation()
              quickMutation.mutate('reopen')
            }}
          >
            <Undo2 className="h-3 w-3" />
          </button>
        )}
        {(tab === 'pending_review' || tab === 'editing' || tab === 'scheduled' || tab === 'discarded') && (
          <button
            className="rounded-md border border-gray-200 bg-white p-1 text-gray-500 hover:text-red-600"
            title={tab === 'pending_review' ? '丢弃' : '彻底删除'}
            onClick={(e) => {
              e.stopPropagation()
              quickMutation.mutate(tab === 'pending_review' ? 'discard' : 'delete')
            }}
          >
            <X className="h-3 w-3" />
          </button>
        )}
      </div>
    </div>
  )
}

function DraftDetail({ draft, tab, onChanged }: { draft: UserDraft; tab: Tab; onChanged: () => void }) {
  const [instruction, setInstruction] = useState('')
  const [showInstruction, setShowInstruction] = useState(false)
  const [message, flash] = useFlash()
  const queryClient = useQueryClient()
  const compose = useCompose()

  useEffect(() => {
    setInstruction('')
    setShowInstruction(false)
  }, [draft.id])

  const refresh = () => {
    onChanged()
    void queryClient.invalidateQueries({ queryKey: ['user-drafts'] })
  }
  const act = (fn: () => Promise<unknown>, okMsg: string) =>
    fn().then(() => {
      flash(okMsg)
      refresh()
    }).catch((err: Error) => flash(`${okMsg}失败：${err.message}`, 6000))

  const sendMutation = useMutation({ mutationFn: () => api.sendUserDraft(draft.id), onSuccess: () => { flash('已发送'); refresh() }, onError: (err: Error) => flash(`发送失败：${err.message}`, 6000) })
  const regenMutation = useMutation({
    mutationFn: () => api.regenerateUserDraft(draft.id, instruction.trim() || undefined),
    onSuccess: () => { setShowInstruction(false); setInstruction(''); flash('已重写'); refresh() },
    onError: (err: Error) => flash(`重写失败：${err.message}`, 6000),
  })

  const title = draft.subject || '（无主题）'
  const contextInfo = draft.email
    ? `回复 ${draft.email.sender_name || draft.email.sender_email} · ${draft.email.subject}`
    : draft.to_addrs || ''

  return (
    <div className="flex h-full flex-col">
      {/* 详情头：主题 + 收件人 + 操作栏 */}
      <div className="shrink-0 border-b border-gray-200 bg-white px-4 py-3">
        <div className="flex items-start gap-2">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              {draft.origin === 'ai' ? (
                <span className="shrink-0 rounded bg-violet-100 px-1.5 py-0.5 t-xs text-violet-700">✦ AI 拟稿</span>
              ) : (
                <span className="shrink-0 rounded bg-gray-100 px-1.5 py-0.5 t-xs text-gray-500">✎ 手写</span>
              )}
              <h2 className="min-w-0 truncate t-lg font-semibold text-gray-900">{title}</h2>
            </div>
            <p className="mt-0.5 truncate t-sm text-gray-500">
              {contextInfo}
              {tab === 'scheduled' && draft.send_at && (
                <span className="ml-2 inline-flex items-center gap-1 text-amber-600">
                  <AlarmClock className="h-3 w-3" /> {fmtTime(draft.send_at)} 自动发送
                </span>
              )}
            </p>
          </div>
          <div className="flex shrink-0 flex-wrap items-center justify-end gap-1.5">
            {tab === 'pending_review' && (
              <>
                <button className={hubBtn} disabled={sendMutation.isPending} onClick={() => sendMutation.mutate()} title="按当前内容直接发送">
                  <Send className="h-3.5 w-3.5" /> 批准并发送
                </button>
                <button className={hubBtn} onClick={() => compose.openDraft(draft)} title="进写信台修改后发送（同一发送通路）">
                  <Pencil className="h-3.5 w-3.5" /> 编辑后发送
                </button>
                {draft.origin === 'ai' && (
                  <button className={hubBtn} onClick={() => setShowInstruction((v) => !v)} title="带指令重写正文">
                    <Sparkles className="h-3.5 w-3.5" /> 重写
                  </button>
                )}
                <button className={hubBtn} onClick={() => void act(() => api.discardUserDraft(draft.id), '已丢弃')}>
                  丢弃
                </button>
              </>
            )}
            {(tab === 'editing' || tab === 'scheduled') && (
              <>
                <button className={hubBtn} onClick={() => compose.openDraft(draft)}>
                  <Pencil className="h-3.5 w-3.5" /> 打开编辑
                </button>
                {tab === 'scheduled' && (
                  <button className={hubBtn} onClick={() => void act(() => api.unscheduleDraft(draft.id), '已取消定时')}>
                    <AlarmClock className="h-3.5 w-3.5" /> 取消定时
                  </button>
                )}
              </>
            )}
            {tab === 'discarded' && (
              <button className={hubBtn} onClick={() => void act(() => api.reopenUserDraft(draft.id), '已恢复')}>
                <Undo2 className="h-3.5 w-3.5" /> 恢复
              </button>
            )}
            {tab !== 'sent' && tab !== 'pending_review' && (
              <button className={hubBtn} onClick={() => void act(() => api.deleteUserDraft(draft.id), '已删除')}>
                <Trash2 className="h-3.5 w-3.5" /> 删除
              </button>
            )}
          </div>
        </div>
        {showInstruction && (
          <div className="mt-2 flex items-center gap-1.5">
            <input
              className="min-w-0 flex-1 rounded-lg border border-violet-200 px-2.5 py-1.5 t-sm outline-none focus:border-violet-400"
              placeholder="重写要求，如：更简短、语气更正式（留空=按原样重写）"
              value={instruction}
              onChange={(e) => setInstruction(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && regenMutation.mutate()}
              autoFocus
            />
            <button className={hubBtn} disabled={regenMutation.isPending} onClick={() => regenMutation.mutate()}>
              {regenMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : '重写'}
            </button>
          </div>
        )}
        {message && <p className="mt-2 t-sm text-indigo-600">{message}</p>}
      </div>
      {/* 正文预览（本地草稿自产 HTML；发送时统一消毒，预览沙箱无脚本） */}
      <div className="min-h-0 flex-1 overflow-y-auto bg-white p-4">
        {draft.body_html ? (
          <HtmlMail html={draft.body_html} />
        ) : (
          <div className="p-8 text-center t-sm text-gray-300">（空正文）</div>
        )}
      </div>
    </div>
  )
}

const hubBtn =
  'inline-flex items-center gap-1 whitespace-nowrap rounded-lg border border-gray-300 bg-white px-2.5 py-1.5 t-sm text-gray-700 transition-colors hover:border-indigo-300 hover:text-indigo-700 disabled:opacity-50'
