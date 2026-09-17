import { BarChart3, FilePenLine, Inbox, Menu, Pencil, Settings, Sparkles, SquarePen, X } from 'lucide-react'
import { useEffect, useState, type DragEvent as ReactDragEvent, type ReactNode } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import { useAIEnabled } from '../api/useAI'
import { PageActiveProvider } from '../hooks/usePageActive'
import { toggleTreeCollapsed, useTreeCollapsed } from '../hooks/useSidebar'
import DigestPage from '../pages/DigestPage'
import DraftsHubPage from '../pages/DraftsHubPage'
import MailPage from '../pages/MailPage'
import ManagerPage from '../pages/ManagerPage'
import SettingsPage from '../pages/SettingsPage'
import { useCompose } from './compose/ComposeContext'
import ComposeWorkbench from './compose/ComposeWorkbench'
import NotificationBell from './NotificationBell'
import UpdateReadyBar from './UpdateReadyBar'

/** 右侧图标按钮样式：激活=页面页签正在前台。 */
const iconBtnCls = (active: boolean) =>
  `flex h-8 w-8 shrink-0 items-center justify-center rounded-lg transition-colors ${
    active ? 'bg-indigo-100 text-indigo-700' : 'text-gray-500 hover:bg-gray-200/60 hover:text-indigo-600'
  }`

/**
 * v0.4 导航（REDESIGN_PLAN §3.2）：无应用侧栏。「邮件」是唯一常驻基座页签，
 * 其余页面（AI 总管家/每日摘要/设置）经标签条右侧小图标按钮点击才产生页签；
 * 写信页签由列表操作或右侧笔形按钮（SquarePen）产生，每次点击必新开一封。
 */
const PAGE_TABS: Record<string, { label: string; icon: typeof Inbox }> = {
  '/drafts': { label: '草稿', icon: FilePenLine },
  '/digest': { label: '每日摘要', icon: BarChart3 },
  '/assistant': { label: 'AI 总管家', icon: Sparkles },
  '/settings': { label: '设置', icon: Settings },
}

// 纯 AI 页面：AI 停用（传统邮件模式）时从按钮与标签条隐藏
const AI_ONLY_TABS = ['/digest', '/assistant']

/**
 * 页签统一顺序键（v0.4.x 浏览器式拖拽排序，REDESIGN_PLAN §3.2 增强）：
 * `page:<路由>` ｜ `compose:<tabId>`（写信页签）。「邮件」基座钉死首位不参与，
 * 相当于浏览器的钉选页签。
 */
type TabKey = string

/** 主区顶部的标签条：邮件基座（固定）+ 已开启的页面页签 + 写信页签，右侧图标按钮区。 */
function WorkspaceTabs() {
  const { tabs, activeTabId, setActiveTab, openNew, requestClose, restored } = useCompose()
  const location = useLocation()
  const navigate = useNavigate()
  const aiEnabled = useAIEnabled()
  const treeCollapsed = useTreeCollapsed()

  // 汉堡主菜单（Gmail 式，REDESIGN_PLAN §3.2）：切换文件夹树展开/折叠；
  // 在其他页签点击先跳回邮件基座再切换——侧栏只在基座可见，避免「点了没反应」
  const onMenuClick = () => {
    if (location.pathname !== '/') {
      navigate('/')
      setActiveTab(null)
    }
    toggleTreeCollapsed()
  }

  // 页面标签：经右侧图标按钮打开过即留下，去重。会话级记忆（2026-09-13 用户定版，浏览器行为）：
  // sessionStorage 挂在浏览器标签页上——应用内刷新保留，关闭浏览器标签页/退出应用即归零，
  // 新用户初始化与每次重进都只见「邮件」基座；写信页签本为内存态，行为一致
  const [pageTabs, setPageTabs] = useState<string[]>(() => {
    try {
      const saved: unknown = JSON.parse(sessionStorage.getItem('nmail_page_tabs') ?? '[]')
      return Array.isArray(saved) ? saved.filter((p): p is string => typeof p === 'string' && !!PAGE_TABS[p]) : []
    } catch {
      return []
    }
  })
  useEffect(() => {
    sessionStorage.setItem('nmail_page_tabs', JSON.stringify(pageTabs))
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

  // 页签统一顺序：会话级记忆（与 pageTabs 同生命周期），只存开启中页签的相对顺序——
  // 已关页签剔除、新开页签按打开序追加尾部。「邮件」基座不在序列内（钉死首位）。
  const [tabOrder, setTabOrder] = useState<TabKey[]>(() => {
    try {
      const saved: unknown = JSON.parse(sessionStorage.getItem('nmail_tab_order') ?? '[]')
      return Array.isArray(saved) ? saved.filter((k): k is string => typeof k === 'string') : []
    } catch {
      return []
    }
  })
  useEffect(() => {
    sessionStorage.setItem('nmail_tab_order', JSON.stringify(tabOrder))
  }, [tabOrder])

  // 页面页签先过 AI 停用过滤再进顺序（与渲染口径一致；重新启用后原顺序恢复）
  const pageKeys = pageTabs
    .filter((path) => aiEnabled || !AI_ONLY_TABS.includes(path))
    .map((p) => `page:${p}`)
  const composeKeys = tabs.map((t) => `compose:${t.tabId}`)
  const alive = new Set([...pageKeys, ...composeKeys])
  const orderedKeys = [
    ...[...new Set(tabOrder)].filter((k) => alive.has(k)),
    ...[...pageKeys, ...composeKeys].filter((k) => !tabOrder.includes(k)),
  ]

  // tabOrder 死键清理：页签关闭/恢复换绑后及时剔除失效键（渲染本就过滤，这里保证
  // state 与 sessionStorage 的顺序记忆不积灰）；alive 与 aliveSig 同源同变。
  // 恢复完成前不剪——启动恢复是异步的，期间 compose 键缺席≠页签已关
  const aliveSig = [...alive].sort().join('\n')
  useEffect(() => {
    if (!restored) return
    setTabOrder((prev) => {
      const next = prev.filter((k) => alive.has(k))
      return next.length === prev.length ? prev : next
    })
  }, [aliveSig, restored])

  // 拖拽排序状态：dragKey=拖动中页签（渲染半透明）；dropHint.before=插入点（null=追加到末尾）
  const [dragKey, setDragKey] = useState<TabKey | null>(null)
  const [dropHint, setDropHint] = useState<{ before: TabKey | null } | null>(null)

  const moveTab = (key: TabKey, before: TabKey | null) => {
    const rest = orderedKeys.filter((k) => k !== key)
    const idx = before == null ? rest.length : rest.indexOf(before)
    rest.splice(idx < 0 ? rest.length : idx, 0, key)
    setTabOrder(rest)
  }

  // 与邮件行同一套 HTML5 dnd；插入指示线画在目标页签左缘（后半段悬停=插到下一页签之前）
  const tabDrag = (key: TabKey) => ({
    draggable: true,
    onDragStart: (e: ReactDragEvent) => {
      e.dataTransfer.setData('application/x-nmail-tab', key)
      e.dataTransfer.effectAllowed = 'move'
      setDragKey(key)
    },
    onDragEnd: () => {
      setDragKey(null)
      setDropHint(null)
    },
    onDragOver: (e: ReactDragEvent) => {
      if (dragKey == null || dragKey === key) return
      e.preventDefault()
      e.dataTransfer.dropEffect = 'move'
      const rect = e.currentTarget.getBoundingClientRect()
      const after = e.clientX >= rect.left + rect.width / 2
      const idx = orderedKeys.indexOf(key)
      setDropHint({ before: after ? orderedKeys[idx + 1] ?? null : key })
    },
    onDrop: (e: ReactDragEvent) => {
      e.preventDefault()
      if (dragKey == null) return
      moveTab(dragKey, dropHint?.before ?? null)
      setDragKey(null)
      setDropHint(null)
    },
  })

  // 页签条空白处（目标=容器自身）：允许放置并提示追加到末尾
  const stripDrag = {
    onDragOver: (e: ReactDragEvent) => {
      if (dragKey == null || e.target !== e.currentTarget) return
      e.preventDefault()
      setDropHint({ before: null })
    },
    onDrop: (e: ReactDragEvent) => {
      if (dragKey == null || e.target !== e.currentTarget) return
      e.preventDefault()
      moveTab(dragKey, null)
      setDragKey(null)
      setDropHint(null)
    },
  }

  const inboxActive = activeTabId === null && location.pathname === '/'
  // 统一宽度：所有页签同宽（浏览器式），标题超长截断（审核意见：长短不一观感差）；
  // 2026-09-13 用户反馈 w-44 放不下几个 → 缩至 w-36 并收紧内距，固定标签完整显示、长标题照常截断
  const tabCls = (active: boolean) =>
    `relative flex w-36 shrink-0 items-center gap-1 rounded-t-lg border border-b-0 px-2.5 py-1.5 t-sm transition-colors ${
      active
        ? 'border-gray-200 bg-white font-medium text-indigo-700'
        : 'border-transparent text-gray-500 hover:bg-gray-200/60'
    }`
  // 页面页签已开启且正激活时，右侧对应图标亮起
  const iconActive = (path: string) => activeTabId === null && location.pathname === path

  return (
    <div className="flex shrink-0 items-stretch border-b border-gray-200 bg-gray-100 pl-2 pr-1.5">
      {/* 品牌区：汉堡（折叠文件夹树）+ 应用标识（与浏览器标签页 favicon 同源），整区垂直居中；点标识回邮件基座 */}
      <div className="flex shrink-0 items-center gap-1 pr-1.5">
        <button
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-gray-500 transition-colors hover:bg-gray-200/60 hover:text-gray-700"
          onClick={onMenuClick}
          title={treeCollapsed ? '展开侧栏' : '折叠侧栏'}
          aria-label={treeCollapsed ? '展开侧栏' : '折叠侧栏'}
        >
          <Menu className="h-5 w-5" />
        </button>
        <button
          className="flex shrink-0 items-center gap-1.5 rounded-lg px-1 py-1 transition-colors hover:bg-gray-200/60"
          onClick={() => {
            if (location.pathname !== '/') navigate('/')
            setActiveTab(null)
          }}
          title="回到邮件"
        >
          <img src="/icon-192.png" alt="Nmail" className="h-6 w-6 rounded-[6px]" />
          <span className="t-md font-semibold tracking-tight text-gray-800">Nmail</span>
        </button>
      </div>
      <div className="my-2.5 w-px shrink-0 bg-gray-200" />
      <div className="flex min-w-0 flex-1 items-end gap-1 overflow-x-auto pl-2 pt-1.5" {...stripDrag}>
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
        {/* 页面页签 + 写信页签按统一顺序渲染（拖拽换位；中键关闭，浏览器习惯） */}
        {orderedKeys.map((key) => {
          const dragging = dragKey === key
          const indicator =
            dragKey != null && dropHint?.before === key ? (
              <span className="pointer-events-none absolute -left-[3px] bottom-1 top-1 w-0.5 rounded-full bg-indigo-500" />
            ) : null
          if (key.startsWith('page:')) {
            const path = key.slice(5)
            const meta = PAGE_TABS[path]
            if (!meta) return null
            const Icon = meta.icon
            const active = activeTabId === null && location.pathname === path
            return (
              <div
                key={key}
                onClick={() => {
                  if (location.pathname !== path) navigate(path)
                  setActiveTab(null)
                }}
                onAuxClick={(e) => {
                  if (e.button === 1) {
                    e.preventDefault()
                    closePageTab(path)
                  }
                }}
                {...tabDrag(key)}
                title={meta.label}
                className={`${tabCls(active)} cursor-pointer group ${dragging ? 'opacity-40' : ''}`}
              >
                {indicator}
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
          }
          const tab = tabs.find((t) => `compose:${t.tabId}` === key)
          if (!tab) return null
          return (
            <div
              key={key}
              onClick={() => setActiveTab(tab.tabId)}
              onAuxClick={(e) => {
                if (e.button === 1) {
                  e.preventDefault()
                  requestClose(tab.tabId)
                }
              }}
              {...tabDrag(key)}
              title={tab.title}
              className={`${tabCls(tab.tabId === activeTabId)} cursor-pointer group ${dragging ? 'opacity-40' : ''}`}
            >
              {indicator}
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
          )
        })}
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
          <SquarePen className="h-4 w-4" />
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

/** keep-alive 页签（EXPERIENCE_PLAN B4）：五个页面首次到访即常驻挂载，切页签只
 *  显隐不卸载——滚动位置/筛选/选中邮件/聊天记录/AI 流式输出全部保留。
 *  visibility 隐藏（非 display:none）：布局与滚动位置不丢，且不进 Tab 焦点序与
 *  无障碍树。隐藏页签的轮询与全局键盘监听由 usePageActive 门控。 */
const KEEP_ALIVE_PAGES: { path: string; el: ReactNode }[] = [
  { path: '/', el: <MailPage /> },
  { path: '/drafts', el: <DraftsHubPage /> },
  { path: '/digest', el: <DigestPage /> },
  { path: '/assistant', el: <ManagerPage /> },
  { path: '/settings', el: <SettingsPage /> },
]
const KNOWN_PATHS = new Set(KEEP_ALIVE_PAGES.map((p) => p.path))

export default function Layout() {
  const composing = useCompose().activeTabId !== null
  const { pendingCloseTabId, settleClose } = useCompose()
  const location = useLocation()

  // /?view=drafts 旧深链在 MailPage 内兜底重定向；未知路径回落邮件基座
  const activePath = KNOWN_PATHS.has(location.pathname) ? location.pathname : '/'
  // 首次到访才挂载；挂过后常驻
  const [mounted, setMounted] = useState<Set<string>>(() => new Set([activePath]))
  useEffect(() => {
    setMounted((prev) => (prev.has(activePath) ? prev : new Set([...prev, activePath])))
  }, [activePath])

  // 旧路由与未知路径兜底（原 Routes 重定向：/mydrafts、/archived、* → /）——
  // 重定向渲染必须放在全部 hooks 之后（React hooks 顺序不可条件化）
  if (location.pathname === '/mydrafts') return <Navigate to="/drafts" replace />
  if (location.pathname === '/archived') return <Navigate to="/" replace />
  if (location.pathname !== activePath) return <Navigate to="/" replace />

  return (
    <div className="flex h-full flex-col bg-gray-50 text-gray-900">
      <WorkspaceTabs />
      {/* 更新就绪浮条：后台已装好新版本时全局提示（UPDATE_AND_DESKTOP.md §3.3） */}
      <UpdateReadyBar />
      {/* 收件箱等页面在写信时仅隐藏不卸载（keep-alive），切回即恢复列表与阅读状态 */}
      <div className="relative min-h-0 flex-1">
        <main
          className="absolute inset-0 overflow-hidden"
          style={{ visibility: composing ? 'hidden' : 'visible' }}
        >
          <PageActiveProvider path={activePath}>
            {KEEP_ALIVE_PAGES.map((page) => (
              <div
                key={page.path}
                className="absolute inset-0 overflow-y-auto overflow-x-hidden"
                style={{ visibility: page.path === activePath && !composing ? 'visible' : 'hidden' }}
                aria-hidden={page.path !== activePath}
              >
                {mounted.has(page.path) ? page.el : null}
              </div>
            ))}
          </PageActiveProvider>
        </main>
        {composing && (
          <div className="absolute inset-0 z-20 min-h-0">
            <ComposeWorkbench />
          </div>
        )}
      </div>
      {/* 关闭写信页签的确认——挂在 Layout 常驻渲染：工作台仅激活态挂载，
          放里面则非激活页签点 × 永远见不到弹窗 */}
      {pendingCloseTabId != null && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-6">
          <div className="w-full max-w-sm rounded-2xl bg-white p-5 shadow-2xl">
            <h3 className="t-md font-semibold">关闭页签，草稿怎么处理？</h3>
            <p className="mt-1.5 t-sm text-gray-500">
              保留后草稿仍在草稿箱，下次启动会在工作台自动恢复；丢弃则彻底删除。
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <button
                className="rounded-lg border border-gray-300 px-3 py-1.5 t-sm text-gray-700 hover:bg-gray-50"
                onClick={() => void settleClose(pendingCloseTabId, false)}
              >
                保留草稿
              </button>
              <button
                className="rounded-lg border border-red-200 px-3 py-1.5 t-sm text-red-600 hover:bg-red-50"
                onClick={() => void settleClose(pendingCloseTabId, true)}
              >
                丢弃草稿
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
