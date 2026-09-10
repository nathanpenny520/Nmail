import { Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import ArchivedPage from './pages/ArchivedPage'
import DigestPage from './pages/DigestPage'
import DraftsPage from './pages/DraftsPage'
import InboxPage from './pages/InboxPage'
import SettingsPage from './pages/SettingsPage'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<InboxPage />} />
        <Route path="/drafts" element={<DraftsPage />} />
        <Route path="/archived" element={<ArchivedPage />} />
        <Route path="/digest" element={<DigestPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
