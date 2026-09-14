import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Check, ChevronDown, Clock, Loader2, Pencil, Pin, PinOff, Plus, Send, ShieldAlert,
  Sparkles, Square, Trash2, Undo2, X,
} from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import { useAIEnabled } from '../api/useAI'
import { streamAgentEvents } from '../api/stream'
import { relativeTime } from '../utils/format'
import Markdown from '../components/Markdown'
import SplitDivider from '../components/SplitDivider'
import { appZoom, usePanelWidth } from '../hooks/usePanelWidth'
import type { Account, AgentEvent, AgentSegment, ChatSession } from '../types'

interface ChatMsg {
  role: 'user' | 'assistant'
  content: string
  segments?: AgentSegment[] // v0.4.x §17.4：结构化分段（过程/审批/文本），旧消息回落纯文本
}

/** 工具中文名（过程块展示用，模型协议名不直接暴露给用户） */
const TOOL_LABELS: Record<string, string> = {
  search_emails: '搜索邮件', list_recent_emails: '最近邮件', read_email: '读取邮件',
  list_folders: '查看文件夹', list_contacts: '查通讯录', digest_stats: '邮箱概况',
  mark_emails: '标记已读', star_emails: '星标', archive_emails: '归档',
  move_emails: '移动邮件', trash_emails: '删除邮件', create_folder: '新建文件夹',
  rename_folder: '重命名文件夹', delete_folder: '删除文件夹', set_category: '设置分类',
  create_draft: '起草邮件', update_draft: '修改草稿', schedule_draft: '定时发送',
  discard_draft: '丢弃草稿', send_draft: '发送邮件', start_organize: 'AI 整理',
  upsert_contact: '保存联系人', delete_contact: '删除联系人',
  add_sender_list: '加入名单', remove_sender_list: '移出名单',
}

const QUICK_PROMPTS = [
  '总结一下各账号的邮箱概况',
  '有没有我漏回的邮件？',
  '找一下最近一周来自银行的邮件',
  '把收件箱里的营销邮件都归档',
]

type RenderItem =
  | { type: 'text'; content: string }
  | { type: 'process'; steps: AgentSegment[] }
  | { type: 'approval'; seg: AgentSegment }
  | { type: 'error'; content: string }

/** 分段 → 渲染项：连续 step 合并为一个可折叠过程块（Claude Code 式，§17.4） */
function groupSegments(segs: AgentSegment[]): RenderItem[] {
  const items: RenderItem[] = []
  for (const seg of segs) {
    if (seg.kind === 'step') {
      if (seg.echo) continue // 续跑流回放的审批结果步（原消息已落定），不重复渲染
      const last = items[items.length - 1]
      if (last?.type === 'process') last.steps.push(seg)
      else items.push({ type: 'process', steps: [seg] })
    } else if (seg.kind === 'text') {
      if (seg.content?.trim()) items.push({ type: 'text', content: seg.content })
    } else if (seg.kind === 'approval') {
      items.push({ type: 'approval', seg })
    } else if (seg.kind === 'error') {
      items.push({ type: 'error', content: seg.content || '执行出错' })
    }
  }
  return items
}

/** 「AI 总管家」2.x（v0.4 P6 + §17 Agent 化）：对话 Agent——原生工具调用 +
 * 流式过程折叠 + 审批续跑不断链 + Stop/继续。会话持久化沿用原总管家。 */
export default function ManagerPage() {
  const [sessionId, setSessionId] = useState<number | null>(null)
  const [messages, setMessages] = useState<ChatMsg[]>([])
  const [input, setInput] = useState('')
  const [accountId, setAccountId] = useState<number | null>(null)
  const [profileId, setProfileId] = useState<string>('')
  const [mode, setMode] = useState<'approval' | 'auto'>(() =>
    localStorage.getItem('nmail_agent_mode') === 'auto' ? 'auto' : 'approval')
  const [pending, setPending] = useState(false)
  const [pausedRun, setPausedRun] = useState<{ runId: number; reason: string } | null>(null)
  const [error, setError] = useState('')
  const scrollRef = useRef<HTMLDivElement>(null)
  const runIdRef = useRef<number | null>(null) // 当前运行（审批决定后自动续跑）
  const abortRef = useRef<AbortController | null>(null)
  const seenActionIds = useRef<Set<number>>(new Set()) // 续跑回放去重
  const queryClient = useQueryClient()

  // 会话历史栏宽度可拖拽记忆（v0.4.x 浏览器式分栏），默认 224px = 原 w-56
  const { width: colWidth, setWidth: setColWidth, persist: persistColWidth, reset: resetColWidth } =
    usePanelWidth('nmail_manager_col_width', { min: 180, max: 360, fallback: 224 })
  const colRef = useRef<HTMLElement>(null)
  const moveColWidth = (e: MouseEvent) => {
    if (!colRef.current) return
    setColWidth((e.clientX - colRef.current.getBoundingClientRect().left) / appZoom())
  }

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
    setPausedRun(null)
    runIdRef.current = null
  }

  const openSession = async (session: ChatSession) => {
    if (pending || session.id === sessionId) return
    try {
      const data = await api.getChat(session.id)
      setSessionId(session.id)
      setMessages(data.messages.map((m) => ({
        role: m.role,
        content: m.content,
        segments: (m as { segments?: AgentSegment[] | null }).segments
          ?? [{ kind: 'text', content: m.content }], // 旧消息回落纯文本渲染
      })))
      setAccountId(data.session.account_id ?? null)
      setError('')
    } catch (err) {
      setError((err as Error).message || '加载会话失败')
    }
  }

  const patchLastSegments = (fn: (segs: AgentSegment[]) => AgentSegment[]) => {
    setMessages((m) => {
      const next = [...m]
      const last = next[next.length - 1]
      if (last?.role === 'assistant') {
        next[next.length - 1] = { ...last, segments: fn(last.segments ?? []) }
      }
      return next
    })
  }

  /** 就地更新某条分段（审批卡/步骤状态，跨任意消息查找 action_id） */
  const patchByActionId = (actionId: number, patch: (seg: AgentSegment) => AgentSegment) => {
    setMessages((m) => m.map((msg) => {
      if (msg.role !== 'assistant' || !msg.segments?.some((s) => s.action_id === actionId)) return msg
      return { ...msg, segments: msg.segments.map((s) => (s.action_id === actionId ? patch(s) : s)) }
    }))
  }

  const handleAgentEvent = (ev: AgentEvent) => {
    if (ev.type === 'run_started') {
      runIdRef.current = ev.run_id ?? null
    } else if (ev.type === 'text_delta') {
      patchLastSegments((segs) => {
        const last = segs[segs.length - 1]
        if (last?.kind === 'text') {
          return [...segs.slice(0, -1), { ...last, content: last.content + (ev.delta || '') }]
        }
        return [...segs, { kind: 'text', content: ev.delta || '' }]
      })
    } else if (ev.type === 'text') {
      // 全量事件：覆盖同轮流式累积（内容一致，幂等）
      patchLastSegments((segs) => {
        const last = segs[segs.length - 1]
        if (last?.kind === 'text') {
          return [...segs.slice(0, -1), { ...last, content: ev.text || last.content }]
        }
        return [...segs, { kind: 'text', content: ev.text || '' }]
      })
    } else if (ev.type === 'tool_call') {
      patchLastSegments((segs) => [...segs, {
        kind: 'step', tool: ev.tool, call_id: ev.call_id, args: ev.args, status: 'running',
      }])
    } else if (ev.type === 'tool_result') {
      patchLastSegments((segs) => {
        if (ev.action_id != null && seenActionIds.current.has(ev.action_id)) return segs
        if (ev.action_id != null) seenActionIds.current.add(ev.action_id)
        const next = [...segs]
        for (let i = next.length - 1; i >= 0; i--) {
          const s = next[i]
          if (s.kind !== 'step' || s.status === 'ok' || s.status === 'fail') continue
          const hit = ev.action_id != null ? s.action_id === ev.action_id : s.tool === ev.tool
          if (hit) {
            next[i] = { ...s, status: ev.ok ? 'ok' : 'fail', summary: ev.summary,
              action_id: ev.action_id ?? s.action_id }
            return next
          }
        }
        return [...next, { kind: 'step', tool: ev.tool, call_id: ev.call_id, args: {},
          status: ev.ok ? 'ok' : 'fail', summary: ev.summary, action_id: ev.action_id }]
      })
    } else if (ev.type === 'approval_required') {
      patchLastSegments((segs) => {
        const next = [...segs]
        for (let i = next.length - 1; i >= 0; i--) {
          const s = next[i]
          if (s.kind === 'step' && s.status === 'running' && s.tool === ev.tool) {
            next[i] = { ...s, status: 'waiting', action_id: ev.action_id }
            break
          }
        }
        next.push({ kind: 'approval', action_id: ev.action_id!, tool: ev.tool!,
          args: ev.args, reason: ev.reason, meta: ev.meta, run_id: ev.run_id })
        return next
      })
    } else if (ev.type === 'paused') {
      if (ev.reason === 'approval' && ev.run_id) runIdRef.current = ev.run_id
      else if (ev.run_id) setPausedRun({ runId: ev.run_id, reason: ev.reason || '' })
    } else if (ev.type === 'error') {
      patchLastSegments((segs) => [...segs, { kind: 'error', content: ev.error || '执行出错' }])
    }
  }

  const invalidateAfter = () => {
    queryClient.invalidateQueries({ queryKey: ['chats'] })
    queryClient.invalidateQueries({ queryKey: ['emails'] })
    queryClient.invalidateQueries({ queryKey: ['user-drafts'] })
    queryClient.invalidateQueries({ queryKey: ['accounts'] })
  }

  const runResume = async (runId: number) => {
    if (pending) return
    runIdRef.current = runId
    setPausedRun(null)
    setMessages((m) => [...m, { role: 'assistant', content: '', segments: [] }])
    setPending(true)
    abortRef.current = new AbortController()
    try {
      await streamAgentEvents('/api/ai/agent/resume', { run_id: runId },
        (ev) => handleAgentEvent(ev as unknown as AgentEvent), abortRef.current.signal)
      invalidateAfter()
    } catch (err) {
      if ((err as Error).name !== 'AbortError') {
        setError((err as Error).message || '续跑失败')
      }
      invalidateAfter()
    } finally {
      setPending(false)
    }
  }

  const ask = async (question: string) => {
    const q = question.trim()
    if (!q || pending) return
    setError('')
    setInput('')
    setPausedRun(null)
    seenActionIds.current = new Set()
    runIdRef.current = null
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
    setMessages((m) => [...m, { role: 'user', content: q }, { role: 'assistant', content: '', segments: [] }])
    setPending(true)
    abortRef.current = new AbortController()
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
        abortRef.current.signal,
      )
      invalidateAfter()
    } catch (err) {
      if ((err as Error).name !== 'AbortError') {
        setError((err as Error).message || '请求失败')
      }
      if (!received) setMessages((m) => m.slice(0, -1))
      queryClient.invalidateQueries({ queryKey: ['chats'] })
    } finally {
      setPending(false)
    }
  }

  const stop = () => {
    abortRef.current?.abort()
  }

  const decide = async (actionId: number, decision: 'approve' | 'reject', runId?: number) => {
    patchByActionId(actionId, (seg) => ({ ...seg, status: decision === 'approve' ? '执行中…' : '已拒绝' }))
    try {
      const result = await api.agentDecide(actionId, decision)
      const okRun = result.status === 'executed'
      const statusWord = okRun ? '已执行' : result.status === 'failed' ? '失败' : '已拒绝'
      patchByActionId(actionId, (seg) => seg.kind === 'approval'
        ? { ...seg, status: result.error ?? statusWord }
        : { ...seg, status: okRun ? 'ok' : 'fail', summary: result.summary ?? result.error })
      invalidateAfter()
      // 审批续跑（§17.2）：批准/拒绝都把结果回灌，Agent 自动继续，无需再发消息
      // run_id 以审批卡自身携带的为准（流结束后 runIdRef 仍指向它）
      const rid = runId ?? runIdRef.current
      if (rid) {
        await runResume(rid)
      }
    } catch (err) {
      setError((err as Error).message || '审批请求失败')
      patchByActionId(actionId, (seg) => ({ ...seg, status: seg.kind === 'approval' ? '失败' : seg.status }))
    }
  }

  const undoAction = async (actionId: number) => {
    try {
      const result = await api.agentUndo(actionId)
      patchByActionId(actionId, (seg) => ({ ...seg,
        status: result.error ? seg.status : 'ok',
        summary: result.error ?? `已撤销（${result.undone} 项）` }))
      invalidateAfter()
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
      setError((err as Error).message || '删除会话失败')
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
      <aside
        ref={colRef}
        style={{ width: colWidth }}
        className="flex shrink-0 flex-col bg-gray-50/60"
      >
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
      <SplitDivider
        onMove={moveColWidth}
        onReset={resetColWidth}
        onDragEnd={persistColWidth}
        title="拖拽调整历史栏宽度（双击复位）"
      />

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
              ? '读操作直接执行；移动/归档/发送等会先给你确认，批准后自动继续'
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
            if (m.role === 'user') {
              return (
                <div key={i} className="flex justify-end">
                  <div className="min-w-0 max-w-[85%] wrap-anywhere whitespace-pre-wrap rounded-2xl bg-violet-600 px-3.5 py-2.5 t-md leading-relaxed text-white">
                    {m.content}
                  </div>
                </div>
              )
            }
            const segs = m.segments ?? (m.content ? [{ kind: 'text' as const, content: m.content }] : [])
            const items = groupSegments(segs)
            const isLast = i === messages.length - 1
            if (isLast && pending && items.length === 0) {
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
                <div className="min-w-0 max-w-[90%] space-y-2">
                  {items.map((item, j) => {
                    if (item.type === 'text') {
                      return (
                        <div key={j} className="rounded-2xl bg-gray-100 px-3.5 py-2.5 t-md text-gray-800">
                          <Markdown text={item.content} />
                        </div>
                      )
                    }
                    if (item.type === 'process') {
                      return <ProcessBlock key={j} steps={item.steps} onUndo={undoAction} />
                    }
                    if (item.type === 'approval') {
                      return <ApprovalCard key={j} seg={item.seg} onDecide={decide} runId={item.seg.run_id} />
                    }
                    return (
                      <div key={j} className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 t-sm text-red-600">
                        {item.content}
                      </div>
                    )
                  })}
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

        {/* 步数/预算触顶：继续按钮（§17.2，用户点继续=新的一段预算） */}
        {pausedRun && !pending && (
          <div className="pb-2">
            <button
              className="w-full rounded-lg border border-violet-200 bg-violet-50 px-3 py-2 t-sm text-violet-700 transition-colors hover:bg-violet-100"
              onClick={() => runResume(pausedRun.runId)}
            >
              {pausedRun.reason === 'budget' ? '已到时间预算，任务未完成 — 点击继续执行' : '已达单轮步数上限，任务未完成 — 点击继续执行'}
            </button>
          </div>
        )}

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
            {pending ? (
              <button
                className="rounded-lg border border-gray-300 bg-white p-2 text-gray-500 hover:border-red-200 hover:text-red-500"
                title="停止执行（已完成部分保留）"
                onClick={stop}
              >
                <Square className="h-4 w-4" />
              </button>
            ) : (
              <button
                className="rounded-lg bg-violet-600 p-2 text-white hover:bg-violet-700 disabled:opacity-50"
                onClick={() => ask(input)}
                disabled={!input.trim()}
              >
                <Send className="h-4 w-4" />
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

/** 执行过程（Claude 式极简单行，§17.4 简化版）：运行中一行状态、完成后一行淡字、
 * 失败才醒目；点击才展开步骤明细，默认不占版面 */
function ProcessBlock({ steps, onUndo }: {
  steps: AgentSegment[]
  onUndo: (id: number) => void
}) {
  const running = steps.some((s) => s.status === 'running')
  const waiting = steps.some((s) => s.status === 'waiting')
  const failCount = steps.filter((s) => s.status === 'fail').length
  const doneCount = steps.filter((s) => s.status === 'ok' || s.status === 'fail').length
  const [open, setOpen] = useState(false)
  let head
  if (running) {
    head = (
      <>
        <Loader2 className="h-3 w-3 shrink-0 animate-spin text-violet-500" />
        <span className="text-gray-500">正在执行…{doneCount > 0 ? `（已 ${doneCount} 步）` : ''}</span>
      </>
    )
  } else if (failCount > 0) {
    head = (
      <>
        <X className="h-3 w-3 shrink-0 text-red-500" />
        <span className="text-red-500">执行过程 · {steps.length} 步 · {failCount} 步失败</span>
      </>
    )
  } else if (waiting) {
    head = (
      <>
        <Clock className="h-3 w-3 shrink-0 text-amber-500" />
        <span className="text-amber-600">待审批 · 已执行 {doneCount} 步</span>
      </>
    )
  } else {
    head = (
      <>
        <Check className="h-3 w-3 shrink-0 text-gray-300" />
        <span className="text-gray-400">已执行 {steps.length} 步</span>
      </>
    )
  }
  return (
    <div>
      <button
        className="group flex w-full items-center gap-1.5 py-0.5 t-xs"
        onClick={() => setOpen(!open)}
        title="查看执行明细"
      >
        {head}
        <ChevronDown className={`h-3 w-3 shrink-0 text-gray-300 transition-transform group-hover:text-gray-500 ${open ? '' : '-rotate-90'}`} />
      </button>
      {open && (
        <div className="mt-0.5 ml-2 border-l border-gray-200 pl-3">
          {steps.map((s, i) => <StepRow key={s.call_id ?? i} step={s} onUndo={onUndo} />)}
        </div>
      )}
    </div>
  )
}

/** 过程块单步行：点击展开参数与结果明细 */
function StepRow({ step, onUndo }: {
  step: AgentSegment
  onUndo: (id: number) => void
}) {
  const [open, setOpen] = useState(false)
  const argsBrief = Object.entries(step.args ?? {})
    .map(([k, v]) => `${k}=${typeof v === 'object' ? JSON.stringify(v) : String(v)}`)
    .slice(0, 3)
    .map((s) => (s.length > 48 ? `${s.slice(0, 48)}…` : s))
    .join('　')
  const undone = step.summary?.startsWith('已撤销')
  const statusIcon = step.status === 'running'
    ? <Loader2 className="h-3 w-3 shrink-0 animate-spin text-violet-500" />
    : step.status === 'waiting'
      ? <Clock className="h-3 w-3 shrink-0 text-amber-500" />
      : step.status === 'fail'
        ? <X className="h-3 w-3 shrink-0 text-red-500" />
        : <Check className="h-3 w-3 shrink-0 text-emerald-600" />
  return (
    <div className="py-1">
      <button className="flex w-full items-center gap-2 t-xs" onClick={() => setOpen(!open)}>
        {statusIcon}
        <span className="shrink-0 font-medium text-gray-700">{TOOL_LABELS[step.tool ?? ''] ?? step.tool}</span>
        {argsBrief && <span className="min-w-0 flex-1 truncate text-left text-gray-400">{argsBrief}</span>}
        {step.summary && (
          <span className={`max-w-[40%] shrink truncate text-right ${
            step.status === 'fail' ? 'text-red-500' : undone ? 'text-gray-400' : 'text-gray-500'
          }`}>
            {step.summary}
          </span>
        )}
        {step.status === 'ok' && step.action_id != null && !undone && (
          <span
            className="inline-flex shrink-0 items-center gap-0.5 rounded border border-gray-200 bg-white px-1.5 py-0.5 text-gray-500 hover:text-indigo-600"
            title="撤销该操作（发送不可撤销）"
            onClick={(e) => { e.stopPropagation(); onUndo(step.action_id!) }}
          >
            <Undo2 className="h-3 w-3" /> 撤销
          </span>
        )}
        {undone && <Undo2 className="h-3 w-3 shrink-0 text-gray-400" />}
      </button>
      {open && (
        <div className="mt-1 ml-6 rounded-lg bg-white px-2.5 py-1.5 t-xs text-gray-500">
          {Object.keys(step.args ?? {}).length > 0 && (
            <pre className="max-h-40 overflow-auto wrap-anywhere whitespace-pre-wrap text-left leading-relaxed">
              {JSON.stringify(step.args, null, 2)}
            </pre>
          )}
          {step.summary && <div className="mt-1">{step.summary}</div>}
        </div>
      )}
    </div>
  )
}

/** 审批动作卡（§6.5 + §17.6-5 影响明细）：独立醒目、不折叠；决定后由 Agent 自动续跑 */
function ApprovalCard({ seg, onDecide, runId }: {
  seg: AgentSegment
  onDecide: (id: number, d: 'approve' | 'reject', runId?: number) => void
  runId?: number
}) {
  const st = seg.status
  const meta = seg.meta ?? {}
  const argsBrief = Object.entries(seg.args ?? {})
    .map(([k, v]) => `${k}=${typeof v === 'object' ? JSON.stringify(v) : String(v)}`)
    .slice(0, 4)
    .join('　')
  return (
    <div className="rounded-xl border border-amber-300 bg-amber-50 px-3 py-2.5">
      <div className="flex items-center gap-2">
        <ShieldAlert className="h-4 w-4 shrink-0 text-amber-600" />
        <span className="t-sm font-medium text-amber-800">
          待批准：{TOOL_LABELS[seg.tool ?? ''] ?? seg.tool}
        </span>
        {st && (
          <span className={`ml-auto t-xs ${st === '已拒绝' || st === '失败' ? 'text-red-500' : 'text-gray-500'}`}>
            {st}
          </span>
        )}
      </div>
      {typeof meta.to === 'string' && (
        <div className="mt-1 t-xs text-gray-700">
          收件人 {meta.to}{typeof meta.subject === 'string' ? ` · 主题「${meta.subject}」` : ''}
        </div>
      )}
      {argsBrief && <div className="mt-1 break-all t-xs text-gray-600">{argsBrief}</div>}
      {typeof meta.affected_emails === 'number' && (
        <div className="mt-1 t-xs font-medium text-amber-700">
          影响 {meta.affected_emails} 封邮件
        </div>
      )}
      {Array.isArray(meta.titles) && meta.titles.length > 0 && (
        <div className="mt-1 max-h-28 space-y-0.5 overflow-y-auto rounded-lg bg-white/70 px-2 py-1.5 t-xs text-gray-500">
          {meta.titles.map((t, i) => <div key={i} className="truncate">· {String(t)}</div>)}
        </div>
      )}
      {typeof meta.warn === 'string' && <div className="mt-1 t-xs text-red-500">{meta.warn}</div>}
      {seg.reason && <div className="mt-1 t-xs text-amber-700">原因：{seg.reason}</div>}
      {!st && (
        <div className="mt-2 flex gap-1.5">
          <button
            className="inline-flex items-center gap-1 rounded-lg bg-emerald-600 px-2.5 py-1 t-sm font-medium text-white hover:bg-emerald-700"
            onClick={() => onDecide(seg.action_id!, 'approve', runId)}
          >
            <Check className="h-3.5 w-3.5" /> 批准执行
          </button>
          <button
            className="inline-flex items-center gap-1 rounded-lg border border-gray-300 bg-white px-2.5 py-1 t-sm text-gray-600 hover:text-red-600"
            onClick={() => onDecide(seg.action_id!, 'reject', runId)}
          >
            <X className="h-3.5 w-3.5" /> 拒绝
          </button>
        </div>
      )}
    </div>
  )
}
