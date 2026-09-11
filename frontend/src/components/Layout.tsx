import { Archive, BarChart3, FilePenLine, Inbox, Settings, Sparkles } from 'lucide-react'
import { useEffect, useRef, useState, type MouseEvent as ReactMouseEvent } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import NotificationBell from './NotificationBell'

const navItems = [
  { to: '/', label: '收件箱', icon: Inbox },
  { to: '/drafts', label: '待审草稿', icon: FilePenLine },
  { to: '/archived', label: '已归档', icon: Archive },
  { to: '/digest', label: '每日摘要', icon: BarChart3 },
  { to: '/assistant', label: 'AI 总管家', icon: Sparkles },
]

const NAV_MIN = 96
const NAV_MAX = 240
const NAV_DEFAULT = 148
const ICON_ONLY_BELOW = 132 // 窄于此宽度切换为纯图标模式

export default function Layout() {
  const [navWidth, setNavWidth] = useState(() => {
    const saved = Number(localStorage.getItem('nmail_nav_width'))
    return saved >= NAV_MIN && saved <= NAV_MAX ? saved : NAV_DEFAULT
  })
  const dragging = useRef(false)
  const widthRef = useRef(navWidth)
  widthRef.current = navWidth

  // 侧栏从视口左缘开始，宽度即鼠标 X
  const startDrag = (e: ReactMouseEvent) => {
    e.preventDefault()
    dragging.current = true
    document.body.classList.add('dragging-col')
  }

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!dragging.current) return
      // 全局 zoom 会缩放视觉坐标，换算回布局 px
      const zoom = Number(getComputedStyle(document.documentElement).getPropertyValue('--app-zoom')) || 1
      const w = Math.min(NAV_MAX, Math.max(NAV_MIN, e.clientX / zoom))
      widthRef.current = w
      setNavWidth(w)
    }
    const onUp = () => {
      if (!dragging.current) return
      dragging.current = false
      document.body.classList.remove('dragging-col')
      localStorage.setItem('nmail_nav_width', String(widthRef.current))
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
    return () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
  }, [])

  const iconOnly = navWidth <= ICON_ONLY_BELOW
  const navLinkClass = (isActive: boolean) =>
    `flex items-center rounded-lg px-2 py-1.5 t-sm transition-colors ${
      iconOnly ? 'justify-center' : 'gap-2'
    } ${
      isActive
        ? 'bg-indigo-50 font-medium text-indigo-700'
        : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
    }`

  return (
    <div className="flex h-screen bg-gray-50 text-gray-900">
      <aside
        className="relative flex shrink-0 flex-col border-r border-gray-200 bg-white"
        style={{ width: navWidth }}
      >
        <div className={`flex items-center py-4 ${iconOnly ? 'justify-center px-1' : 'gap-2 px-4'}`}>
          {/* 应用专属图标（与浏览器标签页 favicon 同源） */}
          <img src="/icon-192.png" alt="Nmail" className="h-[18px] w-[18px] shrink-0 rounded-[4px]" />
          {!iconOnly && <span className="truncate text-sm font-bold tracking-tight">Nmail</span>}
        </div>
        <nav className={`flex-1 space-y-0.5 ${iconOnly ? 'px-1.5' : 'px-2.5'}`}>
          {navItems.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              title={label}
              className={({ isActive }) => navLinkClass(isActive)}
            >
              <Icon className="h-4 w-4 shrink-0" />
              {!iconOnly && <span className="truncate">{label}</span>}
            </NavLink>
          ))}
        </nav>
        <div className={`flex items-center border-t border-gray-200 py-2 ${iconOnly ? 'flex-col gap-1 px-1.5' : 'gap-1 px-2.5'}`}>
          <NotificationBell />
          <NavLink
            to="/settings"
            title="设置"
            className={({ isActive }) => `${navLinkClass(isActive)} flex-1`}
          >
            <Settings className="h-4 w-4 shrink-0" />
            {!iconOnly && <span className="truncate">设置</span>}
          </NavLink>
        </div>
        {/* 拖拽手柄：贴右缘整条高度，双击复位 */}
        <div
          onMouseDown={startDrag}
          onDoubleClick={() => {
            setNavWidth(NAV_DEFAULT)
            localStorage.setItem('nmail_nav_width', String(NAV_DEFAULT))
          }}
          className="absolute inset-y-0 -right-1 z-10 w-2 cursor-col-resize hover:bg-indigo-200/60"
          title="拖拽调整侧栏宽度（双击复位）"
        />
      </aside>
      {/* 文档流页面（设置/摘要/总管家）依赖此滚动；邮件页自身 h-full 自管滚动 */}
      <main className="min-w-0 flex-1 overflow-y-auto overflow-x-hidden">
        <Outlet />
      </main>
    </div>
  )
}
