import { useQuery } from '@tanstack/react-query'
import { useEffect } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import { api } from './api/client'
import { ComposeProvider } from './components/compose/ComposeContext'
import ArchivedPage from './pages/ArchivedPage'
import ComposePage from './pages/ComposePage'
import DigestPage from './pages/DigestPage'
import DraftsPage from './pages/DraftsPage'
import InboxPage from './pages/InboxPage'
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
            <Route path="/" element={<InboxPage />} />
            <Route path="/drafts" element={<DraftsPage />} />
            <Route path="/archived" element={<ArchivedPage />} />
            <Route path="/digest" element={<DigestPage />} />
            <Route path="/assistant" element={<ManagerPage />} />
            <Route path="/compose" element={<ComposePage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </ComposeProvider>
    </>
  )
}
