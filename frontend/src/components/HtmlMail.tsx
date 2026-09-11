import { useQuery } from '@tanstack/react-query'
import { useCallback, useEffect, useRef, useState, type CSSProperties } from 'react'
import { api } from '../api/client'

interface HtmlMailProps {
  html: string
}

/**
 * HTML 邮件沙箱渲染：sandbox 仅 allow-same-origin（禁止脚本/表单/弹窗），
 * 后端已消毒；允许父级读取 scrollHeight 以自适应高度。
 * 正文字号缩放独立于界面字号（zoom 注入沙箱）。
 */
const BODY_ZOOM: Record<string, number> = { small: 0.85, standard: 1, large: 1.15 }

export default function HtmlMail({ html }: HtmlMailProps) {
  const iframeRef = useRef<HTMLIFrameElement>(null)
  const [height, setHeight] = useState(320)
  const { data: settings } = useQuery({
    queryKey: ['settings'],
    queryFn: api.getSettings,
    staleTime: Infinity,
  })
  const zoom = BODY_ZOOM[settings?.body_font ?? 'standard'] ?? 1

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

  const handleLoad = () => {
    // 图片等资源异步加载会改变文档高度，加载后多次复测
    for (const delay of [0, 500, 1200, 2500, 4000]) {
      setTimeout(remeasure, delay)
    }
  }

  // 窗口尺寸变化时复测（换行数变化会改变文档高度）
  useEffect(() => {
    window.addEventListener('resize', remeasure)
    return () => window.removeEventListener('resize', remeasure)
  }, [remeasure])

  const style: CSSProperties = { height, width: '100%', border: 'none' }

  return (
    <iframe
      ref={iframeRef}
      title="邮件正文"
      style={style}
      sandbox="allow-same-origin"
      srcDoc={`<style>html{zoom:${zoom}}</style>` + html}
      onLoad={handleLoad}
    />
  )
}
