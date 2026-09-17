import { useEffect, useState } from 'react'
import { Download, Loader2, X } from 'lucide-react'
import type { EmailAttachment } from '../types'
import { fmtSize } from '../utils/format'

export const TEXT_PREVIEW_MAX = 1024 * 1024 // 文本预览上限 1MB，超出提示下载

/** 附件是否可预览：与后端 inline 白名单同口径（HTML/SVG 可携带脚本，不预览）。 */
export function previewKind(att: EmailAttachment): 'image' | 'pdf' | 'text' | null {
  const base = (att.mime || '').split(';')[0].trim().toLowerCase()
  if (base.startsWith('image/') && base !== 'image/svg+xml') return 'image'
  if (base === 'application/pdf') return 'pdf'
  if (base.startsWith('text/')) return 'text'
  return null
}

const inlineUrl = (att: EmailAttachment) => `${att.download_url}?inline=1`

/** 附件预览弹层：图片直接渲染、PDF 用浏览器内置 viewer、文本读出后 <pre> 展示；其余类型不进入此层。 */
export default function AttachmentPreview({ att, onClose }: { att: EmailAttachment; onClose: () => void }) {
  const kind = previewKind(att)
  const [text, setText] = useState<string | null>(null)
  const [loadError, setLoadError] = useState(false)

  useEffect(() => {
    setText(null)
    setLoadError(false)
    if (kind !== 'text') return
    const overLimit = att.size > TEXT_PREVIEW_MAX
    if (overLimit) return
    let cancelled = false
    fetch(inlineUrl(att))
      .then((r) => (r.ok ? r.text() : Promise.reject(new Error(String(r.status)))))
      .then((t) => {
        if (!cancelled) setText(t)
      })
      .catch(() => {
        if (!cancelled) setLoadError(true)
      })
    return () => {
      cancelled = true
    }
  }, [att, kind])

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onClick={onClose}
    >
      <div
        className="flex max-h-full w-full max-w-4xl flex-col overflow-hidden rounded-xl bg-white shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex shrink-0 items-center gap-2 border-b border-gray-100 px-4 py-2.5">
          <span className="min-w-0 flex-1 truncate t-sm font-semibold text-gray-800" title={att.filename}>
            {att.filename}
          </span>
          <span className="t-xs text-gray-400">{fmtSize(att.size)}</span>
          <a
            href={att.download_url}
            className="rounded-md p-1.5 text-gray-500 hover:bg-gray-100 hover:text-indigo-600"
            title="下载"
          >
            <Download className="h-4 w-4" />
          </a>
          <button
            onClick={onClose}
            className="rounded-md p-1.5 text-gray-500 hover:bg-gray-100 hover:text-gray-700"
            title="关闭（Esc）"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-auto bg-gray-50">
          {kind === 'image' && (
            <div className="flex min-h-full items-center justify-center p-4">
              <img src={inlineUrl(att)} alt={att.filename} className="max-h-full max-w-full object-contain" />
            </div>
          )}
          {kind === 'pdf' && <iframe src={inlineUrl(att)} title={att.filename} className="h-[75vh] w-full" />}
          {kind === 'text' &&
            (att.size > TEXT_PREVIEW_MAX ? (
              <PreviewFallback text="文本文件超过 1MB，请下载后查看" />
            ) : text === null ? (
              <div className="flex h-40 items-center justify-center text-gray-400">
                {loadError ? <PreviewFallback text="预览加载失败，请下载后查看" /> : <Loader2 className="h-5 w-5 animate-spin" />}
              </div>
            ) : (
              <pre className="whitespace-pre-wrap break-words p-4 font-mono t-sm leading-relaxed text-gray-800">
                {text}
              </pre>
            ))}
        </div>
      </div>
    </div>
  )
}

function PreviewFallback({ text }: { text: string }) {
  return <div className="p-8 text-center t-sm text-gray-500">{text}</div>
}
