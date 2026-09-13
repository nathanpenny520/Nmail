import { useCallback, useRef, useState } from 'react'

/** 读取全局界面 zoom（index.css 三档 --app-zoom）：鼠标 clientX 是视觉 px，布局 px 需除以它。 */
export function appZoom(): number {
  return Number(getComputedStyle(document.documentElement).getPropertyValue('--app-zoom')) || 1
}

/**
 * 面板宽度记忆（浏览器/VSCode 式分栏，v0.4.x）：localStorage 持久化 + clamp。
 * 拖拽 mouseup 时经 persist() 落盘 widthRef 最新值——拖拽中不反复写 localStorage。
 */
export function usePanelWidth(key: string, opts: { min: number; max: number; fallback: number }) {
  const { min, max, fallback } = opts
  const clamp = useCallback((v: number) => Math.min(max, Math.max(min, v)), [min, max])
  const [width, setWidthState] = useState(() => {
    const saved = Number(localStorage.getItem(key))
    return Number.isFinite(saved) && saved > 0 ? clamp(saved) : fallback
  })
  const widthRef = useRef(width)
  widthRef.current = width
  const setWidth = useCallback((v: number) => {
    const c = clamp(v)
    // 同步写 ref：mousemove 紧跟 mouseup 时（React 18 连续事件渲染可能推迟提交），
    // onDragEnd 的 persist 才不会落盘最后一步之前的旧值
    widthRef.current = c
    setWidthState(c)
  }, [clamp])
  const persist = useCallback(() => localStorage.setItem(key, String(widthRef.current)), [key])
  const reset = useCallback(() => {
    localStorage.removeItem(key)
    setWidthState(fallback)
  }, [key, fallback])
  return { width, widthRef, setWidth, persist, reset }
}
