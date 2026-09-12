import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Check, Loader2, Pencil, Pin, PinOff, Plus, Send, ShieldAlert, Sparkles, Trash2, Undo2, Wrench, X,
} from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import { useAIEnabled } from '../api/useAI'
import { streamAgentEvents } from '../api/stream'
import { relativeTime } from '../utils/format'
import Markdown from '../components/Markdown'
import type { Account, AgentEvent, ChatSession } from '../types'

interface ChatMsg {
  role: 'user' | 'assistant'
  content: string
  events?: AgentEvent[] // v0.4 P6：工具调用/审批卡随消息展示
}

const QUICK_PROMPTS = [
  '总结一下各账号的邮箱概况',
  '有没有我漏回的邮件？',
  '找一下最近一周来自银行的邮件',
  '把收件箱里的营销邮件都归档',
]

/** 「AI 总管家」2.0（v0.4 P6，REDESIGN_PLAN §6）：对话 Agent——工具调用 +
 * 审批/自动双模式 + 动作卡。会话持久化沿用原总管家。 */
export default function ManagerPage() {
  const [sessionId, setSessionId] = useState<number | null>(null)
  const [messages, setMessages] = useState<ChatMsg[]>([])
  const [input, setInput] = useState('')
  const [accountId, setAccountId] = useState<number | null>(null)
  const [profileId, setProfileId] = useState<string>('')
  const [mode, setMode] = useState<'approval' | 'auto'>(() =>
    localStorage.getItem('nmail_agent_mode') === 'auto' ? 'auto' : 'approval')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')
  const scrollRef = useRef<HTMLDivElement>(null)
  const queryClient = useQueryClient()

  const accountsQuery = useQuery({ queryKey: ['accounts'], queryFn: api.getAccounts })
  const accounts: Account[] = accountsQuery.data?.accounts ?? []
  const sessionsQuery = useQuery({ queryKey: ['chats'], queryFn: api.getChats })
  const aiEnabled = useAIEnabled()
  const sessions: ChatSession[] = sessionsQuery.data?.sessions ?? []
  const profilesQuery = useQuery({ queryKey: ['ai-profiles'], queryFn: api.getAIProfiles })
  const profiles = profilesQuery.data?.profiles ?? []

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight })
  }, [messages, pending])

  const startNewChat = () => {
    if (pending) return
    setSessionId(null)
    setMessages([])
    setError('')
  }

  const openSession = async (session: ChatSession) => {
    if (pending || session.id === sessionId) return
    try {
      const data = await api.getChat(session.id)
      setSessionId(session.id)
      setMessages(data.messages.map((m) => ({ role: m.role, content: m.content })))
      setAccountId(data.session.account_id ?? null)
      setError('')
    } catch (err) {
      setError((err as Error).message || '加载会话失败')
    }
  }

  const patchLastEvents = (fn: (events: AgentEvent[]) => AgentEvent[]) => {
    setMessages((m) => {
      const next = [...m]
      const last = next[next.length - 1]
      if (last?.role === 'assistant') {
        next[next.length - 1] = { ...last, events: fn(last.events ?? []) }
      }
      return next
    })
  }

  const handleAgentEvent = (ev: AgentEvent) => {
    if (ev.type === 'text' && ev.text) {
      setMessages((m) => {
        const next = [...m]
        const last = next[next.length - 1]
        next[next.length - 1] = { ...last, content: last.content + ev.text }
        return next
      })
    } else if (ev.type === 'tool_call' || ev.type === 'tool_result' || ev.type === 'approval_required') {
      patchLastEvents((events) => [...events, ev])
    } else if (ev.type === 'error') {
      setError(ev.error || 'Agent 出错')
    }
  }

  const ask = async (question: string) => {
    const q = question.trim()
    if (!q || pending) return
    setError('')
    setInput('')
    let sid = sessionId
    if (sid === null) {
      try {
        const { session } = await api.createChat({ account_id: accountId })
        sid = session.id
        setSessionId(session.id)
      } catch (err) {
        setError((err as Error).message || '创建会话失败')
        return
      }
    }
    const history = messages
      .filter((m) => m.content)
      .slice(-6)
      .map((m) => ({ role: m.role, content: m.content }))
    setMessages((m) => [...m, { role: 'user', content: q }, { role: 'assistant', content: '', events: [] }])
    setPending(true)
    let received = false
    try {
      await streamAgentEvents(
        '/api/ai/agent/stream',
        {
          question: q,
          history,
          account_ids: accountId ? [accountId] : [],
          mode,
          session_id: sid ?? undefined,
          profile_id: profileId || undefined,
        },
        (ev) => {
          received = true
          handleAgentEvent(ev as unknown as AgentEvent)
        },
      )
      queryClient.invalidateQueries({ queryKey: ['chats'] })
      queryClient.invalidateQueries({ queryKey: ['emails'] })
      queryClient.invalidateQueries({ queryKey: ['user-drafts'] })
      queryClient.invalidateQueries({ queryKey: ['accounts'] })
    } catch (err) {
      setError((err as Error).message || '请求失败')
      if (!received) setMessages((m) => m.slice(0, -1))
      queryClient.invalidateQueries({ queryKey: ['chats'] })
    } finally {
      setPending(false)
    }
  }

  const decide = async (actionId: number, decision: 'approve' | 'reject') => {
    patchLastEvents((events) => events.map((e) =>
      e.action_id === actionId ? { ...e, status: decision === 'approve' ? '执行中…' : '已拒绝' } : e))
    try {
      const result = await api.agentDecide(actionId, decision)
      patchLastEvents((events) => events.map((e) =>
        e.action_id === actionId
          ? { ...e, status: (result.status ?? decision) as string, summary: result.summary ?? result.error }
          : e))
      queryClient.invalidateQueries({ queryKey: ['emails'] })
      queryClient.invalidateQueries({ queryKey: ['user-drafts'] })
      queryClient.invalidateQueries({ queryKey: ['accounts'] })
    } catch (err) {
      setError((err as Error).message || '审批请求失败')
      patchLastEvents((events) => events.map((e) =>
        e.action_id === actionId ? { ...e, status: '失败' } : e))
    }
  }

  const undoAction = async (actionId: number) => {
    try {
      const result = await api.agentUndo(actionId)
      patchLastEvents((events) => events.map((e) =>
        e.action_id === actionId
          ? { ...e, status: result.error ? e.status : '已撤销', summary: result.error ?? `已撤销（${result.undone} 项）` }
          : e))
      queryClient.invalidateQueries({ queryKey: ['emails'] })
      queryClient.invalidateQueries({ queryKey: ['accounts'] })
    } catch (err) {
      setError((err as Error).message || '撤销失败')
    }
  }

  const togglePin = async (session: ChatSession) => {
    try {
      await api.updateChat(session.id, { pinned: !session.pinned })
      queryClient.invalidateQueries({ queryKey: ['chats'] })
    } catch (err) {
      setError((err as Error).message || '操作失败')
    }
  }

  const renameSession = async (session: ChatSession) => {
    const title = prompt('重命名会话', session.title)?.trim()
    if (!title || title === session.title) return
    try {
      await api.updateChat(session.id, { title })
      queryClient.invalidateQueries({ queryKey: ['chats'] })
    } catch (err) {
      setError((err as Error).message || '重命名失败')
    }
  }

  const removeSession = async (session: ChatSession) => {
    if (!confirm(`删除会话「${session.title}」？不可恢复。`)) return
    try {
      await api.deleteChat(session.id)
      queryClient.invalidateQueries({ queryKey: ['chats'] })
      if (sessionId === session.id) {
        setSessionId(null)
        setMessages([])
      }
    } catch (err) {
      setError((err as Error).message || '删除失败')
    }
  }

  const switchMode = (next: 'approval' | 'auto') => {
    if (next === mode) return
    if (next === 'auto' && !confirm(
      '切换到自动模式？写操作（移动/归档/发送等）将在账号授权与安全约束内直接执行、不再逐条审批：\n'
      + '· 发送仅限通讯录与历史往来中的收件人，每日限 20 封\n'
      + '· 全部动作留痕，可在 设置-AI 用量-操作记录 查看/撤销\n'
      + '确认切换？',
    )) return
    setMode(next)
    localStorage.setItem('nmail_agent_mode', next)
  }

  return (
    <div className="flex h-full">
      {!aiEnabled && (
        <div className="absolute inset-x-0 top-0 z-10 border-b border-amber-200 bg-amber-50 px-4 py-2 text-center t-sm text-amber-800">
          AI 功能已停用，可在「设置 - AI 配置」重新开启
        </div>
      )}
      {/* 会话历史栏 */}
      <aside className="flex w-56 shrink-0 flex-col border-r border-gray-100 bg-gray-50/60">
        <div className="flex items-center justify-between px-3 py-3">
          <span className="t-sm font-medium text-gray-500">对话历史</span>
          <button
            className="flex items-center gap-1 rounded-lg border border-violet-200 bg-white px-2 py-1 t-xs text-violet-700 hover:bg-violet-50"
            onClick={startNewChat}
            disabled={pending}
          >
            <Plus className="h-3 w-3" /> 新对话
          </button>
        </div>
        <div className="min-h-0 flex-1 space-y-1 overflow-y-auto px-2 pb-3">
          {sessions.length === 0 && (
            <p className="px-2 py-4 t-xs leading-relaxed text-gray-400">
              还没有历史对话。发第一条消息后自动保存，仅供本机查看。
            </p>
          )}
          {sessions.map((s) => (
            <div
              key={s.id}
              className={`group relative cursor-pointer rounded-lg px-2.5 py-2 transition-colors ${
                s.id === sessionId ? 'bg-violet-100/80' : 'hover:bg-white'
              }`}
              onClick={() => openSession(s)}
            >
              <div className="flex items-center gap-1 pr-10">
                {s.pinned && <Pin className="h-3 w-3 shrink-0 text-violet-500" />}
                <span className="truncate t-sm text-gray-700">{s.title}</span>
              </div>
              <div className="mt-0.5 t-xs text-gray-400">
                {relativeTime(s.updated_at)}
                {s.message_count ? ` · ${s.message_count} 条` : ''}
              </div>
              <div className="absolute right-1.5 top-1.5 hidden items-center gap-0.5 rounded-md bg-white p-0.5 shadow-sm group-hover:flex">
                <button
                  className="rounded p-1 text-gray-400 hover:bg-violet-50 hover:text-violet-600"
                  title={s.pinned ? '取消置顶' : '置顶'}
                  onClick={(e) => { e.stopPropagation(); togglePin(s) }}
                >
                  {s.pinned ? <PinOff className="h-3 w-3" /> : <Pin className="h-3 w-3" />}
                </button>
                <button
                  className="rounded p-1 text-gray-400 hover:bg-violet-50 hover:text-violet-600"
                  title="重命名"
                  onClick={(e) => { e.stopPropagation(); renameSession(s) }}
                >
                  <Pencil className="h-3 w-3" />
                </button>
                <button
                  className="rounded p-1 text-gray-400 hover:bg-red-50 hover:text-red-500"
                  title="删除"
                  onClick={(e) => { e.stopPropagation(); removeSession(s) }}
                >
                  <Trash2 className="h-3 w-3" />
                </button>
              </div>
            </div>
          ))}
        </div>
      </aside>

      {/* 对话区 */}
      <div className="mx-auto flex h-full min-w-0 max-w-3xl flex-1 flex-col px-6">
        <div className="flex items-center justify-between py-4">
          <h1 className="flex items-center gap-2 t-md font-semibold text-violet-700">
            <Sparkles className="h-4 w-4" /> AI 总管家
          </h1>
          <div className="flex items-center gap-2 t-sm text-gray-500">
            {profiles.length > 1 && (
              <select
                className="rounded-lg border border-gray-300 px-2 py-1 t-sm outline-none focus:border-violet-500"
                value={profileId}
                onChange={(e) => setProfileId(e.target.value)}
                title="本次对话使用的 AI 配置"
              >
                <option value="">跟随使用中</option>
                {profiles.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name === p.model ? p.name : `${p.name}（${p.model}）`}
                  </option>
                ))}
              </select>
            )}
            <select
              className="rounded-lg border border-gray-300 px-2 py-1 t-sm outline-none focus:border-violet-500"
              value={accountId ?? ''}
              onChange={(e) => setAccountId(e.target.value ? Number(e.target.value) : null)}
            >
              <option value="">全部账号</option>
              {accounts.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.email}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* 模式开关（§6.4）：审批=写操作逐条批准；自动=授权与安全约束内直执行 */}
        <div className="flex items-center gap-2 pb-2">
          <div className="flex rounded-lg bg-gray-100 p-0.5">
            {(['approval', 'auto'] as const).map((m) => (
              <button
                key={m}
                className={`rounded-md px-3 py-1 t-sm transition-colors ${
                  mode === m
                    ? m === 'auto' ? 'bg-amber-500 font-medium text-white shadow-sm' : 'bg-white font-medium text-violet-700 shadow-sm'
                    : 'text-gray-500 hover:text-gray-800'
                }`}
                onClick={() => switchMode(m)}
                title={m === 'approval' ? '写操作逐条审批后执行（默认）' : '写操作在账号授权与安全约束内直接执行，全部留痕'}
              >
                {m === 'approval' ? '审批模式' : '自动模式'}
              </button>
            ))}
          </div>
          <span className="t-xs text-gray-400">
            {mode === 'approval'
              ? '读操作直接执行；移动/归档/发送等会先给你确认'
              : '写操作直接执行：收件人限通讯录与历史往来，每日发送 ≤20 封，全部留痕可撤销'}
          </span>
        </div>

        <div ref={scrollRef} className="min-h-0 flex-1 space-y-3 overflow-y-auto pb-4">
          {messages.length === 0 && !pending && (
            <div className="rounded-2xl border border-dashed border-violet-200 bg-violet-50/40 p-6">
              <p className="t-sm leading-relaxed text-gray-500">
                我是你的邮件总管家：可以查邮件、总结、整理归档、起草回复、发送邮件。
                范围：{accountId ? accounts.find((a) => a.id === accountId)?.email ?? '指定账号' : '全部账号'} · {mode === 'auto' ? '自动模式' : '审批模式'}。
              </p>
              <div className="mt-3 space-y-2">
                {QUICK_PROMPTS.map((q) => (
                  <button
                    key={q}
                    className="block w-full rounded-lg border border-violet-200 bg-white px-3 py-2 text-left t-sm text-violet-700 hover:bg-violet-50"
                    onClick={() => ask(q)}
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )}
          {messages.map((m, i) => {
            const isLast = i === messages.length - 1
            if (m.role === 'user') {
              return (
                <div key={i} className="flex justify-end">
                  <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl bg-violet-600 px-3.5 py-2.5 t-md leading-relaxed text-white">
                    {m.content}
                  </div>
                </div>
              )
            }
            // 回复中且该条还没有内容 → 打字指示
            if (isLast && pending && m.content === '' && !(m.events ?? []).length) {
              return (
                <div key={i} className="flex justify-start">
                  <div className="flex items-center gap-2 rounded-2xl bg-gray-100 px-3.5 py-2.5 t-sm text-gray-500">
                    <Loader2 className="h-3.5 w-3.5 animate-spin" /> 正在思考与调用工具…
                  </div>
                </div>
              )
            }
            return (
              <div key={i} className="flex justify-start">
                <div className="max-w-[90%] space-y-2">
                  {(m.events ?? []).map((ev, j) => (
                    <EventCard key={`${i}-${j}`} ev={ev as AgentEvent & { status?: string }} onDecide={decide} onUndo={undoAction} />
                  ))}
                  {m.content && (
                    <div className="rounded-2xl bg-gray-100 px-3.5 py-2.5 t-md text-gray-800">
                      <Markdown text={m.content} />
                    </div>
                  )}
                </div>
              </div>
            )
          })}
          {error && (
            <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 t-sm text-red-600">
              {error}
            </div>
          )}
        </div>

        <div className="border-t border-gray-100 py-3">
          <div className="flex items-center gap-2">
            <input
              className="flex-1 rounded-lg border border-gray-300 px-3 py-2 t-md outline-none focus:border-violet-500 focus:ring-2 focus:ring-violet-100"
              placeholder="吩咐一句，比如「把上周的营销邮件归档，然后给老张回一封」"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && ask(input)}
              disabled={pending}
            />
            <button
              className="rounded-lg bg-violet-600 p-2 text-white hover:bg-violet-700 disabled:opacity-50"
              onClick={() => ask(input)}
              disabled={pending || !input.trim()}
            >
              <Send className="h-4 w-4" />
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

/** 工具调用/结果/审批动作卡。 */
function EventCard({ ev, onDecide, onUndo }: {
  ev: AgentEvent & { status?: string }
  onDecide: (id: number, d: 'approve' | 'reject') => void
  onUndo: (id: number) => void
}) {
  const argsBrief = Object.entries(ev.args ?? {})
    .map(([k, v]) => `${k}=${typeof v === 'object' ? JSON.stringify(v) : String(v)}`)
    .slice(0, 4)
    .join('　')

  if (ev.type === 'approval_required') {
    const st = ev.status
    return (
      <div className="rounded-xl border border-amber-300 bg-amber-50 px-3 py-2.5">
        <div className="flex items-center gap-2">
          <ShieldAlert className="h-4 w-4 shrink-0 text-amber-600" />
          <span className="t-sm font-medium text-amber-800">待批准：{ev.tool}</span>
          {st && <span className={`ml-auto t-xs ${st === '已拒绝' || st === '失败' ? 'text-red-500' : 'text-gray-500'}`}>{st}</span>}
        </div>
        {argsBrief && <div className="mt-1 break-all t-xs text-gray-600">{argsBrief}</div>}
        {ev.reason && <div className="mt-1 t-xs text-amber-700">原因：{ev.reason}</div>}
        {!st && (
          <div className="mt-2 flex gap-1.5">
            <button
              className="inline-flex items-center gap-1 rounded-lg bg-emerald-600 px-2.5 py-1 t-sm font-medium text-white hover:bg-emerald-700"
              onClick={() => onDecide(ev.action_id!, 'approve')}
            >
              <Check className="h-3.5 w-3.5" /> 批准执行
            </button>
            <button
              className="inline-flex items-center gap-1 rounded-lg border border-gray-300 bg-white px-2.5 py-1 t-sm text-gray-600 hover:text-red-600"
              onClick={() => onDecide(ev.action_id!, 'reject')}
            >
              <X className="h-3.5 w-3.5" /> 拒绝
            </button>
          </div>
        )}
      </div>
    )
  }

  if (ev.type === 'tool_call') {
    return (
      <div className="flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-2.5 py-1.5 t-xs text-gray-500">
        <Wrench className="h-3.5 w-3.5 shrink-0 text-violet-400" />
        <span className="shrink-0 font-medium text-gray-700">{ev.tool}</span>
        {argsBrief && <span className="min-w-0 truncate">{argsBrief}</span>}
      </div>
    )
  }

  if (ev.type === 'tool_result') {
    const status = ev.status
    const undone = status === '已撤销'
    return (
      <div className={`flex items-center gap-2 rounded-lg border px-2.5 py-1.5 t-xs ${
        ev.ok ? 'border-emerald-200 bg-emerald-50/60 text-emerald-700' : 'border-red-200 bg-red-50/60 text-red-600'
      }`}>
        {ev.ok ? <Check className="h-3.5 w-3.5 shrink-0" /> : <X className="h-3.5 w-3.5 shrink-0" />}
        <span className="shrink-0 font-medium">{ev.tool}</span>
        <span className="min-w-0 flex-1 truncate">{ev.summary || status}</span>
        {ev.action_id != null && !undone && !status && (
          <button
            className="inline-flex shrink-0 items-center gap-0.5 rounded border border-gray-200 bg-white px-1.5 py-0.5 text-gray-500 hover:text-indigo-600"
            title="撤销该操作（发送不可撤销）"
            onClick={() => onUndo(ev.action_id!)}
          >
            <Undo2 className="h-3 w-3" /> 撤销
          </button>
        )}
        {undone && <Undo2 className="h-3 w-3 shrink-0" />}
      </div>
    )
  }
  return null
}
