import { X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { api } from '../../api/client'

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

/**
 * 收件人 chips 输入（v0.4 P4，REDESIGN_PLAN §5.2）：
 * 值保持「逗号分隔地址串」（与后端 to_addrs 格式一致，自动保存无感）；
 * 输入触发通讯录联想（use_count×最近加权），↑↓ 选择、Enter 确认、
 * 逗号/失焦提交、退格删除上一枚；非法地址红框提示。
 */
export default function RecipientChipsInput({
  value,
  onChange,
  placeholder,
  autoFocus,
}: {
  value: string
  onChange: (v: string) => void
  placeholder?: string
  autoFocus?: boolean
}) {
  const tokens = value.split(',').map((s) => s.trim()).filter(Boolean)
  const [input, setInput] = useState('')
  const [open, setOpen] = useState(false)
  const [items, setItems] = useState<{ email: string; name: string; use_count: number }[]>([])
  const [active, setActive] = useState(0)
  const boxRef = useRef<HTMLDivElement>(null)

  // 联想防抖
  useEffect(() => {
    if (!open) return
    const q = input.trim()
    const t = setTimeout(() => {
      api.suggestContacts(q).then((d) => {
        setItems(d.items.filter((s) => !tokens.includes(s.email)))
        setActive(0)
      }).catch(() => setItems([]))
    }, 150)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [input, open])

  const commit = (raw: string) => {
    const v = raw.trim().replace(/,+$/, '').trim()
    if (!v) return
    if (!tokens.includes(v)) onChange([...tokens, v].join(', '))
    setInput('')
    setItems([])
  }

  const removeAt = (i: number) => onChange(tokens.filter((_, idx) => idx !== i).join(', '))

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      if (open && items[active]) commit(items[active].email)
      else commit(input)
    } else if (e.key === ',' || e.key === 'Tab') {
      if (input.trim()) {
        e.preventDefault()
        commit(input)
      }
    } else if (e.key === 'Backspace' && !input && tokens.length) {
      e.preventDefault()
      removeAt(tokens.length - 1)
    } else if (e.key === 'ArrowDown' && items.length) {
      e.preventDefault()
      setActive((i) => (i + 1) % items.length)
    } else if (e.key === 'ArrowUp' && items.length) {
      e.preventDefault()
      setActive((i) => (i - 1 + items.length) % items.length)
    } else if (e.key === 'Escape') {
      setOpen(false)
    }
  }

  return (
    <div ref={boxRef} className="relative min-w-0 flex-1">
      <div
        className={`flex min-h-7 w-full flex-wrap items-center gap-1 rounded-lg border px-1.5 py-0.5 t-sm outline-none transition-colors focus-within:border-indigo-500 focus-within:ring-2 focus-within:ring-indigo-100 ${'border-transparent'}`}
        onMouseDown={(e) => {
          if ((e.target as HTMLElement).dataset.chipArea) {
            e.preventDefault()
            ;(boxRef.current?.querySelector('input') as HTMLInputElement | null)?.focus()
          }
        }}
        data-chip-area="1"
      >
        {tokens.map((tk, i) => {
          const bad = !EMAIL_RE.test(tk) && !/<[^<>]+>/.test(tk)
          return (
            <span
              key={`${tk}-${i}`}
              className={`inline-flex max-w-64 shrink-0 items-center gap-0.5 rounded-md px-1.5 py-0.5 t-sm ${
                bad ? 'bg-red-50 text-red-600' : 'bg-indigo-50 text-indigo-700'
              }`}
              title={bad ? '地址格式有误' : tk}
            >
              <span className="truncate">{tk}</span>
              <button
                className="shrink-0 rounded p-px hover:bg-white/70"
                onClick={(e) => {
                  e.stopPropagation()
                  removeAt(i)
                }}
                title="移除"
              >
                <X className="h-3 w-3" />
              </button>
            </span>
          )
        })}
        <input
          className="min-w-24 flex-1 bg-transparent py-0.5 t-sm outline-none"
          value={input}
          placeholder={tokens.length === 0 ? placeholder : ''}
          autoFocus={autoFocus}
          onChange={(e) => {
            const v = e.target.value
            if (v.includes(',')) {
              v.split(',').forEach((p) => commit(p))
            } else {
              setInput(v)
              setOpen(true)
            }
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => {
            // 失焦把输入中的合法地址收进 chips
            if (input.trim() && EMAIL_RE.test(input.trim())) commit(input)
            setTimeout(() => setOpen(false), 150)
          }}
          onKeyDown={onKeyDown}
        />
      </div>
      {open && items.length > 0 && (
        <div className="absolute left-0 top-full z-30 mt-1 w-80 overflow-hidden rounded-xl border border-gray-200 bg-white shadow-xl">
          {items.map((s, i) => (
            <button
              key={s.email}
              className={`flex w-full items-center gap-2 px-3 py-1.5 t-sm text-left ${
                i === active ? 'bg-indigo-50 text-indigo-700' : 'text-gray-700 hover:bg-gray-50'
              }`}
              onMouseEnter={() => setActive(i)}
              onMouseDown={(e) => {
                e.preventDefault() // 防止 input 失焦先收面板
                commit(s.email)
                setOpen(false)
              }}
            >
              <span className="min-w-0 flex-1 truncate">
                {s.name && <b className="font-medium">{s.name} </b>}
                <span className="text-gray-500">&lt;{s.email}&gt;</span>
              </span>
              <span className="shrink-0 t-xs text-gray-300">{s.use_count} 次</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
