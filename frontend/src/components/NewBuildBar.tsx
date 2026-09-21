/** 新构建已就绪浮条（S-0921）：后端更新前端后，已打开的页面跑在内存里不会自己换
 * JS——每 30s 轮询 /api/meta 的构建指纹，与自身编译期注入的 __BUILD_ID__ 比对，
 * 不一致提示一键刷新。dev 模式热更新自带，不启用；后端无指纹（旧 dist）不提示。 */
import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'

export default function NewBuildBar() {
  const { data } = useQuery({
    queryKey: ['frontend-build'],
    queryFn: api.getMeta,
    refetchInterval: 30_000,
    staleTime: 20_000,
  })
  if (import.meta.env.DEV) return null
  const served = data?.frontend_build
  if (!served || served === __BUILD_ID__) return null
  return (
    <div className="fixed inset-x-0 bottom-5 z-50 flex justify-center px-4">
      <div className="flex items-center gap-3 rounded-full border border-indigo-200 bg-white py-2.5 pl-5 pr-3 shadow-lg">
        <span className="t-sm text-gray-700">Nmail 已更新，刷新启用新界面</span>
        <button
          className="rounded-full bg-indigo-600 px-3 py-1 t-sm text-white hover:bg-indigo-500"
          onClick={() => location.reload()}
        >
          立即刷新
        </button>
      </div>
    </div>
  )
}
