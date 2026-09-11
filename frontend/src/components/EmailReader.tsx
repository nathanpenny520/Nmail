import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Archive, ArchiveRestore, Ban, CircleCheck, CornerUpLeft, CornerUpRight,
  ExternalLink, Forward, Loader2, Maximize2, Minimize2, PenLine, Sparkles, Star, Trash2, X,
} from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import type { EmailDetail } from '../types'
import AiPanel from './AiPanel'
import HtmlMail from './HtmlMail'

interface EmailReaderProps {
  detail: EmailDetail
  archived: boolean
  actionBusy: boolean
  onAction: (action: string, folder?: string) => void
  onCompose: (mode: 'reply' | 'replyAll' | 'forward') => void
  onShowImages: () => void
  full: boolean
  onToggleFull: () => void
  onClose: () => void
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
  'inline-flex items-center gap-1 rounded-md border border-gray-200 bg-white px-1.5 py-1 t-sm text-gray-600 transition-colors hover:bg-gray-50 hover:text-gray-900 disabled:opacity-50'

/** 邮件阅读区：分屏右栏，可一键全屏；内容列随容器自适应。 */
export default function EmailReader({
  detail, archived, actionBusy, onAction, onCompose, onShowImages, full, onToggleFull, onClose,
}: EmailReaderProps) {
  const [moveOpen, setMoveOpen] = useState(false)
  const [aiOpen, setAiOpen] = useState(false)
  const [listMessage, setListMessage] = useState<string | null>(null)
  const [draftInstrOpen, setDraftInstrOpen] = useState(false)
  const [draftInstr, setDraftInstr] = useState('')
  const queryClient = useQueryClient()
  const navigate = useNavigate()

  // 手动触发 AI 拟稿（可带要求提示词）：生成后直接跳到待审草稿页
  const draftMutation = useMutation({
    mutationFn: () =>
      api.regenerateDraft(detail.id, draftInstr.trim() || undefined),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['drafts'] })
      navigate('/drafts')
    },
    onError: (err: Error) => {
      setListMessage(`拟稿失败：${err.message}`)
      setTimeout(() => setListMessage(null), 6000)
    },
  })

  // 图片信任白名单：该发件人以后的邮件远程图片直接显示
  const trustImagesMutation = useMutation({
    mutationFn: () => api.addSenderList(detail.sender_email, 'image_trust'),
    onSuccess: () => {
      setListMessage('已加入图片信任白名单，正在重新加载图片…')
      onShowImages()
    },
    onError: (err: Error) => {
      setListMessage(`操作失败：${err.message}`)
      setTimeout(() => setListMessage(null), 6000)
    },
  })

  const senderListMutation = useMutation({
    mutationFn: ({ type }: { type: 'whitelist' | 'blacklist' }) =>
      api.addSenderList(detail.sender_email, type),
    onSuccess: (_data, variables) => {
      setListMessage(
        variables.type === 'whitelist'
          ? '已加入白名单：该发件人以后直接进收件箱'
          : '已加入黑名单：该发件人以后自动归档',
      )
      void queryClient.invalidateQueries({ queryKey: ['sender-lists'] })
      setTimeout(() => setListMessage(null), 5000)
    },
    onError: (err: Error) => {
      setListMessage(`操作失败：${err.message}`)
      setTimeout(() => setListMessage(null), 5000)
    },
  })

  return (
    <div className="flex h-full min-w-0 flex-col bg-white">
      {/* 顶部：全屏切换 + 关闭 */}
      <div className="flex shrink-0 items-center gap-2 border-b border-gray-100 px-3 py-1.5">
        <button
          className="inline-flex items-center gap-1.5 rounded-lg border border-gray-200 px-2 py-1 t-sm text-gray-600 hover:bg-gray-50"
          onClick={onToggleFull}
          title={full ? '返回分屏' : '全屏阅读'}
        >
          {full ? <Minimize2 className="h-3 w-3" /> : <Maximize2 className="h-3 w-3" />}
          {full ? '返回分屏' : '全屏'}
        </button>
        <span className="flex-1" />
        <span
          className="max-w-56 truncate rounded-full px-2 py-0.5 t-xs font-medium text-white"
          style={{ backgroundColor: detail.account_color }}
          title={detail.account_email}
        >
          {detail.account_email}
        </span>
        <button
          className="rounded-lg p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-700"
          onClick={onClose}
          title="关闭 (Esc)"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-6xl px-5 pb-10 pt-4">
          {/* 头部 */}
          <h1 className="t-lg font-semibold leading-snug text-gray-900">
            {detail.subject || '（无主题）'}
          </h1>
          <div className="mt-1.5 flex flex-wrap items-baseline gap-x-2 t-sm text-gray-500">
            <span className="font-medium text-gray-700">{detail.sender_name || detail.sender_email}</span>
            {detail.sender_name && detail.sender_email && detail.sender_name !== detail.sender_email && (
              <span className="text-gray-400">&lt;{detail.sender_email}&gt;</span>
            )}
            <span className="text-gray-300">·</span>
            <span>{formatDate(detail.date)}</span>
          </div>
          {detail.recipients.length > 0 && (
            <div className="mt-0.5 t-xs text-gray-400">
              收件人：{detail.recipients.join('，')}
            </div>
          )}
          {detail.cc.length > 0 && (
            <div className="mt-0.5 t-xs text-gray-400">抄送：{detail.cc.join('，')}</div>
          )}

          {/* 操作栏 */}
          <div className="relative mt-3 flex flex-wrap items-center gap-1.5 border-y border-gray-100 py-2">
            <button className={btn} onClick={() => onCompose('reply')} disabled={actionBusy}>
              <CornerUpLeft className="h-3 w-3" /> 回复
            </button>
            <button className={btn} onClick={() => onCompose('replyAll')} disabled={actionBusy}>
              <CornerUpRight className="h-3 w-3" /> 回复全部
            </button>
            <button className={btn} onClick={() => onCompose('forward')} disabled={actionBusy}>
              <Forward className="h-3 w-3" /> 转发
            </button>
            <span className="mx-0.5 h-4 w-px bg-gray-200" />
            <button
              className={btn}
              onClick={() => onAction(detail.starred ? 'unstar' : 'star')}
              disabled={actionBusy}
            >
              <Star className={`h-3 w-3 ${detail.starred ? 'fill-amber-400 text-amber-400' : ''}`} />
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
                <ArchiveRestore className="h-3 w-3" /> 恢复到收件箱
              </button>
            ) : (
              <button className={btn} onClick={() => onAction('archive')} disabled={actionBusy}>
                <Archive className="h-3 w-3" /> 归档
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
              <Trash2 className="h-3 w-3" /> 删除
            </button>
            <span className="mx-0.5 h-4 w-px bg-gray-200" />
            <button
              className={btn}
              title="白名单：以后该发件人的邮件直接进收件箱，AI 不参与"
              onClick={() => senderListMutation.mutate({ type: 'whitelist' })}
              disabled={senderListMutation.isPending}
            >
              <CircleCheck className="h-3 w-3 text-emerald-500" /> 永久收信
            </button>
            <button
              className={btn}
              title="黑名单：以后该发件人的邮件直接归档，AI 不参与"
              onClick={() => senderListMutation.mutate({ type: 'blacklist' })}
              disabled={senderListMutation.isPending}
            >
              <Ban className="h-3 w-3 text-rose-500" /> 拉黑归档
            </button>
            <span className="mx-0.5 h-4 w-px bg-gray-200" />
            <button
              className={`${btn} border-violet-200 bg-violet-50/60 text-violet-700 hover:bg-violet-50 ${
                draftInstrOpen ? 'border-violet-400' : ''
              }`}
              title="让 AI 为这封邮件起草回复，可附带你的要求"
              onClick={() => setDraftInstrOpen((v) => !v)}
              disabled={draftMutation.isPending}
            >
              {draftMutation.isPending
                ? <Loader2 className="h-3 w-3 animate-spin" />
                : <PenLine className="h-3 w-3" />}
              AI 拟稿
            </button>
            <button
              className={`${btn} border-violet-200 text-violet-700 hover:bg-violet-50`}
              onClick={() => setAiOpen((v) => !v)}
            >
              <Sparkles className="h-3 w-3" /> AI 助手
            </button>
            {actionBusy && <Loader2 className="h-3.5 w-3.5 animate-spin text-gray-400" />}
            {listMessage && <span className="t-xs text-indigo-600">{listMessage}</span>}
            {draftInstrOpen && (
              <div className="mt-1 flex w-full items-center gap-2">
                <input
                  className="min-w-0 flex-1 rounded-lg border border-violet-200 px-2.5 py-1.5 t-sm outline-none focus:border-violet-500 focus:ring-2 focus:ring-violet-100"
                  placeholder="对回复的要求，如：婉拒并致谢 / 询问附件细节（留空则由 AI 自行起草）"
                  value={draftInstr}
                  onChange={(e) => setDraftInstr(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && draftMutation.mutate()}
                  autoFocus
                />
                <button
                  className="shrink-0 rounded-lg bg-violet-600 px-3 py-1.5 t-sm font-medium text-white hover:bg-violet-700 disabled:opacity-50"
                  onClick={() => draftMutation.mutate()}
                  disabled={draftMutation.isPending}
                >
                  {draftMutation.isPending ? '生成中…' : '生成草稿'}
                </button>
              </div>
            )}
          </div>

          {/* 正文 */}
          <div className="mt-4">
            {detail.remote_blocked > 0 && (
              <div className="mb-4 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-violet-200 bg-violet-50 px-3 py-2 t-sm text-violet-700">
                <span>已拦截 {detail.remote_blocked} 张外部图片（防追踪）</span>
                <div className="flex items-center gap-1.5">
                  <button
                    className="rounded-md border border-violet-300 bg-white px-2 py-1 t-sm font-medium text-violet-700 hover:bg-violet-100"
                    onClick={onShowImages}
                  >
                    <ExternalLink className="mr-1 inline h-3 w-3" />
                    本次显示
                  </button>
                  <button
                    className="rounded-md border border-violet-300 bg-white px-2 py-1 t-sm font-medium text-violet-700 hover:bg-violet-100 disabled:opacity-50"
                    title="把该发件人加入图片信任白名单：以后其邮件的远程图片直接显示"
                    onClick={() => trustImagesMutation.mutate()}
                    disabled={trustImagesMutation.isPending}
                  >
                    始终显示该发件人图片
                  </button>
                </div>
              </div>
            )}

            {detail.body_html ? (
              <HtmlMail html={detail.body_html} />
            ) : (
              <pre className="whitespace-pre-wrap break-words font-sans t-md leading-relaxed text-gray-800">
                {detail.body_text}
              </pre>
            )}
          </div>

          {/* 附件 */}
          {detail.attachments.length > 0 && (
            <div className="mt-6 border-t border-gray-100 pt-3">
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
      </div>

      {aiOpen && <AiPanel email={detail} onClose={() => setAiOpen(false)} />}
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
