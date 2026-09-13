/**
 * 账号标识色工具：12 色板（与 backend COLOR_PALETTE 色值集合同步，后端另按创建顺序轮转取初值）
 * + Tailwind 浅底深字映射（首字母头像用）。限定调色板是因为任意色无法保证浅色 UI 下的
 * 对比度与协调性——浅底 100 / 深字 700（激活档 200/800）全部过 WCAG AA。
 */

/** 展示顺序按色相排列（设置页取色器用）；与后端轮转顺序无关。 */
export const ACCOUNT_COLOR_PALETTE = [
  '#ef4444', '#f97316', '#f59e0b', '#84cc16',
  '#10b981', '#14b8a6', '#0ea5e9', '#3b82f6',
  '#6366f1', '#8b5cf6', '#d946ef', '#ec4899',
] as const

const COLOR_CLS: Record<string, { avatar: string; avatarActive: string }> = {
  '#ef4444': { avatar: 'bg-red-100 text-red-700', avatarActive: 'bg-red-200 text-red-800' },
  '#f97316': { avatar: 'bg-orange-100 text-orange-700', avatarActive: 'bg-orange-200 text-orange-800' },
  '#f59e0b': { avatar: 'bg-amber-100 text-amber-700', avatarActive: 'bg-amber-200 text-amber-800' },
  '#84cc16': { avatar: 'bg-lime-100 text-lime-700', avatarActive: 'bg-lime-200 text-lime-800' },
  '#10b981': { avatar: 'bg-emerald-100 text-emerald-700', avatarActive: 'bg-emerald-200 text-emerald-800' },
  '#14b8a6': { avatar: 'bg-teal-100 text-teal-700', avatarActive: 'bg-teal-200 text-teal-800' },
  '#0ea5e9': { avatar: 'bg-sky-100 text-sky-700', avatarActive: 'bg-sky-200 text-sky-800' },
  '#3b82f6': { avatar: 'bg-blue-100 text-blue-700', avatarActive: 'bg-blue-200 text-blue-800' },
  '#6366f1': { avatar: 'bg-indigo-100 text-indigo-700', avatarActive: 'bg-indigo-200 text-indigo-800' },
  '#8b5cf6': { avatar: 'bg-violet-100 text-violet-700', avatarActive: 'bg-violet-200 text-violet-800' },
  '#d946ef': { avatar: 'bg-fuchsia-100 text-fuchsia-700', avatarActive: 'bg-fuchsia-200 text-fuchsia-800' },
  '#ec4899': { avatar: 'bg-pink-100 text-pink-700', avatarActive: 'bg-pink-200 text-pink-800' },
}

/** 调色板外取值（历史数据兜底）回退灰，与旧版折叠头像观感一致。 */
const FALLBACK_CLS = { avatar: 'bg-gray-100 text-gray-600', avatarActive: 'bg-gray-200 text-gray-700' }

export function accountColorCls(color: string): { avatar: string; avatarActive: string } {
  return COLOR_CLS[color] ?? FALLBACK_CLS
}
