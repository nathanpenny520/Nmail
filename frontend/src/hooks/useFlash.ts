import { useEffect, useRef, useState } from 'react'

/** 一次性通知横幅（IMPROVEMENT_PLAN 3.7b）。

 * flash(msg, ms?) 展示消息并在 ms 后自动消失；重复调用会重置计时器，
 * 组件卸载时清理未触发的定时器——替代各页面手写的 setTimeout(setX(null))。
 */
export function useFlash(defaultMs = 4000): [string | null, (msg: string, ms?: number) => void] {
  const [message, setMessage] = useState<string | null>(null)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(
    () => () => {
      if (timerRef.current) clearTimeout(timerRef.current)
    },
    [],
  )

  const flash = (msg: string, ms = defaultMs) => {
    setMessage(msg)
    if (timerRef.current) clearTimeout(timerRef.current)
    timerRef.current = setTimeout(() => {
      setMessage(null)
      timerRef.current = null
    }, ms)
  }

  return [message, flash]
}
