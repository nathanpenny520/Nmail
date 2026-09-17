import { useQuery } from '@tanstack/react-query'
import { useEffect } from 'react'
import Layout from './components/Layout'
import { api } from './api/client'
import { ComposeProvider } from './components/compose/ComposeContext'

/** 把设置里的界面字号档位应用到 <html data-font>，全局 CSS 变量随之切换。 */
function FontApplier() {
  const { data } = useQuery({ queryKey: ['settings'], queryFn: api.getSettings, staleTime: Infinity })
  useEffect(() => {
    if (data?.ui_font) {
      document.documentElement.dataset.font = data.ui_font
    }
  }, [data])
  return null
}

export default function App() {
  return (
    <>
      <FontApplier />
      {/* 页面路由由 Layout 内的 keep-alive 页签承载（EXPERIENCE_PLAN B4）：
          五个页面常驻挂载、切页签只显隐——滚动/筛选/选中/聊天记录全保留 */}
      <ComposeProvider>
        <Layout />
      </ComposeProvider>
    </>
  )
}
