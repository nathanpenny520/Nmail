import { Archive, BarChart3, FilePenLine, Inbox, Mail, Settings } from 'lucide-react'
import { NavLink, Outlet } from 'react-router-dom'

const navItems = [
  { to: '/', label: '收件箱', icon: Inbox },
  { to: '/drafts', label: '待审草稿', icon: FilePenLine },
  { to: '/archived', label: '已归档', icon: Archive },
  { to: '/digest', label: '每日摘要', icon: BarChart3 },
]

const navLinkClass = (isActive: boolean) =>
  `flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors ${
    isActive
      ? 'bg-indigo-50 font-medium text-indigo-700'
      : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
  }`

export default function Layout() {
  return (
    <div className="flex h-screen bg-gray-50 text-gray-900">
      <aside className="flex w-56 shrink-0 flex-col border-r border-gray-200 bg-white">
        <div className="flex items-center gap-2 px-5 py-5">
          <Mail className="h-6 w-6 text-indigo-600" />
          <span className="text-lg font-bold tracking-tight">Nmail</span>
        </div>
        <nav className="flex-1 space-y-1 px-3">
          {navItems.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) => navLinkClass(isActive)}
            >
              <Icon className="h-4 w-4" />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-gray-200 p-3">
          <NavLink to="/settings" className={({ isActive }) => navLinkClass(isActive)}>
            <Settings className="h-4 w-4" />
            设置
          </NavLink>
        </div>
      </aside>
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  )
}
