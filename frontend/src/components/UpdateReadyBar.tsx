/** 全局更新就绪浮条（UPDATE_AND_DESKTOP.md §3.3）：后台已装好新版本时提示重启。
 * 文字从简（用户定）；叉掉即等下次打开自动生效——按版本记忆，不重复打扰；
 * 重启到新版后启动收尾把已应用的就绪态自愈归位 idle（update_apply），浮条自然消失。 */
import { useQuery } from '@tanstack/react-query'
import { X } from 'lucide-react'
import { useState } from 'react'
import { api } from '../api/client'
import { restartForUpdateThenReload } from '../utils/updateRestart'

const DISMISS_KEY = 'nmail_update_banner_dismissed'

export default function UpdateReadyBar() {
  const [restarting, setRestarting] = useState(false)
  const [dismissedVersion, setDismissedVersion] = useState<string | null>(
    () => localStorage.getItem(DISMISS_KEY),
  )
  const applyQuery = useQuery({
    queryKey: ['update-apply'],
    queryFn: api.getUpdateApply,
    refetchInterval: 60_000,
    staleTime: 30_000,
  })
  const a = applyQuery.data
  // 后台进行中不打扰（设置页有全状态）；仅「就绪且未重启」时出现
  const visible = a && a.phase === 'ready' && a.staged_version
    && a.staged_version !== a.current_version
    && dismissedVersion !== a.staged_version
  if (!visible) return null
  return (
    <div className="fixed inset-x-0 bottom-5 z-50 flex justify-center px-4">
      <div className="flex items-center gap-3 rounded-full border border-gray-200 bg-white py-2.5 pl-5 pr-3 shadow-lg">
        <span className="t-sm text-gray-700">
          新版本 <b>{a!.staged_version}</b> 已就绪，重启即更新；下次打开自动生效
        </span>
        <button
          className="rounded-full bg-indigo-600 px-3 py-1 t-sm text-white hover:bg-indigo-500 disabled:opacity-50"
          onClick={() => {
            setRestarting(true)
            restartForUpdateThenReload(a!.current_version)
          }}
          disabled={restarting}
        >
          {restarting ? '重启中…' : '立即重启'}
        </button>
        <button
          title="知道了（下次打开自动生效）"
          className="text-gray-400 hover:text-gray-600"
          onClick={() => {
            localStorage.setItem(DISMISS_KEY, a!.staged_version ?? '')
            setDismissedVersion(a!.staged_version ?? null)
          }}
        >
          <X className="h-4 w-4" />
        </button>
      </div>
    </div>
  )
}
