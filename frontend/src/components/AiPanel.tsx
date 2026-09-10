import { useEffect, useRef, useState } from 'react'
import { Loader2, Send, Sparkles, X } from 'lucide-react'
import { api } from '../api/client'
import type { EmailDetail } from '../types'

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
  const [busy, setBusy] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight })
  }, [messages, busy])

  const ask = async (question: string) => {
    const q = question.trim()
    if (!q || busy) return
    const history = messages.slice(-6)
    setMessages((m) => [...m, { role: 'user', content: q }])
    setInput('')
    setBusy(true)
    try {
      const { answer } = await api.aiChat({
        email_id: email.id,
        question: q,
        history: history.map((m) => ({ role: m.role, content: m.content })),
      })
      setMessages((m) => [...m, { role: 'assistant', content: answer }])
    } catch (err) {
      setMessages((m) => [...m, { role: 'assistant', content: `出错了：${(err as Error).message}` }])
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-y-0 right-0 z-30 flex w-96 flex-col border-l border-gray-200 bg-white shadow-2xl">
      <div className="flex items-center justify-between border-b border-gray-100 px-4 py-3">
        <span className="flex items-center gap-2 text-sm font-semibold text-violet-700">
          <Sparkles className="h-4 w-4" /> AI 助手 · 本封邮件
        </span>
        <button onClick={onClose} className="text-gray-400 hover:text-gray-700">
          <X className="h-5 w-5" />
        </button>
      </div>

      <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto p-4">
        {messages.length === 0 && (
          <div className="space-y-2">
            <p className="text-xs leading-relaxed text-gray-400">
              基于当前邮件（{email.subject || '无主题'}）向 AI 提问：
            </p>
            {QUICK_PROMPTS.map((q) => (
              <button
                key={q}
                className="block w-full rounded-lg border border-violet-200 bg-violet-50 px-3 py-2 text-left text-xs text-violet-700 hover:bg-violet-100"
                onClick={() => ask(q)}
              >
                {q}
              </button>
            ))}
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div
              className={`max-w-[85%] whitespace-pre-wrap rounded-2xl px-3 py-2 text-xs leading-relaxed ${
                m.role === 'user'
                  ? 'bg-indigo-600 text-white'
                  : 'bg-gray-100 text-gray-800'
              }`}
            >
              {m.content}
            </div>
          </div>
        ))}
        {busy && (
          <div className="flex justify-start">
            <div className="flex items-center gap-2 rounded-2xl bg-gray-100 px-3 py-2 text-xs text-gray-500">
              <Loader2 className="h-3.5 w-3.5 animate-spin" /> 思考中…
            </div>
          </div>
        )}
      </div>

      <div className="border-t border-gray-100 p-3">
        <div className="flex items-center gap-2">
          <input
            className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-xs outline-none focus:border-violet-500 focus:ring-2 focus:ring-violet-100"
            placeholder="问点什么…"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && ask(input)}
            disabled={busy}
          />
          <button
            className="rounded-lg bg-violet-600 p-2 text-white hover:bg-violet-700 disabled:opacity-50"
            onClick={() => ask(input)}
            disabled={busy || !input.trim()}
          >
            <Send className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  )
}
