import { useQuery } from '@tanstack/react-query'
import { useCallback, useEffect, useRef, useState, type CSSProperties } from 'react'
import { api } from '../api/client'

interface HtmlMailProps {
  html: string
}

/**
 * HTML 邮件沙箱渲染：sandbox 仅 allow-same-origin + allow-popups（禁止脚本/表单/顶层导航），
 * 后端已消毒且 http(s) 链接强制 target="_blank"——点击在新标签打开（escaped sandbox），
 * 避免 iframe 内导航被目标站 X-Frame-Options 拒绝（「拒绝连接」）。
 * 允许父级读取 scrollHeight 以自适应高度：body 挂 ResizeObserver，
 * 图片等异步资源加载改变高度时即时复测（定时复测仅兜底）。
 * 正文字号缩放独立于界面字号（zoom 注入沙箱，见下方 UI_ZOOM 校正）。
 */
const BODY_ZOOM: Record<string, number> = { small: 0.85, standard: 1, large: 1.15 }
// 界面三档的全局缩放（与 index.css 各档 --app-zoom 保持一致）。正文档位语义 =
// 对邮件原始字号的缩放；iframe 处在全局 zoom 子树内会被一起缩，注入前先除掉
// 界面档位——否则两档相乘（紧凑 0.85 × 小 0.85 = 0.72，「都调小」时正文特别小，
// 且紧凑界面下正文档选「标准」也到不了原始大小）。从设置读而非 computedStyle：
// 同一次渲染即响应界面字号切换，不等 CSS 变量应用时序。
const UI_ZOOM: Record<string, number> = { compact: 0.85, standard: 1, large: 1.12 }

export default function HtmlMail({ html }: HtmlMailProps) {
  const iframeRef = useRef<HTMLIFrameElement>(null)
  const observerRef = useRef<ResizeObserver | null>(null)
  const [height, setHeight] = useState(320)
  const { data: settings } = useQuery({
    queryKey: ['settings'],
    queryFn: api.getSettings,
    staleTime: Infinity,
  })
  const appZoom = UI_ZOOM[settings?.ui_font ?? 'standard'] ?? 1
  const zoom = (BODY_ZOOM[settings?.body_font ?? 'standard'] ?? 1) / appZoom

  const remeasure = useCallback(() => {
    try {
      const doc = iframeRef.current?.contentDocument
      if (doc?.body) {
        setHeight(Math.max(200, Math.min(doc.body.scrollHeight + 24, 40000)))
      }
    } catch {
      // 沙箱限制下读取失败则保持固定高度（可滚动）
    }
  }, [])

  const setup = useCallback(() => {
    remeasure()
    // 图片等资源异步加载会改变文档高度：ResizeObserver 即时复测，定时复测兜底
    const doc = iframeRef.current?.contentDocument
    observerRef.current?.disconnect()
    if (doc?.body && typeof ResizeObserver !== 'undefined') {
      const observer = new ResizeObserver(remeasure)
      observer.observe(doc.body)
      observerRef.current = observer
    }
    for (const delay of [500, 1200, 2500, 4000]) {
      setTimeout(remeasure, delay)
    }
  }, [remeasure])

  // 测高链路不能依赖 onLoad：React 18 对 srcdoc iframe 存在竞态——load 事件
  // 可能在 React 挂上监听之前就已触发（实测表现为 style 永远停在初始 320px、
  // 邮件被裁剪只剩上半截）。因此挂载后独立轮询到文档就绪再完成测量与监听注册，
  // onLoad 仅作提前触发；srcDoc 变更（换邮件/字号档位）会整文档重载，需重跑。
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined
    let tries = 0
    const poll = () => {
      const doc = iframeRef.current?.contentDocument
      if (doc?.body) {
        setup()
        return
      }
      if (++tries < 50) timer = setTimeout(poll, 100)
    }
    timer = setTimeout(poll, 100)
    return () => {
      clearTimeout(timer)
      observerRef.current?.disconnect()
    }
  }, [setup, html, zoom])

  // 窗口尺寸变化时复测（换行数变化会改变文档高度）
  useEffect(() => {
    window.addEventListener('resize', remeasure)
    return () => {
      window.removeEventListener('resize', remeasure)
      observerRef.current?.disconnect()
    }
  }, [remeasure])

  const style: CSSProperties = { height, width: '100%', border: 'none' }

  return (
    <iframe
      ref={iframeRef}
      title="邮件正文"
      style={style}
      sandbox="allow-same-origin allow-popups allow-popups-to-escape-sandbox"
      srcDoc={`<style>html{zoom:${zoom}}</style>` + html}
      onLoad={setup}
    />
  )
}
