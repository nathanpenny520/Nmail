import { useQuery } from '@tanstack/react-query'
import { api } from './client'

/**
 * 键盘快捷键总开关（全局共享 ['settings'] 缓存，与设置页同源）。
 * 加载中默认视为开启，避免按键失效闪烁；设置页切换即时写库并经 guardVersion 回填缓存。
 */
export function useShortcutsEnabled(): boolean {
  const { data } = useQuery({ queryKey: ['settings'], queryFn: api.getSettings, staleTime: 60_000 })
  return data?.shortcuts_enabled ?? true
}
