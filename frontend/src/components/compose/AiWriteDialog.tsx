import { Loader2, RefreshCw, Sparkles } from 'lucide-react'
import { useRef, useState } from 'react'
import type { Editor } from '@tiptap/react'
import { api } from '../../api/client'
import { Modal } from './ui'

const QUICK_OPS = [
  { key: 'polish', label: '润色' },
  { key: 'formal', label: '更正式' },
  { key: 'shorten', label: '更简短' },
  { key: 'translate_zh', label: '译中' },
  { key: 'translate_en', label: '译英' },
]

const chipCls =
  'rounded-md border border-violet-200 px-2 py-0.5 text-violet-600 transition-colors hover:bg-violet-50 disabled:opacity-40'

/**
 * AI 写作对话框：点「AI 写作」弹出。可按指令整篇生成（compose），
 * 也可一键润色/正式/缩短/翻译；结果先预览再决定替换正文或插入末尾。
 * 输出经后端 Markdown→HTML 转换，插入即得可用富文本。
 */
export default function AiWriteDialog({ editor, onClose }: { editor: Editor; onClose: () => void }) {
  const [instruction, setInstruction] = useState('')
  const [busyOp, setBusyOp] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [result, setResult] = useState<{ html: string } | null>(null)
  const lastOpRef = useRef('compose')

  const run = async (op: string) => {
    if (busyOp) return
    const text = editor.getText({ blockSeparator: '\n\n' })
    if (op !== 'compose' && !text.trim()) {
      setError('快捷改写需要正文有内容；空文档请用上方指令让 AI 直接写')
      return
    }
    lastOpRef.current = op
    setBusyOp(op)
    setError('')
    try {
      const resp = await api.aiWrite({
        text,
        op,
        instruction: op === 'compose' ? instruction : undefined,
        want_html: true,
      })
      setResult({ html: resp.html ?? '' })
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusyOp(null)
    }
  }

  const insert = (mode: 'replace' | 'append') => {
    if (!result) return
    if (mode === 'replace') editor.commands.setContent(result.html || '<p></p>')
    else editor.commands.insertContent(result.html)
    onClose()
  }

  return (
    <Modal title="AI 写作" onClose={onClose} width="max-w-2xl">
      <textarea
        className="h-24 w-full resize-none rounded-lg border border-gray-300 px-3 py-2 t-sm leading-relaxed outline-none transition-colors focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100"
        placeholder="描述要写什么，例如：回复客户询问发货进度的邮件，语气友好，说明已发货并附顺丰单号，请对方注意查收"
        value={instruction}
        onChange={(e) => setInstruction(e.target.value)}
        autoFocus
      />
      <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
        <button
          className="inline-flex items-center gap-1 rounded-md bg-violet-600 px-2.5 py-1 t-sm font-medium text-white transition-colors hover:bg-violet-700 disabled:opacity-50"
          onClick={() => void run('compose')}
          disabled={busyOp != null || !instruction.trim()}
          title="按上方指令生成整篇正文"
        >
          {busyOp === 'compose' ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Sparkles className="h-3.5 w-3.5" />
          )}
          AI 生成
        </button>
        <span className="mx-0.5 h-4 w-px bg-gray-200" />
        {QUICK_OPS.map((op) => (
          <button
            key={op.key}
            className={chipCls}
            disabled={busyOp != null}
            onClick={() => void run(op.key)}
            title={`对整篇正文执行「${op.label}」`}
          >
            {busyOp === op.key ? <Loader2 className="h-3 w-3 animate-spin" /> : op.label}
          </button>
        ))}
        <span className="ml-auto t-xs text-gray-400">生成后预览，再决定替换或插入</span>
      </div>
      {error && <div className="mt-2 t-sm text-red-500">{error}</div>}
      {result && (
        <div className="mt-3 overflow-hidden rounded-lg border border-gray-200">
          <div className="border-b border-gray-100 bg-gray-50 px-3 py-1.5 t-xs text-gray-400">生成结果预览</div>
          <div
            className="mail-preview max-h-72 overflow-y-auto p-4"
            dangerouslySetInnerHTML={{ __html: result.html }}
          />
          <div className="flex items-center justify-end gap-2 border-t border-gray-100 bg-gray-50 px-3 py-2">
            <button
              className="inline-flex items-center gap-1 rounded-md border border-gray-300 px-2.5 py-1 t-sm text-gray-600 hover:bg-gray-100 disabled:opacity-50"
              onClick={() => void run(lastOpRef.current)}
              disabled={busyOp != null}
            >
              <RefreshCw className="h-3 w-3" />
              重新生成
            </button>
            <button
              className="rounded-md border border-gray-300 px-2.5 py-1 t-sm text-gray-700 hover:bg-gray-100"
              onClick={() => insert('append')}
            >
              插入末尾
            </button>
            <button
              className="rounded-md bg-indigo-600 px-3 py-1 t-sm font-medium text-white hover:bg-indigo-700"
              onClick={() => insert('replace')}
            >
              替换正文
            </button>
          </div>
        </div>
      )}
    </Modal>
  )
}
