import { X } from 'lucide-react'
import { useEffect, useRef, useState, type ReactNode } from 'react'

/** 工具栏下拉菜单：点击外部收起，项点击自动收起（panel 内自带 onClick 冒泡关闭）。 */
export function Dropdown({
  label, title, disabled, children,
}: {
  label: ReactNode
  title: string
  disabled?: boolean
  children: ReactNode
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [open])

  return (
    <div ref={ref} className="relative shrink-0">
      <button
        type="button"
        title={title}
        disabled={disabled}
        onMouseDown={(e) => e.preventDefault()}
        onClick={() => setOpen((v) => !v)}
        className="flex h-7 shrink-0 items-center gap-1 whitespace-nowrap rounded-md px-1.5 t-sm text-gray-600 transition-colors hover:bg-gray-100 disabled:opacity-30"
      >
        {label}
      </button>
      {open && (
        <div
          className="absolute left-0 top-full z-40 mt-1 max-w-72 min-w-44 rounded-lg border border-gray-200 bg-white py-1 shadow-lg"
          onClick={() => setOpen(false)}
        >
          {children}
        </div>
      )}
    </div>
  )
}

export function menuItemCls(extra = ''): string {
  return `block w-full truncate px-3 py-1.5 text-left t-sm text-gray-700 transition-colors hover:bg-gray-50 ${extra}`
}

/** 居中弹窗：点击遮罩关闭。 */
export function Modal({
  title, onClose, children, width = 'max-w-lg',
}: {
  title: string
  onClose: () => void
  children: ReactNode
  width?: string
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-6" onMouseDown={onClose}>
      <div
        className={`flex max-h-full w-full ${width} flex-col overflow-hidden rounded-2xl bg-white shadow-2xl`}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="flex shrink-0 items-center justify-between border-b border-gray-100 px-5 py-3">
          <h2 className="t-md font-semibold">{title}</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-700">
            <X className="h-5 w-5" />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-5">{children}</div>
      </div>
    </div>
  )
}

/** datetime-local 输入框值格式（本地时间） */
export function toLocalInput(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}
