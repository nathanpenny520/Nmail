import { useQuery } from '@tanstack/react-query'
import { api } from './client'

/**
 * AI 总开关（全局共享 ['ai-profiles'] 缓存，与设置页同源）。
 * 停用时前端隐藏全部 AI 入口，回归传统邮件；加载中默认视为启用，避免按钮闪烁。
 */
export function useAIEnabled(): boolean {
  const { data } = useQuery({
    queryKey: ['ai-profiles'],
    queryFn: api.getAIProfiles,
    staleTime: 60_000,
  })
  return data?.ai_enabled ?? true
}
