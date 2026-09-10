import { useRef, useState, type CSSProperties } from 'react'

interface HtmlMailProps {
  html: string
}

/**
 * HTML 邮件沙箱渲染：sandbox 仅 allow-same-origin（禁止脚本/表单/弹窗），
 * 后端已消毒；允许父级读取 scrollHeight 以自适应高度。
 */
export default function HtmlMail({ html }: HtmlMailProps) {
  const iframeRef = useRef<HTMLIFrameElement>(null)
  const [height, setHeight] = useState(320)

  const handleLoad = () => {
    // 图片等资源异步加载会改变文档高度，加载后多次复测
    const remeasure = [0, 600, 1500, 3000]
    for (const delay of remeasure) {
      setTimeout(() => {
        try {
          const doc = iframeRef.current?.contentDocument
          if (doc?.body) {
            setHeight(Math.max(200, Math.min(doc.body.scrollHeight + 24, 20000)))
          }
        } catch {
          // 沙箱限制下读取失败则保持固定高度（可滚动）
        }
      }, delay)
    }
  }

  const style: CSSProperties = { height, width: '100%', border: 'none' }

  return (
    <iframe
      ref={iframeRef}
      title="邮件正文"
      style={style}
      sandbox="allow-same-origin"
      srcDoc={html}
      onLoad={handleLoad}
    />
  )
}
