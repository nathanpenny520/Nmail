/** 一键重启更新（UPDATE_AND_DESKTOP.md §3.4）：POST restart 后轮询 /api/health，
 * 待新版本应答即刷新页面。旧进程退出前 health 仍应答：至少等 1.5s，且版本已变
 * （或 15s 兜底）才刷新；45s 超时放弃回调 onTimeout。 */
const DISMISS_KEY = 'nmail_update_banner_dismissed'

export function restartForUpdateThenReload(oldVersion: string, onTimeout?: () => void): void {
  const started = Date.now()
  const timer = setInterval(() => {
    fetch('/api/health')
      .then((r) => r.json())
      .then((h) => {
        if (h?.status === 'ok' && Date.now() - started > 1500
          && (h.version !== oldVersion || Date.now() - started > 15000)) {
          clearInterval(timer)
          localStorage.removeItem(DISMISS_KEY)
          window.location.reload()
        }
      })
      .catch(() => {})
    if (Date.now() - started > 45000) {
      clearInterval(timer)
      onTimeout?.()
    }
  }, 600)
}
