import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2, Pencil, Pin, PinOff, Plus, Send, Sparkles, Trash2 } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import { useAIEnabled } from '../api/useAI'
import { streamChat } from '../api/stream'
import Markdown from '../components/Markdown'
import type { Account, ChatSession } from '../types'

interface ChatMsg {
  role: 'user' | 'assistant'
  content: string
}

const QUICK_PROMPTS = [
  '最近有什么重要邮件需要我注意？',
  '有没有我漏回的邮件？',
  '总结一下各账号的情况',
  '这周收到过哪些验证码？',
]

/** 后端 datetime('now') 为无时区标记的 UTC，补 Z 后按本地时间展示。 */
function relativeTime(value: string): string {
  const ts = new Date(value.includes('T') ? value : value.replace(' ', 'T') + 'Z').getTime()
  if (Number.isNaN(ts)) return value
  const min = Math.floor((Date.now() - ts) / 60000)
  if (min < 1) return '刚刚'
  if (min < 60) return `${min} 分钟前`
  const hour = Math.floor(min / 60)
  if (hour < 24) return `${hour} 小时前`
  const day = Math.floor(hour / 24)
  if (day < 7) return `${day} 天前`
  return value.slice(0, 10)
}

/** 「AI 总管家」：基于最近邮件全量上下文的全局对话入口（流式 + Markdown + 历史会话）。 */
export default function ManagerPage() {
  const [sessionId, setSessionId] = useState<number | null>(null)
  const [messages, setMessages] = useState<ChatMsg[]>([])
  const [input, setInput] = useState('')
  const [accountId, setAccountId] = useState<number | null>(null)
  const [days, setDays] = useState(7)
  const [profileId, setProfileId] = useState<string>('')
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

  const ask = async (question: string) => {
    const q = question.trim()
    if (!q || pending) return
    setError('')
    setInput('')
    // 首条消息时才真正建会话，避免留下空会话
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
    setMessages((m) => [...m, { role: 'user', content: q }, { role: 'assistant', content: '' }])
    setPending(true)
    let received = false
    try {
      await streamChat(
        '/api/ai/chat-manager/stream',
        {
          question: q,
          history: messages.slice(-6),
          account_id: accountId ?? undefined,
          days,
          session_id: sid ?? undefined,
          profile_id: profileId || undefined,
        },
        (delta) => {
          received = true
          setMessages((m) => {
            const next = [...m]
            next[next.length - 1] = { role: 'assistant', content: next[next.length - 1].content + delta }
            return next
          })
        },
      )
      queryClient.invalidateQueries({ queryKey: ['chats'] })
    } catch (err) {
      setError((err as Error).message || '请求失败')
      if (!received) {
        setMessages((m) => m.slice(0, -1)) // 移除空的占位回复
      }
      queryClient.invalidateQueries({ queryKey: ['chats'] })
    } finally {
      setPending(false)
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
          <span className="text-xs font-medium text-gray-500">对话历史</span>
          <button
            className="flex items-center gap-1 rounded-lg border border-violet-200 bg-white px-2 py-1 text-[11px] text-violet-700 hover:bg-violet-50"
            onClick={startNewChat}
            disabled={pending}
          >
            <Plus className="h-3 w-3" /> 新对话
          </button>
        </div>
        <div className="min-h-0 flex-1 space-y-1 overflow-y-auto px-2 pb-3">
          {sessions.length === 0 && (
            <p className="px-2 py-4 text-[11px] leading-relaxed text-gray-400">
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
                <span className="truncate text-xs text-gray-700">{s.title}</span>
              </div>
              <div className="mt-0.5 text-[10px] text-gray-400">
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
          <h1 className="flex items-center gap-2 text-base font-semibold text-violet-700">
            <Sparkles className="h-4 w-4" /> AI 总管家
          </h1>
          <div className="flex items-center gap-2 text-xs text-gray-500">
            {profiles.length > 1 && (
              <select
                className="rounded-lg border border-gray-300 px-2 py-1 text-xs outline-none focus:border-violet-500"
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
              className="rounded-lg border border-gray-300 px-2 py-1 text-xs outline-none focus:border-violet-500"
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
            <select
              className="rounded-lg border border-gray-300 px-2 py-1 text-xs outline-none focus:border-violet-500"
              value={days}
              onChange={(e) => setDays(Number(e.target.value))}
            >
              <option value={7}>最近 7 天</option>
              <option value={30}>最近 30 天</option>
              <option value={90}>最近 90 天</option>
            </select>
          </div>
        </div>

        <div ref={scrollRef} className="min-h-0 flex-1 space-y-3 overflow-y-auto pb-4">
          {messages.length === 0 && !pending && (
            <div className="rounded-2xl border border-dashed border-violet-200 bg-violet-50/40 p-6">
              <p className="text-xs leading-relaxed text-gray-500">
                我是你的邮件总管家，基于你选择的范围（{accountId ? '指定账号' : '全部账号'} · 最近 {days} 天）
                的邮件回答问题。
              </p>
              <div className="mt-3 space-y-2">
                {QUICK_PROMPTS.map((q) => (
                  <button
                    key={q}
                    className="block w-full rounded-lg border border-violet-200 bg-white px-3 py-2 text-left text-xs text-violet-700 hover:bg-violet-50"
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
                  <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl bg-violet-600 px-3.5 py-2.5 text-[13px] leading-relaxed text-white">
                    {m.content}
                  </div>
                </div>
              )
            }
            // 回复中且该条还没有内容 → 打字指示
            if (isLast && pending && m.content === '') {
              return (
                <div key={i} className="flex justify-start">
                  <div className="flex items-center gap-2 rounded-2xl bg-gray-100 px-3.5 py-2.5 text-xs text-gray-500">
                    <Loader2 className="h-3.5 w-3.5 animate-spin" /> 正在翻你的邮件…
                  </div>
                </div>
              )
            }
            return (
              <div key={i} className="flex justify-start">
                <div className="max-w-[90%] rounded-2xl bg-gray-100 px-3.5 py-2.5 text-[13px] text-gray-800">
                  <Markdown text={m.content} />
                </div>
              </div>
            )
          })}
          {error && (
            <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-600">
              {error}
            </div>
          )}
        </div>

        <div className="border-t border-gray-100 py-3">
          <div className="flex items-center gap-2">
            <input
              className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-[13px] outline-none focus:border-violet-500 focus:ring-2 focus:ring-violet-100"
              placeholder="问问你的邮箱…"
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
