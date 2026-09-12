import type { LucideIcon } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

export interface ContextMenuItem {
  label: string
  icon?: LucideIcon
  danger?: boolean
  disabled?: boolean
  onSelect: () => void
}

/** 右键菜单（VSCode 式）：固定定位 + 视口内夹紧，点击他处/Esc/滚动关闭。 */
export default function ContextMenu({
  x,
  y,
  items,
  onClose,
}: {
  x: number
  y: number
  items: ContextMenuItem[]
  onClose: () => void
}) {
  const ref = useRef<HTMLDivElement>(null)
  const [pos, setPos] = useState({ left: x, top: y })

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const rect = el.getBoundingClientRect()
    setPos({
      left: Math.min(x, window.innerWidth - rect.width - 8),
      top: Math.min(y, window.innerHeight - rect.height - 8),
    })
  }, [x, y])

  useEffect(() => {
    const close = () => onClose()
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('mousedown', close)
    window.addEventListener('keydown', onKey)
    window.addEventListener('resize', close)
    return () => {
      window.removeEventListener('mousedown', close)
      window.removeEventListener('keydown', onKey)
      window.removeEventListener('resize', close)
    }
  }, [onClose])

  return (
    <div
      ref={ref}
      className="fixed z-50 min-w-40 rounded-lg border border-gray-200 bg-white py-1 shadow-xl"
      style={{ left: pos.left, top: pos.top }}
      onMouseDown={(e) => e.stopPropagation()}
      onContextMenu={(e) => e.preventDefault()}
    >
      {items.map((item, i) => (
        <button
          key={`${item.label}-${i}`}
          className={`flex w-full items-center gap-2 px-3 py-1.5 t-sm text-left transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${
            item.danger
              ? 'text-red-600 hover:bg-red-50'
              : 'text-gray-700 hover:bg-indigo-50 hover:text-indigo-700'
          }`}
          disabled={item.disabled}
          onClick={() => {
            onClose()
            item.onSelect()
          }}
        >
          {item.icon && <item.icon className="h-3.5 w-3.5 shrink-0" />}
          <span className="truncate">{item.label}</span>
        </button>
      ))}
    </div>
  )
}
