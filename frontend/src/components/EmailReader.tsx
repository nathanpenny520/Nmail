import { useQuery } from '@tanstack/react-query'
import {
  Archive, ArchiveRestore, CornerUpLeft, CornerUpRight, ExternalLink,
  Forward, Loader2, Star, Trash2,
} from 'lucide-react'
import { useState } from 'react'
import { api } from '../api/client'
import type { EmailDetail } from '../types'
import HtmlMail from './HtmlMail'

interface EmailReaderProps {
  detail: EmailDetail
  archived: boolean
  actionBusy: boolean
  onAction: (action: string, folder?: string) => void
  onCompose: (mode: 'reply' | 'replyAll' | 'forward') => void
  onShowImages: () => void
}

function formatSize(size: number): string {
  if (size >= 1024 * 1024) return `${(size / 1024 / 1024).toFixed(1)} MB`
  if (size >= 1024) return `${(size / 1024).toFixed(0)} KB`
  return `${size} B`
}

function formatDate(iso: string | null): string {
  if (!iso) return ''
  return new Date(iso).toLocaleString('zh-CN', { hour12: false })
}

const btn =
  'inline-flex items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-2.5 py-1.5 text-xs text-gray-600 transition-colors hover:bg-gray-50 hover:text-gray-900 disabled:opacity-50'

export default function EmailReader({
  detail, archived, actionBusy, onAction, onCompose, onShowImages,
}: EmailReaderProps) {
  const [moveOpen, setMoveOpen] = useState(false)

  return (
    <div className="flex h-full flex-col">
      {/* 头部 */}
      <div className="border-b border-gray-200 px-6 py-4">
        <div className="flex items-start justify-between gap-4">
          <h1 className="text-lg font-semibold leading-snug">{detail.subject || '（无主题）'}</h1>
          <span
            className="mt-1 shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium text-white"
            style={{ backgroundColor: detail.account_color }}
          >
            {detail.account_email}
          </span>
        </div>
        <div className="mt-1 text-sm text-gray-500">
          {detail.sender_name || detail.sender_email}
          {detail.sender_name && detail.sender_email && detail.sender_name !== detail.sender_email && (
            <span className="text-gray-400"> &lt;{detail.sender_email}&gt;</span>
          )}
          <span className="mx-2 text-gray-300">·</span>
          {formatDate(detail.date)}
        </div>
        {detail.recipients.length > 0 && (
          <div className="mt-0.5 text-xs text-gray-400">收件人：{detail.recipients.join('，')}</div>
        )}
        {detail.cc.length > 0 && (
          <div className="mt-0.5 text-xs text-gray-400">抄送：{detail.cc.join('，')}</div>
        )}
      </div>

      {/* 操作栏 */}
      <div className="relative flex flex-wrap items-center gap-2 border-b border-gray-100 px-6 py-2.5">
        <button className={btn} onClick={() => onCompose('reply')} disabled={actionBusy}>
          <CornerUpLeft className="h-3.5 w-3.5" /> 回复
        </button>
        <button className={btn} onClick={() => onCompose('replyAll')} disabled={actionBusy}>
          <CornerUpRight className="h-3.5 w-3.5" /> 回复全部
        </button>
        <button className={btn} onClick={() => onCompose('forward')} disabled={actionBusy}>
          <Forward className="h-3.5 w-3.5" /> 转发
        </button>
        <span className="mx-1 h-4 w-px bg-gray-200" />
        <button
          className={btn}
          onClick={() => onAction(detail.starred ? 'unstar' : 'star')}
          disabled={actionBusy}
        >
          <Star className={`h-3.5 w-3.5 ${detail.starred ? 'fill-amber-400 text-amber-400' : ''}`} />
          {detail.starred ? '取消星标' : '星标'}
        </button>
        <button
          className={btn}
          onClick={() => onAction(detail.is_read ? 'unread' : 'read')}
          disabled={actionBusy}
        >
          {detail.is_read ? '标为未读' : '标为已读'}
        </button>
        {archived ? (
          <button className={btn} onClick={() => onAction('unarchive')} disabled={actionBusy}>
            <ArchiveRestore className="h-3.5 w-3.5" /> 恢复到收件箱
          </button>
        ) : (
          <button className={btn} onClick={() => onAction('archive')} disabled={actionBusy}>
            <Archive className="h-3.5 w-3.5" /> 归档
          </button>
        )}

        {/* 移动到 */}
        <div className="relative">
          <button className={btn} onClick={() => setMoveOpen((v) => !v)} disabled={actionBusy}>
            移动到 ▾
          </button>
          {moveOpen && (
            <MoveMenu
              accountId={detail.account_id}
              current={detail.folder}
              onPick={(folder) => {
                setMoveOpen(false)
                onAction('move', folder)
              }}
              onClose={() => setMoveOpen(false)}
            />
          )}
        </div>

        <button
          className={`${btn} hover:text-red-600`}
          onClick={() => onAction('trash')}
          disabled={actionBusy}
        >
          <Trash2 className="h-3.5 w-3.5" /> 删除
        </button>
        {actionBusy && <Loader2 className="ml-1 h-4 w-4 animate-spin text-gray-400" />}
      </div>

      {/* 正文 */}
      <div className="flex-1 overflow-auto px-6 py-5">
        {detail.remote_blocked > 0 && (
          <div className="mb-4 flex items-center justify-between rounded-lg border border-violet-200 bg-violet-50 px-4 py-2.5 text-sm text-violet-700">
            <span>已拦截 {detail.remote_blocked} 张外部图片（防追踪）</span>
            <button
              className="rounded-md border border-violet-300 bg-white px-2.5 py-1 text-xs font-medium text-violet-700 hover:bg-violet-100"
              onClick={onShowImages}
            >
              <ExternalLink className="mr-1 inline h-3 w-3" />
              本次显示图片
            </button>
          </div>
        )}

        {detail.body_html ? (
          <HtmlMail html={detail.body_html} />
        ) : (
          <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed text-gray-800">
            {detail.body_text}
          </pre>
        )}
      </div>

      {/* 附件 */}
      {detail.attachments.length > 0 && (
        <div className="border-t border-gray-100 px-6 py-3">
          <div className="mb-2 text-xs font-medium text-gray-500">
            附件（{detail.attachments.length}）
          </div>
          <div className="flex flex-wrap gap-2">
            {detail.attachments.map((att) => (
              <a
                key={att.id}
                href={att.download_url}
                className="flex items-center gap-2 rounded-lg border border-gray-200 bg-gray-50 px-3 py-1.5 text-xs text-gray-700 hover:border-indigo-300 hover:bg-indigo-50"
                title={att.filename}
              >
                <span className="max-w-52 truncate font-medium">{att.filename}</span>
                <span className="text-gray-400">{formatSize(att.size)}</span>
              </a>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function MoveMenu({
  accountId, current, onPick, onClose,
}: {
  accountId: number
  current: string
  onPick: (folder: string) => void
  onClose: () => void
}) {
  const { data, isLoading, error } = useFoldersQuery(accountId)
  return (
    <>
      <div className="fixed inset-0 z-10" onClick={onClose} />
      <div className="absolute left-0 top-full z-20 mt-1 max-h-72 w-56 overflow-auto rounded-xl border border-gray-200 bg-white py-1 shadow-lg">
        {isLoading && <div className="px-3 py-2 text-xs text-gray-400">加载文件夹…</div>}
        {error && <div className="px-3 py-2 text-xs text-red-500">{(error as Error).message}</div>}
        {data?.folders.map((f) => (
          <button
            key={f.name}
            className={`block w-full truncate px-3 py-1.5 text-left text-xs hover:bg-indigo-50 ${
              f.name === current ? 'text-indigo-600 font-medium' : 'text-gray-600'
            }`}
            onClick={() => onPick(f.name)}
          >
            {f.name}
          </button>
        ))}
      </div>
    </>
  )
}

function useFoldersQuery(accountId: number) {
  return useQuery({
    queryKey: ['folders', accountId],
    queryFn: () => api.getFolders(accountId),
    staleTime: 5 * 60 * 1000,
  })
}
