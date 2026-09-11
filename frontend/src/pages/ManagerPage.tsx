import { useMutation, useQuery } from '@tanstack/react-query'
import { Loader2, Send, Sparkles } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import type { Account } from '../types'

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

/** 「AI 总管家」：基于最近邮件全量上下文的全局对话入口。 */
export default function ManagerPage() {
  const [messages, setMessages] = useState<ChatMsg[]>([])
  const [input, setInput] = useState('')
  const [accountId, setAccountId] = useState<number | null>(null)
  const [days, setDays] = useState(7)
  const scrollRef = useRef<HTMLDivElement>(null)

  const accountsQuery = useQuery({ queryKey: ['accounts'], queryFn: api.getAccounts })
  const accounts: Account[] = accountsQuery.data?.accounts ?? []

  const chatMutation = useMutation({
    mutationFn: (question: string) =>
      api.aiManagerChat({
        question,
        history: messages.slice(-6).map((m) => ({ role: m.role, content: m.content })),
        account_id: accountId ?? undefined,
        days,
      }),
    onSuccess: (result) => {
      setMessages((m) => [...m, { role: 'assistant', content: result.answer }])
    },
  })

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight })
  }, [messages, chatMutation.isPending])

  const ask = (question: string) => {
    const q = question.trim()
    if (!q || chatMutation.isPending) return
    setMessages((m) => [...m, { role: 'user', content: q }])
    setInput('')
    chatMutation.mutate(q)
  }

  return (
    <div className="mx-auto flex h-full max-w-3xl flex-col px-6">
      <div className="flex items-center justify-between py-4">
        <h1 className="flex items-center gap-2 text-base font-semibold text-violet-700">
          <Sparkles className="h-4 w-4" /> AI 总管家
        </h1>
        <div className="flex items-center gap-2 text-xs text-gray-500">
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
        {messages.length === 0 && (
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
        {messages.map((m, i) => (
          <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div
              className={`max-w-[85%] whitespace-pre-wrap rounded-2xl px-3.5 py-2.5 text-[13px] leading-relaxed ${
                m.role === 'user' ? 'bg-violet-600 text-white' : 'bg-gray-100 text-gray-800'
              }`}
            >
              {m.content}
            </div>
          </div>
        ))}
        {chatMutation.isPending && (
          <div className="flex justify-start">
            <div className="flex items-center gap-2 rounded-2xl bg-gray-100 px-3.5 py-2.5 text-xs text-gray-500">
              <Loader2 className="h-3.5 w-3.5 animate-spin" /> 正在翻你的邮件…
            </div>
          </div>
        )}
        {chatMutation.isError && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-600">
            {(chatMutation.error as Error).message}
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
            disabled={chatMutation.isPending}
          />
          <button
            className="rounded-lg bg-violet-600 p-2 text-white hover:bg-violet-700 disabled:opacity-50"
            onClick={() => ask(input)}
            disabled={chatMutation.isPending || !input.trim()}
          >
            <Send className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  )
}
