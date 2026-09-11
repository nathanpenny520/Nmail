import { Archive, BarChart3, FilePenLine, FileText, Inbox, Pencil, Plus, Settings, Sparkles, X } from 'lucide-react'
import { useEffect, useRef, useState, type MouseEvent as ReactMouseEvent } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useCompose } from './compose/ComposeContext'
import ComposeWorkbench from './compose/ComposeWorkbench'
import NotificationBell from './NotificationBell'

const navItems = [
  { to: '/', label: '收件箱', icon: Inbox },
  { to: '/drafts', label: '待审草稿', icon: FilePenLine },
  { to: '/mydrafts', label: '草稿箱', icon: FileText },
  { to: '/archived', label: '已归档', icon: Archive },
  { to: '/digest', label: '每日摘要', icon: BarChart3 },
  { to: '/assistant', label: 'AI 总管家', icon: Sparkles },
]

const NAV_MIN = 96
const NAV_MAX = 240
const NAV_DEFAULT = 148
const ICON_ONLY_BELOW = 132 // 窄于此宽度切换为纯图标模式

/** 主区顶部的同层标签条：收件箱（固定）+ 各写信标签，一键互切（对齐网页邮箱）。 */
function WorkspaceTabs() {
  const { tabs, activeComposeId, setActiveCompose, openNew, requestClose } = useCompose()
  const location = useLocation()
  const navigate = useNavigate()
  const onMailRoute = location.pathname === '/' || location.pathname === '/archived'

  // 无写信标签且不在邮件页时不占位（设置/摘要/总管家保持干净）
  if (tabs.length === 0 && !onMailRoute) return null

  const inboxActive = activeComposeId === null && onMailRoute
  const mailLabel = location.pathname === '/archived' ? '已归档' : '收件箱'
  const tabCls = (active: boolean) =>
    `flex min-w-0 shrink-0 items-center gap-1.5 rounded-t-lg border border-b-0 px-3 py-1.5 t-sm transition-colors ${
      active
        ? 'border-gray-200 bg-white font-medium text-indigo-700'
        : 'border-transparent text-gray-500 hover:bg-gray-200/60'
    }`

  return (
    <div className="flex shrink-0 items-end gap-1 overflow-x-auto border-b border-gray-200 bg-gray-100 px-2 pt-1.5">
      <button
        className={tabCls(inboxActive)}
        onClick={() => {
          if (!onMailRoute) navigate('/')
          setActiveCompose(null)
        }}
      >
        <Inbox className="h-3.5 w-3.5 shrink-0" />
        <span className="whitespace-nowrap">{mailLabel}</span>
      </button>
      {tabs.map((tab) => (
        <div
          key={tab.draftId}
          onClick={() => setActiveCompose(tab.draftId)}
          className={`${tabCls(tab.draftId === activeComposeId)} max-w-56 cursor-pointer group`}
          title={tab.title}
        >
          {tab.dirty && <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-amber-400" title="有未保存改动" />}
          <Pencil className="h-3 w-3 shrink-0" />
          <span className="truncate">{tab.title}</span>
          <button
            className="shrink-0 text-gray-400 opacity-0 transition-opacity hover:text-gray-700 group-hover:opacity-100"
            onClick={(e) => {
              e.stopPropagation()
              requestClose(tab.draftId)
            }}
            title="关闭标签"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      ))}
      <button
        className="mb-1 flex shrink-0 items-center rounded-md p-1 text-gray-500 transition-colors hover:bg-gray-200/60 hover:text-indigo-600"
        onClick={() => void openNew()}
        title="新邮件"
      >
        <Plus className="h-4 w-4" />
      </button>
    </div>
  )
}

export default function Layout() {
  const [navWidth, setNavWidth] = useState(() => {
    const saved = Number(localStorage.getItem('nmail_nav_width'))
    return saved >= NAV_MIN && saved <= NAV_MAX ? saved : NAV_DEFAULT
  })
  const dragging = useRef(false)
  const widthRef = useRef(navWidth)
  widthRef.current = navWidth
  const { activeComposeId, setActiveCompose } = useCompose()
  const composing = activeComposeId !== null

  // 侧栏从视口左缘开始，宽度即鼠标 X
  const startDrag = (e: ReactMouseEvent) => {
    e.preventDefault()
    dragging.current = true
    document.body.classList.add('dragging-col')
  }

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!dragging.current) return
      // 全局 zoom 与侧栏局部 zoom 叠加，视觉坐标需除以两者乘积换算回布局 px
      const appZoom = Number(getComputedStyle(document.documentElement).getPropertyValue('--app-zoom')) || 1
      const w = Math.min(NAV_MAX, Math.max(NAV_MIN, e.clientX / (appZoom * 0.75)))
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
    <div className="flex h-full bg-gray-50 text-gray-900">
      <aside
        className="zoom-compact relative flex shrink-0 flex-col border-r border-gray-200 bg-white"
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
              onClick={() => setActiveCompose(null)}
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
            onClick={() => setActiveCompose(null)}
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
      <div className="flex min-w-0 flex-1 flex-col">
        <WorkspaceTabs />
        {/* 收件箱等页面在写信时仅隐藏不卸载（keep-alive），切回即恢复列表与阅读状态 */}
        <div className="relative min-h-0 flex-1">
          <main
            className={`h-full overflow-y-auto overflow-x-hidden ${composing ? 'hidden' : 'block'}`}
          >
            <Outlet />
          </main>
          {composing && (
            <div className="absolute inset-0 z-20 min-h-0">
              <ComposeWorkbench />
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
