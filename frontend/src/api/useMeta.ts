import { useQuery } from '@tanstack/react-query'
import { api } from './client'
import { CATEGORY_FALLBACK, type CategoryMeta } from '../types'

/** 分类元数据（GET /api/meta，拉取一次长期缓存；未就绪时回退内置清单）。
 *  真源在 backend/app/ai/categories.py——加分类不需要改前端。 */
export function useCategories(): CategoryMeta[] {
  const { data } = useQuery({
    queryKey: ['meta-categories'],
    queryFn: async () => (await api.getMeta()).categories,
    staleTime: Infinity,
  })
  return data && data.length > 0 ? data : CATEGORY_FALLBACK
}

/** key → {label, cls} 徽章映射（列表筛选与行内徽章用）。 */
export function categoryBadgeMap(
  cats: CategoryMeta[],
): Record<string, { label: string; cls: string }> {
  return Object.fromEntries(cats.map((c) => [c.key, { label: c.label, cls: c.badge_cls }]))
}

/** key → 图表色（每日摘要柱状图用）。 */
export function categoryColorMap(cats: CategoryMeta[]): Record<string, string> {
  return Object.fromEntries(cats.map((c) => [c.key, c.color]))
}
