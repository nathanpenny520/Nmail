import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Bell, BellRing, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import type { NotificationItem } from '../types'

type NotifyPermission = 'default' | 'granted' | 'denied' | 'unsupported'

function notifyPermission(): NotifyPermission {
  if (typeof window === 'undefined' || !('Notification' in window)) return 'unsupported'
  return Notification.permission as NotifyPermission
}

export default function NotificationBell() {
  const [open, setOpen] = useState(false)
  const [perm, setPerm] = useState<NotifyPermission>(notifyPermission())
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const { data } = useQuery({
    queryKey: ['notifications'],
    queryFn: api.getNotifications,
    refetchInterval: 15000,
  })
  const unread = data?.unread ?? 0

  // 浏览器桌面通知：页面开着时，新通知到达即弹系统通知
  const prevIds = useRef<Set<number> | null>(null)
  useEffect(() => {
    if (!data) return
    const ids = new Set(data.items.map((i) => i.id))
    let refreshMail = false
    if (prevIds.current !== null) {
      for (const item of data.items) {
        if (prevIds.current.has(item.id) || item.is_read) continue
        // 新邮件/账号异常通知到达 → 刷新邮件列表与账号状态（后台同步完成的主要感知途径）
        if (item.type === 'new_mail' || item.type === 'account_error') refreshMail = true
        if (notifyPermission() === 'granted') {
          try {
            const n = new Notification(item.title, { body: item.body ?? '', tag: `nmail-${item.id}` })
            n.onclick = () => window.focus()
          } catch {
            // 通知构造失败（如无头环境）静默忽略
          }
        }
      }
    }
    if (refreshMail) {
      void queryClient.invalidateQueries({ queryKey: ['emails'] })
      void queryClient.invalidateQueries({ queryKey: ['accounts'] })
      void queryClient.invalidateQueries({ queryKey: ['user-drafts'] })
    }
    prevIds.current = ids
  }, [data, queryClient])

  const readAllMutation = useMutation({
    mutationFn: api.markNotificationsRead,
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['notifications'] }),
  })

  const clearReadMutation = useMutation({
    mutationFn: api.clearReadNotifications,
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['notifications'] }),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => api.deleteNotification(id),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['notifications'] }),
  })

  const readOneMutation = useMutation({
    mutationFn: (id: number) => api.markNotificationRead(id),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['notifications'] }),
  })

  // 通知点击：按类型跳转到对应内容（草稿→原邮件，摘要→摘要页，账号异常→设置）
  const openNotification = (n: NotificationItem) => {
    if (!n.is_read) readOneMutation.mutate(n.id)
    const ref = n.ref_id
    let target: string | null = null
    if (n.type === 'ai_draft' && ref) target = `/?focus=${ref}`
    else if (n.type === 'ai_draft_summary') target = '/?view=drafts'
    else if (n.type === 'digest') target = '/digest'
    else if (n.type === 'account_error') target = '/settings'
    if (target) {
      setOpen(false)
      navigate(target)
    }
  }

  return (
    <div className="relative">
      <button
        className="relative flex h-8 w-8 items-center justify-center rounded-lg text-gray-500 hover:bg-gray-100 hover:text-gray-800"
        onClick={() => setOpen((v) => !v)}
        title="通知"
      >
        <Bell className="h-4 w-4" />
        {unread > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-500 px-1 t-xs font-bold leading-none text-white">
            {unread > 99 ? '99+' : unread}
          </span>
        )}
      </button>
      {perm === 'default' && (
        <button
          className="flex h-8 w-8 items-center justify-center rounded-lg text-amber-500 hover:bg-amber-50"
          title="开启浏览器桌面通知：新邮件/草稿/摘要到达时提醒"
          onClick={() => {
            if ('Notification' in window) {
              void Notification.requestPermission().then((p) => setPerm(p as NotifyPermission))
            }
          }}
        >
          <BellRing className="h-4 w-4" />
        </button>
      )}

      {open && (
        <>
          <div className="fixed inset-0 z-30" onClick={() => setOpen(false)} />
          {/* v0.4 铃铛移到顶部图标区：面板向下展开、右缘对齐（旧 bottom-0 向上开会出视口） */}
          <div className="absolute right-0 top-full z-40 mt-1.5 w-80 rounded-xl border border-gray-200 bg-white shadow-xl">
            <div className="flex items-center justify-between border-b border-gray-100 px-4 py-2.5">
              <span className="t-sm font-semibold text-gray-700">通知中心</span>
              <div className="flex items-center gap-2">
                {unread > 0 && (
                  <button
                    className="t-xs text-indigo-600 hover:underline"
                    onClick={() => readAllMutation.mutate()}
                  >
                    全部已读
                  </button>
                )}
                {(data?.items.length ?? 0) > 0 && (
                  <button
                    className="t-xs text-gray-400 hover:text-red-500"
                    title="删除全部已读通知"
                    onClick={() => clearReadMutation.mutate()}
                  >
                    清除已读
                  </button>
                )}
              </div>
            </div>
            <div className="max-h-80 overflow-y-auto">
              {(data?.items.length ?? 0) === 0 && (
                <div className="px-4 py-8 text-center t-sm text-gray-300">暂无通知</div>
              )}
              {data?.items.map((n) => (
                <div
                  key={n.id}
                  role="button"
                  tabIndex={0}
                  className={`group relative cursor-pointer border-b border-gray-50 px-4 py-2.5 transition-colors hover:bg-violet-50/60 ${
                    n.is_read ? '' : 'bg-indigo-50/50'
                  }`}
                  onClick={() => openNotification(n)}
                  onKeyDown={(e) => e.key === 'Enter' && openNotification(n)}
                >
                  <div className="flex items-start gap-2 pr-5">
                    {!n.is_read && <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-indigo-500" />}
                    <div className="min-w-0">
                      <div className="truncate t-sm font-medium text-gray-800">{n.title}</div>
                      {n.body && <div className="mt-0.5 line-clamp-2 t-xs text-gray-500">{n.body}</div>}
                      <div className="mt-0.5 t-xs text-gray-300">{n.created_at}</div>
                    </div>
                  </div>
                  <button
                    className="absolute right-2 top-2 hidden rounded p-0.5 text-gray-300 hover:bg-gray-100 hover:text-red-500 group-hover:block"
                    title="删除这条通知"
                    onClick={(e) => {
                      e.stopPropagation()
                      deleteMutation.mutate(n.id)
                    }}
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  )
}
