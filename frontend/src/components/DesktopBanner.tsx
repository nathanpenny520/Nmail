/** 首跑横幅（UPDATE_AND_DESKTOP.md §7.2，2026-09-18 用户拍板「弹出一次即可」）：
 * 未装桌面图标且没看过横幅时，页面底部浮出一次性引导。**显示即记**——后端
 * banner-seen 在渲染时调用，关掉浏览器没选也不二次纠缠；安装成功自动收起。 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { api } from '../api/client'

export default function DesktopBanner() {
  const queryClient = useQueryClient()
  const [closing, setClosing] = useState(false)
  const statusQuery = useQuery({
    queryKey: ['desktop-shortcut'],
    queryFn: api.getDesktopShortcut,
    staleTime: 30_000,
  })
  const seenMutation = useMutation({ mutationFn: () => api.markDesktopBannerSeen() })
  const installMutation = useMutation({
    mutationFn: () => api.installDesktopShortcut(),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['desktop-shortcut'] })
      setClosing(true)
    },
  })
  const s = statusQuery.data

  // 显示即记：横幅真正渲染的这一轮标记，之后永不再弹
  useEffect(() => {
    if (s?.banner && !closing) seenMutation.mutate()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [s?.banner, closing])

  if (!s || !s.banner || closing) return null
  return (
    <div className="fixed inset-x-0 bottom-4 z-40 flex justify-center px-4">
      <div className="flex max-w-xl flex-wrap items-center gap-3 rounded-xl border border-gray-200 bg-white px-4 py-3 shadow-lg">
        <div className="t-md font-medium text-gray-700">把 Nmail 放到桌面</div>
        <span className="t-sm text-gray-400">
          创建桌面图标，下次双击直达，无需命令行
        </span>
        <span className="flex-1" />
        <button
          className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 t-sm text-gray-500 hover:bg-gray-50"
          onClick={() => setClosing(true)}
        >
          关闭
        </button>
        <button
          className="rounded-lg bg-indigo-600 px-3 py-1.5 t-sm text-white hover:bg-indigo-500 disabled:opacity-50"
          onClick={() => installMutation.mutate()}
          disabled={installMutation.isPending}
        >
          {installMutation.isPending ? '安装中…' : '立即安装'}
        </button>
        {installMutation.isError && (
          <p className="w-full t-sm text-red-600">
            安装失败：{(installMutation.error as Error).message}
          </p>
        )}
      </div>
    </div>
  )
}
