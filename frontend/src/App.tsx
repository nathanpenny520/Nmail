import { useQuery } from '@tanstack/react-query'
import { useEffect } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import { api } from './api/client'
import { ComposeProvider } from './components/compose/ComposeContext'
import DigestPage from './pages/DigestPage'
import DraftsHubPage from './pages/DraftsHubPage'
import MailPage from './pages/MailPage'
import ManagerPage from './pages/ManagerPage'
import SettingsPage from './pages/SettingsPage'

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
      <ComposeProvider>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/" element={<MailPage />} />
            {/* 草稿为页面页签（v0.4.x 修订）；/mydrafts 旧路由并入，/?view=drafts 旧深链在 MailPage 兜底重定向 */}
            <Route path="/drafts" element={<DraftsHubPage />} />
            <Route path="/mydrafts" element={<Navigate to="/drafts" replace />} />
            {/* v0.4 §4.6：本地归档视图退役，Archived 在各账号文件夹树中 */}
            <Route path="/archived" element={<Navigate to="/" replace />} />
            <Route path="/digest" element={<DigestPage />} />
            <Route path="/assistant" element={<ManagerPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </ComposeProvider>
    </>
  )
}
