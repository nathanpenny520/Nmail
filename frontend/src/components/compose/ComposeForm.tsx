import { useMutation } from '@tanstack/react-query'
import { Loader2, Paperclip, Send, Sparkles, X } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../../api/client'
import type { Account, UserDraft } from '../../types'
import { useCompose } from './ComposeContext'
import { applyAiText, EditorSurface, EditorToolbar, useMailEditor } from './RichEditor'

const WRITE_OPS = [
  { key: 'polish', label: '润色' },
  { key: 'formal', label: '更正式' },
  { key: 'shorten', label: '更简短' },
  { key: 'translate_zh', label: '译中' },
  { key: 'translate_en', label: '译英' },
]

const fieldInput =
  'min-w-0 flex-1 rounded-md border border-transparent bg-transparent px-2 py-1.5 t-md outline-none transition-colors placeholder:text-gray-300 hover:border-gray-200 focus:border-indigo-400 focus:bg-white'

function fmtSize(n: number): string {
  if (n >= 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)}M`
  if (n >= 1024) return `${Math.ceil(n / 1024)}K`
  return `${n}B`
}

/**
 * 单个写信标签的编辑表单。内容变化 1s 防抖自动保存到 user_drafts，
 * 卸载时兜底同步一次；发送前先 flush 确保后端拿到最新内容。
 */
export default function ComposeForm({ draft, accounts }: { draft: UserDraft; accounts: Account[] }) {
  const { updateTab, requestClose, finishSent } = useCompose()

  const [accountId, setAccountId] = useState(draft.account_id)
  const [to, setTo] = useState(draft.to_addrs)
  const [cc, setCc] = useState(draft.cc_addrs)
  const [bcc, setBcc] = useState(draft.bcc_addrs)
  const [subject, setSubject] = useState(draft.subject)
  const [showCc, setShowCc] = useState(!!draft.cc_addrs.trim() || !!draft.bcc_addrs.trim())
  const [showBcc, setShowBcc] = useState(!!draft.bcc_addrs.trim())
  const [bodyHtml, setBodyHtml] = useState(draft.body_html)
  const [files, setFiles] = useState<File[]>([])
  const [assistBusy, setAssistBusy] = useState(false)
  const [assistError, setAssistError] = useState('')
  const [savedAt, setSavedAt] = useState('')
  const [saveError, setSaveError] = useState(false)

  // 标签标题跟随主题/收件人
  useEffect(() => {
    updateTab(draft.id, { title: subject.trim() || to.split(',')[0]?.trim() || '新邮件' })
  }, [subject, to, draft.id, updateTab])

  // ── 自动保存 ──
  const payloadRef = useRef({ account_id: accountId, to_addrs: to, cc_addrs: cc, bcc_addrs: bcc, subject, body_html: bodyHtml })
  payloadRef.current = { account_id: accountId, to_addrs: to, cc_addrs: cc, bcc_addrs: bcc, subject, body_html: bodyHtml }
  const savedRef = useRef(
    JSON.stringify({
      account_id: draft.account_id,
      to_addrs: draft.to_addrs,
      cc_addrs: draft.cc_addrs,
      bcc_addrs: draft.bcc_addrs,
      subject: draft.subject,
      body_html: draft.body_html,
    }),
  )
  const saveTimer = useRef<number | undefined>(undefined)

  const doSave = useCallback(async () => {
    const p = payloadRef.current
    const serialized = JSON.stringify(p)
    if (serialized === savedRef.current) return
    try {
      await api.updateUserDraft(draft.id, p)
      savedRef.current = serialized
      setSaveError(false)
      setSavedAt(new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false }))
      updateTab(draft.id, { dirty: false })
    } catch {
      setSaveError(true) // 保持 dirty，后续改动会再次触发保存
    }
  }, [draft.id, updateTab])
  const doSaveRef = useRef(doSave)
  doSaveRef.current = doSave

  useEffect(() => {
    const serialized = JSON.stringify(payloadRef.current)
    if (serialized === savedRef.current) return
    updateTab(draft.id, { dirty: true })
    window.clearTimeout(saveTimer.current)
    saveTimer.current = window.setTimeout(() => void doSaveRef.current(), 1000)
  }, [accountId, to, cc, bcc, subject, bodyHtml, draft.id, updateTab])

  // 卸载兜底：关标签/切换页面时把防抖窗口内的最后编辑同步上去
  useEffect(
    () => () => {
      window.clearTimeout(saveTimer.current)
      void doSaveRef.current().catch(() => {})
    },
    [],
  )

  // ── 发送 ──
  const sendMutation = useMutation({
    mutationFn: async () => {
      await doSaveRef.current()
      const form = new FormData()
      for (const f of files) form.append('files', f)
      return api.sendUserDraft(draft.id, form)
    },
    onSuccess: () => finishSent(draft.id),
  })
  const sendNowRef = useRef<() => void>(() => {})
  sendNowRef.current = () => {
    if (!sendMutation.isPending) sendMutation.mutate()
  }

  const editor = useMailEditor(draft.body_html, setBodyHtml, () => sendNowRef.current())

  const runAssist = async (op: string) => {
    if (!editor || assistBusy) return
    const text = editor.getText({ blockSeparator: '\n\n' })
    if (!text.trim()) return
    setAssistBusy(true)
    setAssistError('')
    try {
      const { text: result } = await api.aiWrite({ text, op })
      applyAiText(editor, result)
    } catch (err) {
      setAssistError((err as Error).message)
    } finally {
      setAssistBusy(false)
    }
  }

  const submitDisabled = !to.trim() || sendMutation.isPending

  return (
    <div
      className="flex h-full flex-col bg-white"
      onKeyDown={(e) => {
        if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
          e.preventDefault()
          void doSaveRef.current()
        }
      }}
    >
      {/* 字段区：收件人 / 抄送密送（默认折叠）/ 主题 / 附件 */}
      <div className="shrink-0 divide-y divide-gray-100 border-b border-gray-100">
        <div className="flex items-center gap-1.5 px-4 py-1.5">
          <span className="w-11 shrink-0 t-sm text-gray-400">收件人</span>
          <input
            className={fieldInput}
            value={to}
            onChange={(e) => setTo(e.target.value)}
            placeholder="多个地址用逗号分隔"
            autoFocus
          />
          {!showCc && (
            <button
              className="shrink-0 whitespace-nowrap rounded-md px-1.5 py-0.5 t-sm text-indigo-500 hover:bg-indigo-50"
              onClick={() => setShowCc(true)}
            >
              抄送/密送
            </button>
          )}
        </div>
        {showCc && (
          <div className="flex items-center gap-1.5 px-4 py-1.5">
            <span className="w-11 shrink-0 t-sm text-gray-400">抄送</span>
            <input className={fieldInput} value={cc} onChange={(e) => setCc(e.target.value)} />
            {!showBcc && (
              <button
                className="shrink-0 whitespace-nowrap rounded-md px-1.5 py-0.5 t-sm text-indigo-500 hover:bg-indigo-50"
                onClick={() => setShowBcc(true)}
                title="添加密送"
              >
                密送
              </button>
            )}
          </div>
        )}
        {showCc && showBcc && (
          <div className="flex items-center gap-1.5 px-4 py-1.5">
            <span className="w-11 shrink-0 t-sm text-gray-400">密送</span>
            <input className={fieldInput} value={bcc} onChange={(e) => setBcc(e.target.value)} />
          </div>
        )}
        <div className="flex items-center gap-1.5 px-4 py-1.5">
          <span className="w-11 shrink-0 t-sm text-gray-400">主题</span>
          <input
            className={`${fieldInput} font-medium`}
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            placeholder="邮件主题"
          />
        </div>
        <div className="flex flex-wrap items-center gap-1.5 px-4 py-1.5">
          <label className="flex cursor-pointer items-center gap-1 whitespace-nowrap rounded-md px-1 py-0.5 t-sm text-gray-500 hover:text-indigo-600">
            <Paperclip className="h-3.5 w-3.5" />
            添加附件
            <input
              type="file"
              multiple
              className="hidden"
              onChange={(e) => {
                setFiles((fs) => [...fs, ...Array.from(e.target.files ?? [])])
                e.target.value = ''
              }}
            />
          </label>
          {files.map((f, i) => (
            <span
              key={`${f.name}-${i}`}
              className="inline-flex max-w-52 items-center gap-1 rounded-md bg-gray-100 px-2 py-0.5 t-xs text-gray-600"
            >
              <span className="truncate" title={f.name}>
                {f.name}
              </span>
              <span className="shrink-0 text-gray-400">{fmtSize(f.size)}</span>
              <button
                className="shrink-0 text-gray-400 hover:text-red-500"
                onClick={() => setFiles((fs) => fs.filter((_, j) => j !== i))}
              >
                <X className="h-3 w-3" />
              </button>
            </span>
          ))}
        </div>
      </div>

      {/* AI 辅助行 */}
      <div className="flex shrink-0 flex-wrap items-center gap-1 border-b border-gray-100 px-3 py-1 t-xs">
        <Sparkles className="h-3 w-3 text-violet-500" />
        <span className="mr-1 text-gray-400">智能写作：</span>
        {WRITE_OPS.map((op) => (
          <button
            key={op.key}
            className="rounded-md border border-violet-200 px-1.5 py-0.5 text-violet-600 transition-colors hover:bg-violet-50 disabled:opacity-40"
            disabled={assistBusy || !editor?.getText().trim()}
            onClick={() => void runAssist(op.key)}
          >
            {op.label}
          </button>
        ))}
        {assistBusy && <Loader2 className="h-3 w-3 animate-spin text-violet-500" />}
        {assistError && <span className="text-red-500">{assistError}</span>}
      </div>

      <EditorToolbar editor={editor} />
      <EditorSurface editor={editor} />

      {/* 底部操作条 */}
      <div className="flex shrink-0 flex-wrap items-center gap-2 border-t border-gray-200 bg-gray-50 px-4 py-2">
        <button
          className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-5 py-1.5 t-sm font-medium text-white transition-colors hover:bg-indigo-700 disabled:opacity-50"
          onClick={() => sendNowRef.current()}
          disabled={submitDisabled}
        >
          {sendMutation.isPending ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Send className="h-3.5 w-3.5" />
          )}
          {sendMutation.isPending ? '发送中…' : '发送'}
        </button>
        <button
          className="rounded-lg border border-gray-300 px-3 py-1.5 t-sm text-gray-700 transition-colors hover:bg-gray-100"
          onClick={() => {
            void doSaveRef.current().then(() => requestClose(draft.id))
          }}
          title="保存并收起标签（草稿保留，下次启动自动恢复）"
        >
          存草稿
        </button>
        <span className="flex-1" />
        {saveError ? (
          <span className="t-xs text-red-500">自动保存失败，请检查后端服务</span>
        ) : savedAt ? (
          <span className="t-xs text-gray-400">已保存 {savedAt}</span>
        ) : null}
        {sendMutation.isError && (
          <span className="max-w-64 truncate t-xs text-red-500" title={(sendMutation.error as Error).message}>
            {(sendMutation.error as Error).message}
          </span>
        )}
        <select
          className="max-w-56 rounded-lg border border-gray-300 bg-white px-2 py-1.5 t-sm outline-none focus:border-indigo-500"
          value={accountId}
          onChange={(e) => setAccountId(Number(e.target.value))}
          title="发件账号"
        >
          {accounts.map((a) => (
            <option key={a.id} value={a.id}>
              {a.email}
            </option>
          ))}
        </select>
      </div>
    </div>
  )
}
