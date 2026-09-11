/** 全局日期/大小格式化（IMPROVEMENT_PLAN 3.7b 归拢：原散布于
 *  MailBrowser/EmailReader/ComposeForm/ManagerPage 四处，行为原样迁入）。 */

/** 列表短日期：当天只显时间，同年省略年份。 */
export function shortDate(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  const now = new Date()
  const sameDay = d.toDateString() === now.toDateString()
  if (sameDay) return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false })
  const sameYear = d.getFullYear() === now.getFullYear()
  return d.toLocaleDateString('zh-CN', {
    month: sameYear ? 'numeric' : undefined,
    day: 'numeric',
    year: sameYear ? undefined : 'numeric',
  })
}

/** 详情页完整本地时间。 */
export function formatDate(iso: string | null): string {
  if (!iso) return ''
  return new Date(iso).toLocaleString('zh-CN', { hour12: false })
}

/** 附件大小：B / K / M。 */
export function fmtSize(n: number): string {
  if (n >= 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)}M`
  if (n >= 1024) return `${Math.ceil(n / 1024)}K`
  return `${n}B`
}

/** 通知/会话相对时间。后端 datetime('now') 为无时区标记的 UTC，补 Z 后按本地展示。 */
export function relativeTime(value: string): string {
  const ts = new Date(value.includes('T') ? value : value.replace(' ', 'T') + 'Z').getTime()
  if (Number.isNaN(ts)) return value
  const min = Math.floor((Date.now() - ts) / 60000)
  if (min < 1) return '刚刚'
  if (min < 60) return `${min} 分钟前`
  const hour = Math.floor(min / 60)
  if (hour < 24) return `${hour} 小时前`
  const day = Math.floor(hour / 24)
  if (day < 7) return `${day} 天前`
  return value.slice(0, 10)
}
