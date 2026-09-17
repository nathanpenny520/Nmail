import { createContext, useContext, type ReactNode } from 'react'

/** 当前前台页签的路由 path。Layout（keep-alive 常驻页签，EXPERIENCE_PLAN B4）提供；
 *  页面组件据此门控轮询与全局键盘监听——隐藏页签不拉取、不响应按键。 */
const PageActiveContext = createContext<string>('/')

export function PageActiveProvider({ path, children }: { path: string; children: ReactNode }) {
  return <PageActiveContext.Provider value={path}>{children}</PageActiveContext.Provider>
}

/** 无参：返回当前前台 path；传 path：返回该页签是否在前台。 */
export function usePageActive(pagePath?: string): string | boolean {
  const active = useContext(PageActiveContext)
  return pagePath ? active === pagePath : active
}
