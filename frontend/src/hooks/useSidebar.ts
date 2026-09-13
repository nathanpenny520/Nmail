import { useSyncExternalStore } from 'react'

/**
 * 文件夹树折叠状态（v0.4 汉堡主菜单，Gmail 式）：w-48 完整树 ⇄ w-14 图标栏。
 * 状态记忆在 localStorage（跨页签切换、刷新后保留）；汉堡在 Layout、树在
 * MailPage 是两棵组件树，靠自定义事件 + useSyncExternalStore 联动，不引 Provider。
 */
const KEY = 'nmail_tree_collapsed'
const EVENT = 'nmail-tree-collapsed'

const subscribe = (onChange: () => void) => {
  window.addEventListener(EVENT, onChange)
  return () => window.removeEventListener(EVENT, onChange)
}

const read = (): boolean => {
  try {
    return localStorage.getItem(KEY) === '1'
  } catch {
    return false
  }
}

/** 当前是否折叠（折叠态渲染由 FolderTree 消费，按钮态由 Layout 消费）。 */
export function useTreeCollapsed(): boolean {
  return useSyncExternalStore(subscribe, read)
}

export function setTreeCollapsed(collapsed: boolean) {
  try {
    localStorage.setItem(KEY, collapsed ? '1' : '0')
  } catch { /* 隐私模式等 localStorage 不可用时仅本态生效 */ }
  window.dispatchEvent(new Event(EVENT))
}

export function toggleTreeCollapsed() {
  setTreeCollapsed(!read())
}
