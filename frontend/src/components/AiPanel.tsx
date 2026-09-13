import { useQuery } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { Loader2, Send, Sparkles, X } from 'lucide-react'
import { api } from '../api/client'
import { streamChat } from '../api/stream'
import type { EmailDetail } from '../types'
import Markdown from './Markdown'

interface AiPanelProps {
  email: EmailDetail
  onClose: () => void
}

interface ChatMsg {
  role: 'user' | 'assistant'
  content: string
}

const QUICK_PROMPTS = ['总结这封邮件', '翻译成中文', '提取关键信息（日期、金额、要求）']

export default function AiPanel({ email, onClose }: AiPanelProps) {
  const [messages, setMessages] = useState<ChatMsg[]>([])
  const [input, setInput] = useState('')
  const [profileId, setProfileId] = useState('')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')
  const scrollRef = useRef<HTMLDivElement>(null)

  const profilesQuery = useQuery({ queryKey: ['ai-profiles'], queryFn: api.getAIProfiles })
  const profiles = profilesQuery.data?.profiles ?? []

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight })
  }, [messages, pending])

  const ask = async (question: string) => {
    const q = question.trim()
    if (!q || pending) return
    setError('')
    const history = messages.slice(-6)
    setMessages((m) => [...m, { role: 'user', content: q }, { role: 'assistant', content: '' }])
    setInput('')
    setPending(true)
    let received = false
    try {
      await streamChat(
        '/api/ai/chat/stream',
        { email_id: email.id, question: q, history, profile_id: profileId || undefined },
        (delta) => {
          received = true
          setMessages((m) => {
            const next = [...m]
            next[next.length - 1] = { role: 'assistant', content: next[next.length - 1].content + delta }
            return next
          })
        },
      )
    } catch (err) {
      setError((err as Error).message || '请求失败')
      if (!received) setMessages((m) => m.slice(0, -1))
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="fixed inset-y-0 right-0 z-30 flex w-96 flex-col border-l border-gray-200 bg-white shadow-2xl">
      <div className="flex items-center justify-between gap-2 border-b border-gray-100 px-4 py-3">
        <span className="flex shrink-0 items-center gap-2 t-md font-semibold text-violet-700">
          <Sparkles className="h-4 w-4" /> AI 助手
        </span>
        {profiles.length > 1 && (
          <select
            className="rounded-lg border border-gray-300 px-1.5 py-1 t-xs outline-none focus:border-violet-500"
            value={profileId}
            onChange={(e) => setProfileId(e.target.value)}
            title="本次对话使用的 AI 配置"
          >
            <option value="">默认模型</option>
            {profiles.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        )}
        <button onClick={onClose} className="text-gray-400 hover:text-gray-700">
          <X className="h-5 w-5" />
        </button>
      </div>

      <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto p-4">
        {messages.length === 0 && !pending && (
          <div className="space-y-2">
            <p className="t-sm leading-relaxed text-gray-400">
              基于当前邮件（{email.subject || '无主题'}）向 AI 提问：
            </p>
            {QUICK_PROMPTS.map((q) => (
              <button
                key={q}
                className="block w-full rounded-lg border border-violet-200 bg-violet-50 px-3 py-2 text-left t-sm text-violet-700 hover:bg-violet-100"
                onClick={() => ask(q)}
              >
                {q}
              </button>
            ))}
          </div>
        )}
        {messages.map((m, i) => {
          const isLast = i === messages.length - 1
          if (m.role === 'user') {
            return (
              <div key={i} className="flex justify-end">
                <div className="min-w-0 max-w-[85%] wrap-anywhere whitespace-pre-wrap rounded-2xl bg-violet-600 px-3 py-2 t-sm leading-relaxed text-white">
                  {m.content}
                </div>
              </div>
            )
          }
          if (isLast && pending && m.content === '') {
            return (
              <div key={i} className="flex justify-start">
                <div className="flex items-center gap-2 rounded-2xl bg-gray-100 px-3 py-2 t-sm text-gray-500">
                  <Loader2 className="h-3.5 w-3.5 animate-spin" /> 思考中…
                </div>
              </div>
            )
          }
          return (
            <div key={i} className="flex justify-start">
              <div className="min-w-0 max-w-[90%] rounded-2xl bg-gray-100 px-3 py-2 t-sm text-gray-800">
                <Markdown text={m.content} />
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

      <div className="border-t border-gray-100 p-3">
        <div className="flex items-center gap-2">
          <input
            className="flex-1 rounded-lg border border-gray-300 px-3 py-2 t-sm outline-none focus:border-violet-500 focus:ring-2 focus:ring-violet-100"
            placeholder="问点什么…"
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
  )
}
