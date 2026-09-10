import { useMutation } from '@tanstack/react-query'
import { Loader2, X } from 'lucide-react'
import { useRef, useState } from 'react'
import { api } from '../api/client'
import type { Account, EmailDetail } from '../types'

export interface ComposeInit {
  mode: 'reply' | 'replyAll' | 'forward' | 'new'
  base?: EmailDetail | null
}

const WRITE_OPS = [
  { key: 'polish', label: '润色' },
  { key: 'formal', label: '更正式' },
  { key: 'shorten', label: '更简短' },
  { key: 'translate_zh', label: '译中' },
  { key: 'translate_en', label: '译英' },
]

interface ComposeModalProps {
  accounts: Account[]
  init: ComposeInit
  onClose: () => void
  onSent: () => void
}

const inputClass =
  'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm outline-none transition-colors focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100'

function buildInit(init: ComposeInit): {
  to: string; cc: string; subject: string; body: string
} {
  const base = init.base
  if (!base) return { to: '', cc: '', subject: '', body: '' }
  const quote = [
    '',
    '',
    '-------- 原始邮件 --------',
    `发件人: ${base.sender_name} <${base.sender_email}>`,
    `日期: ${base.date ? new Date(base.date).toLocaleString('zh-CN', { hour12: false }) : ''}`,
    `主题: ${base.subject}`,
    '',
    (base.body_text || '').slice(0, 2000),
  ].join('\n')

  if (init.mode === 'reply') {
    return { to: base.sender_email, cc: '', subject: prefix(base.subject, 'Re:'), body: quote }
  }
  if (init.mode === 'replyAll') {
    const others = base.recipients.filter((r) => r !== base.sender_email)
    return {
      to: base.sender_email,
      cc: others.join(', '),
      subject: prefix(base.subject, 'Re:'),
      body: quote,
    }
  }
  return {
    to: '',
    cc: '',
    subject: prefix(base.subject, 'Fwd:'),
    body: quote.replace('原始邮件', '转发邮件'),
  }
}

function prefix(subject: string, mark: string): string {
  const trimmed = subject.trim()
  if (!trimmed) return mark
  return trimmed.toLowerCase().startsWith(mark.toLowerCase().slice(0, 3)) ? trimmed : `${mark} ${trimmed}`
}

export default function ComposeModal({ accounts, init, onClose, onSent }: ComposeModalProps) {
  const [accountId, setAccountId] = useState<number>(
    init.base?.account_id ?? accounts[0]?.id ?? 0,
  )
  const prefill = buildInit(init)
  const [to, setTo] = useState(prefill.to)
  const [cc, setCc] = useState(prefill.cc)
  const [subject, setSubject] = useState(prefill.subject)
  const [body, setBody] = useState(prefill.body)
  const [files, setFiles] = useState<File[]>([])
  const fileRef = useRef<HTMLInputElement>(null)
  const [assistBusy, setAssistBusy] = useState(false)
  const [assistError, setAssistError] = useState('')

  const runAssist = async (op: string) => {
    if (!body.trim() || assistBusy) return
    setAssistBusy(true)
    setAssistError('')
    try {
      const { text } = await api.aiWrite({ text: body, op })
      setBody(text)
    } catch (err) {
      setAssistError((err as Error).message)
    } finally {
      setAssistBusy(false)
    }
  }

  const mutation = useMutation({
    mutationFn: () => {
      const form = new FormData()
      form.set('account_id', String(accountId))
      form.set('to', to)
      form.set('cc', cc)
      form.set('bcc', '')
      form.set('subject', subject)
      form.set('body', body)
      files.forEach((f) => form.append('files', f))
      return api.sendEmail(form)
    },
    onSuccess: onSent,
  })

  const submitDisabled = !to.trim() || !accountId || mutation.isPending

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/30 p-6">
      <div className="flex max-h-full w-full max-w-2xl flex-col overflow-hidden rounded-2xl bg-white shadow-2xl">
        <div className="flex items-center justify-between border-b border-gray-100 px-5 py-3">
          <h2 className="text-sm font-semibold">
            {init.mode === 'new' ? '写邮件' : init.mode === 'forward' ? '转发邮件' : '回复邮件'}
          </h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-700">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="flex-1 space-y-3 overflow-y-auto p-5">
          <div className="flex items-center gap-3">
            <span className="w-14 shrink-0 text-sm text-gray-500">账号</span>
            <select
              className={inputClass}
              value={accountId}
              onChange={(e) => setAccountId(Number(e.target.value))}
            >
              {accounts.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.email}
                </option>
              ))}
            </select>
          </div>
          <div className="flex items-center gap-3">
            <span className="w-14 shrink-0 text-sm text-gray-500">收件人</span>
            <input
              className={inputClass}
              value={to}
              onChange={(e) => setTo(e.target.value)}
              placeholder="多个地址用逗号分隔"
            />
          </div>
          <div className="flex items-center gap-3">
            <span className="w-14 shrink-0 text-sm text-gray-500">抄送</span>
            <input className={inputClass} value={cc} onChange={(e) => setCc(e.target.value)} />
          </div>
          <div className="flex items-center gap-3">
            <span className="w-14 shrink-0 text-sm text-gray-500">主题</span>
            <input
              className={inputClass}
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
            />
          </div>
          <div>
            <textarea
              className={`${inputClass} min-h-56 resize-y font-mono text-[13px] leading-relaxed`}
              value={body}
              onChange={(e) => setBody(e.target.value)}
              placeholder="支持 Markdown 格式"
            />
            <div className="mt-2 flex items-center gap-1.5 text-xs">
              <span className="text-gray-400">AI 辅助：</span>
              {WRITE_OPS.map((op) => (
                <button
                  key={op.key}
                  className="rounded-md border border-violet-200 px-2 py-0.5 text-violet-600 hover:bg-violet-50 disabled:opacity-40"
                  disabled={assistBusy || !body.trim()}
                  onClick={() => runAssist(op.key)}
                >
                  {op.label}
                </button>
              ))}
              {assistBusy && <Loader2 className="h-3.5 w-3.5 animate-spin text-violet-500" />}
              {assistError && <span className="text-red-500">{assistError}</span>}
            </div>
          </div>
          <div>
            <input
              ref={fileRef}
              type="file"
              multiple
              className="hidden"
              onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
            />
            <button
              className="rounded-lg border border-gray-300 px-3 py-1.5 text-xs text-gray-600 hover:bg-gray-50"
              onClick={() => fileRef.current?.click()}
            >
              添加附件
            </button>
            {files.length > 0 && (
              <span className="ml-3 text-xs text-gray-500">
                {files.map((f) => f.name).join('、')}
                <button
                  className="ml-2 text-gray-400 hover:text-red-500"
                  onClick={() => setFiles([])}
                >
                  清除
                </button>
              </span>
            )}
          </div>
        </div>

        <div className="flex items-center justify-between border-t border-gray-100 px-5 py-3">
          <div className="text-xs text-red-500">
            {mutation.isError ? (mutation.error as Error).message : ''}
          </div>
          <div className="flex gap-2">
            <button
              className="rounded-lg border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50"
              onClick={onClose}
            >
              取消
            </button>
            <button
              className="rounded-lg bg-indigo-600 px-5 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
              onClick={() => mutation.mutate()}
              disabled={submitDisabled}
            >
              {mutation.isPending ? '发送中…' : '发送'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
