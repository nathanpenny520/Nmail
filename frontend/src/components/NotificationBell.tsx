import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Bell, BellRing } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'

type NotifyPermission = 'default' | 'granted' | 'denied' | 'unsupported'

function notifyPermission(): NotifyPermission {
  if (typeof window === 'undefined' || !('Notification' in window)) return 'unsupported'
  return Notification.permission as NotifyPermission
}

export default function NotificationBell() {
  const [open, setOpen] = useState(false)
  const [perm, setPerm] = useState<NotifyPermission>(notifyPermission())
  const queryClient = useQueryClient()
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
    if (prevIds.current !== null && notifyPermission() === 'granted') {
      for (const item of data.items) {
        if (!prevIds.current.has(item.id) && !item.is_read) {
          try {
            const n = new Notification(item.title, { body: item.body ?? '', tag: `nmail-${item.id}` })
            n.onclick = () => window.focus()
          } catch {
            // 通知构造失败（如无头环境）静默忽略
          }
        }
      }
    }
    prevIds.current = ids
  }, [data])

  const readAllMutation = useMutation({
    mutationFn: api.markNotificationsRead,
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['notifications'] }),
  })

  return (
    <div className="relative">
      <button
        className="relative flex h-8 w-8 items-center justify-center rounded-lg text-gray-500 hover:bg-gray-100 hover:text-gray-800"
        onClick={() => setOpen((v) => !v)}
        title="通知"
      >
        <Bell className="h-4 w-4" />
        {unread > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-bold leading-none text-white">
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
          <div className="absolute bottom-0 left-10 z-40 mb-1 w-80 rounded-xl border border-gray-200 bg-white shadow-xl">
            <div className="flex items-center justify-between border-b border-gray-100 px-4 py-2.5">
              <span className="text-xs font-semibold text-gray-700">通知中心</span>
              {unread > 0 && (
                <button
                  className="text-[11px] text-indigo-600 hover:underline"
                  onClick={() => readAllMutation.mutate()}
                >
                  全部已读
                </button>
              )}
            </div>
            <div className="max-h-80 overflow-y-auto">
              {(data?.items.length ?? 0) === 0 && (
                <div className="px-4 py-8 text-center text-xs text-gray-300">暂无通知</div>
              )}
              {data?.items.map((n) => (
                <div
                  key={n.id}
                  className={`border-b border-gray-50 px-4 py-2.5 ${n.is_read ? '' : 'bg-indigo-50/50'}`}
                >
                  <div className="flex items-start gap-2">
                    {!n.is_read && <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-indigo-500" />}
                    <div className="min-w-0">
                      <div className="truncate text-xs font-medium text-gray-800">{n.title}</div>
                      {n.body && <div className="mt-0.5 line-clamp-2 text-[11px] text-gray-500">{n.body}</div>}
                      <div className="mt-0.5 text-[10px] text-gray-300">{n.created_at}</div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  )
}
