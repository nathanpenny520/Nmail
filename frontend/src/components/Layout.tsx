import { BarChart3, Inbox, Pencil, Plus, Settings, Sparkles, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAIEnabled } from '../api/useAI'
import { useCompose } from './compose/ComposeContext'
import ComposeWorkbench from './compose/ComposeWorkbench'
import NotificationBell from './NotificationBell'

/** 右侧图标按钮样式：激活=页面页签正在前台。 */
const iconBtnCls = (active: boolean) =>
  `flex h-8 w-8 shrink-0 items-center justify-center rounded-lg transition-colors ${
    active ? 'bg-indigo-100 text-indigo-700' : 'text-gray-500 hover:bg-gray-200/60 hover:text-indigo-600'
  }`

/**
 * v0.4 导航（REDESIGN_PLAN §3.2）：无应用侧栏。「邮件」是唯一常驻基座页签，
 * 其余页面（AI 总管家/每日摘要/设置）经标签条右侧小图标按钮点击才产生页签；
 * 写信页签由列表操作或 ＋ 按钮产生。
 */
const PAGE_TABS: Record<string, { label: string; icon: typeof Inbox }> = {
  '/digest': { label: '每日摘要', icon: BarChart3 },
  '/assistant': { label: 'AI 总管家', icon: Sparkles },
  '/settings': { label: '设置', icon: Settings },
}

// 纯 AI 页面：AI 停用（传统邮件模式）时从按钮与标签条隐藏
const AI_ONLY_TABS = ['/digest', '/assistant']

/** 主区顶部的标签条：邮件基座（固定）+ 已开启的页面页签 + 写信页签，右侧图标按钮区。 */
function WorkspaceTabs() {
  const { tabs, activeTabId, setActiveTab, openNew, requestClose } = useCompose()
  const location = useLocation()
  const navigate = useNavigate()
  const aiEnabled = useAIEnabled()

  // 页面标签：经右侧图标按钮打开过即留下，去重；记忆在 localStorage，刷新后仍在
  const [pageTabs, setPageTabs] = useState<string[]>(() => {
    try {
      const saved: unknown = JSON.parse(localStorage.getItem('nmail_page_tabs') ?? '[]')
      return Array.isArray(saved) ? saved.filter((p): p is string => typeof p === 'string' && !!PAGE_TABS[p]) : []
    } catch {
      return []
    }
  })
  useEffect(() => {
    localStorage.setItem('nmail_page_tabs', JSON.stringify(pageTabs))
  }, [pageTabs])
  // 直接输 URL / 前进后退进入页面路由时也补一个标签（AI 停用时跳过纯 AI 页面）
  useEffect(() => {
    const path = location.pathname
    if (PAGE_TABS[path] && (aiEnabled || !AI_ONLY_TABS.includes(path))) {
      setPageTabs((prev) => (prev.includes(path) ? prev : [...prev, path]))
    }
  }, [location.pathname, aiEnabled])

  const closePageTab = (path: string) => {
    setPageTabs((prev) => prev.filter((p) => p !== path))
    if (location.pathname === path) navigate('/')
  }

  const inboxActive = activeTabId === null && location.pathname === '/'
  // 统一宽度：所有页签同宽（浏览器式），标题超长截断（审核意见：长短不一观感差）
  const tabCls = (active: boolean) =>
    `flex w-44 shrink-0 items-center gap-1.5 rounded-t-lg border border-b-0 px-3 py-1.5 t-sm transition-colors ${
      active
        ? 'border-gray-200 bg-white font-medium text-indigo-700'
        : 'border-transparent text-gray-500 hover:bg-gray-200/60'
    }`
  // 页面页签已开启且正激活时，右侧对应图标亮起
  const iconActive = (path: string) => activeTabId === null && location.pathname === path

  return (
    <div className="flex shrink-0 items-stretch border-b border-gray-200 bg-gray-100 pl-2 pr-1.5">
      <div className="flex min-w-0 flex-1 items-end gap-1 overflow-x-auto pt-1.5">
        {/* 应用标识（与浏览器标签页 favicon 同源） */}
        <img src="/icon-192.png" alt="Nmail" className="mb-1.5 mr-0.5 h-4 w-4 shrink-0 self-center rounded-[4px]" />
        <button
          className={tabCls(inboxActive)}
          onClick={() => {
            if (location.pathname !== '/') navigate('/')
            setActiveTab(null)
          }}
        >
          <Inbox className="h-3.5 w-3.5 shrink-0" />
          <span className="whitespace-nowrap">邮件</span>
        </button>
        {pageTabs.filter((path) => aiEnabled || !AI_ONLY_TABS.includes(path)).map((path) => {
          const meta = PAGE_TABS[path]
          const Icon = meta.icon
          const active = activeTabId === null && location.pathname === path
          return (
            <div
              key={path}
              onClick={() => {
                if (location.pathname !== path) navigate(path)
                setActiveTab(null)
              }}
              className={`${tabCls(active)} cursor-pointer group`}
              title={meta.label}
            >
              <Icon className="h-3.5 w-3.5 shrink-0" />
              <span className="min-w-0 flex-1 truncate">{meta.label}</span>
              <button
                className="shrink-0 text-gray-400 opacity-0 transition-opacity hover:text-gray-700 group-hover:opacity-100"
                onClick={(e) => {
                  e.stopPropagation()
                  closePageTab(path)
                }}
                title="关闭标签"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          )
        })}
        {tabs.map((tab) => (
          <div
            key={tab.tabId}
            onClick={() => setActiveTab(tab.tabId)}
            className={`${tabCls(tab.tabId === activeTabId)} cursor-pointer group`}
            title={tab.title}
          >
            {tab.dirty && <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-amber-400" title="有未保存改动" />}
            <Pencil className="h-3 w-3 shrink-0" />
            <span className="min-w-0 flex-1 truncate">{tab.title}</span>
            <button
              className="shrink-0 text-gray-400 opacity-0 transition-opacity hover:text-gray-700 group-hover:opacity-100"
              onClick={(e) => {
                e.stopPropagation()
                requestClose(tab.tabId)
              }}
              title="关闭标签"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        ))}
      </div>
      {/* 右侧图标按钮区：AI 总管家/每日摘要已移入树「智能视图」（审核意见），此处仅剩通知/设置/写信 */}
      <div className="flex shrink-0 items-center gap-0.5 pb-1.5 pl-1.5">
        <NotificationBell />
        <IconTab to="/settings" icon={Settings} title="设置" active={iconActive('/settings')} />
        <button
          className={iconBtnCls(false)}
          onClick={() => openNew()}
          title="新邮件"
        >
          <Plus className="h-4 w-4" />
        </button>
      </div>
    </div>
  )
}

/** 右侧图标按钮：点击打开对应页面（产生或激活页签）。 */
function IconTab({
  to,
  icon: Icon,
  title,
  active,
}: {
  to: string
  icon: typeof Inbox
  title: string
  active: boolean
}) {
  const navigate = useNavigate()
  const location = useLocation()
  const { setActiveTab } = useCompose()
  return (
    <button
      className={iconBtnCls(active)}
      title={title}
      aria-label={title}
      onClick={() => {
        if (location.pathname !== to) navigate(to)
        setActiveTab(null)
      }}
    >
      <Icon className="h-4 w-4" />
    </button>
  )
}

export default function Layout() {
  const composing = useCompose().activeTabId !== null

  return (
    <div className="flex h-full flex-col bg-gray-50 text-gray-900">
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
  )
}
