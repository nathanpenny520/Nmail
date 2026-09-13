import { useRef, useState, type MouseEvent as ReactMouseEvent } from 'react'

/**
 * 可拖拽分栏分隔条（v0.4.x，浏览器/VSCode 式）：hover/拖拽中靛蓝高亮，双击复位；
 * 全局 col-resize 光标与禁选中由 body.dragging-col 承担（index.css）。
 * 两种形态：
 * - 默认（bar）：flex 布局中的 1px 视觉线兄弟元素，两侧各 6px 透明热区（细线好拖准）；
 * - edge：覆盖在面板边缘的透明热区——右停靠浮层（AI 助手）用，面板自带 border-l 作视觉线。
 * 坐标换算归消费方：onMove 给原始 MouseEvent，消费方结合自身 rect 与 appZoom() 算宽度。
 */
export default function SplitDivider({
  onMove,
  onReset,
  onDragStart,
  onDragEnd,
  edge = false,
  title = '拖拽调整宽度（双击复位）',
}: {
  onMove: (e: MouseEvent) => void
  onReset: () => void
  /** 拖拽开始/结束（消费方如需在拖拽中关宽度 transition 用） */
  onDragStart?: () => void
  onDragEnd?: () => void
  edge?: boolean
  title?: string
}) {
  const [dragging, setDragging] = useState(false)
  // 经 ref 转发最新回调：监听器只挂/卸一次，不随渲染重建
  const onMoveRef = useRef(onMove)
  onMoveRef.current = onMove

  const startDrag = (e: ReactMouseEvent) => {
    if (e.button !== 0) return
    e.preventDefault()
    setDragging(true)
    onDragStart?.()
    document.body.classList.add('dragging-col')
    const move = (ev: MouseEvent) => onMoveRef.current(ev)
    const up = () => {
      setDragging(false)
      onDragEnd?.()
      document.body.classList.remove('dragging-col')
      window.removeEventListener('mousemove', move)
      window.removeEventListener('mouseup', up)
    }
    window.addEventListener('mousemove', move)
    window.addEventListener('mouseup', up)
  }

  const handlers = {
    onMouseDown: startDrag,
    onDoubleClick: onReset,
    title,
    role: 'separator' as const,
    'aria-orientation': 'vertical' as const,
  }

  if (edge) {
    return (
      <div
        {...handlers}
        className={`absolute inset-y-0 -left-1.5 z-10 w-3 cursor-col-resize transition-colors ${
          dragging ? 'bg-indigo-400/40' : 'hover:bg-indigo-400/40'
        }`}
      />
    )
  }
  return (
    <div
      {...handlers}
      className={`relative w-px shrink-0 cursor-col-resize transition-colors ${
        dragging ? 'bg-indigo-400' : 'bg-gray-200 hover:bg-indigo-400'
      }`}
    >
      {/* 透明热区：细线难对准，±6px 内都可按下 */}
      <div className="absolute inset-y-0 -left-1.5 -right-1.5" />
    </div>
  )
}
