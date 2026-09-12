import { ChevronRight, type LucideIcon } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

export interface ContextMenuItem {
  label: string
  icon?: LucideIcon
  danger?: boolean
  disabled?: boolean
  /** 有 children（二级菜单）时可省略——点击父项只展开不触发动作 */
  onSelect?: () => void
  /** 二级菜单（悬停展开；§4.3「移动到…」列文件夹）。有 children 时忽略 onSelect。 */
  children?: ContextMenuItem[]
}

const itemCls = (item: ContextMenuItem) =>
  `flex w-full items-center gap-2 px-3 py-1.5 t-sm text-left transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${
    item.danger ? 'text-red-600 hover:bg-red-50' : 'text-gray-700 hover:bg-indigo-50 hover:text-indigo-700'
  }`

/** 菜单条目列表（含二级子菜单：悬停右侧展开，内滚限高）。 */
function MenuItems({ items, onClose }: { items: ContextMenuItem[]; onClose: () => void }) {
  const [openIdx, setOpenIdx] = useState<number | null>(null)
  return (
    <>
      {items.map((item, i) =>
        item.children ? (
          <div
            key={`${item.label}-${i}`}
            className="relative"
            onMouseEnter={() => setOpenIdx(i)}
            onMouseLeave={() => setOpenIdx(null)}
          >
            <button
              className={itemCls(item)}
              disabled={item.disabled || item.children.length === 0}
              onClick={() => setOpenIdx(i)}
            >
              {item.icon && <item.icon className="h-3.5 w-3.5 shrink-0" />}
              <span className="truncate">{item.label}</span>
              <ChevronRight className="ml-auto h-3 w-3 shrink-0 text-gray-400" />
            </button>
            {openIdx === i && item.children.length > 0 && (
              <div
                className="absolute left-full top-0 z-50 max-h-64 min-w-40 overflow-y-auto rounded-lg border border-gray-200 bg-white py-1 shadow-xl"
                onMouseDown={(e) => e.stopPropagation()}
              >
                {item.children.map((child, j) => (
                  <button
                    key={`${child.label}-${j}`}
                    className={itemCls(child)}
                    disabled={child.disabled}
                    onClick={() => {
                      onClose()
                      child.onSelect?.()
                    }}
                  >
                    {child.icon && <child.icon className="h-3.5 w-3.5 shrink-0" />}
                    <span className="truncate">{child.label}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        ) : (
          <button
            key={`${item.label}-${i}`}
            className={itemCls(item)}
            disabled={item.disabled}
            onClick={() => {
              onClose()
              item.onSelect?.()
            }}
          >
            {item.icon && <item.icon className="h-3.5 w-3.5 shrink-0" />}
            <span className="truncate">{item.label}</span>
          </button>
        ),
      )}
    </>
  )
}

/** 右键菜单（VSCode 式）：固定定位 + 视口内夹紧，点击他处/Esc/滚动关闭；条目可带二级菜单。 */
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
      <MenuItems items={items} onClose={onClose} />
    </div>
  )
}
