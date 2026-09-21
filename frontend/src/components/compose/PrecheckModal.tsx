import { AlertTriangle, ShieldAlert } from 'lucide-react'
import type { PrecheckIssue } from '../../types'
import { Modal } from './ui'

const btnFix =
  'rounded-lg border border-gray-300 px-3 py-1.5 t-sm text-gray-700 transition-colors hover:bg-gray-100'
const btnForce =
  'rounded-lg bg-indigo-600 px-4 py-1.5 t-sm font-medium text-white transition-colors hover:bg-indigo-700 disabled:opacity-50'

/** 发送前检查问题卡（S-0921）：blocker/建议分组展示，人工可强制越过。 */
export default function PrecheckModal({
  issues, aiUsed, aiError, busy, onForce, onClose,
}: {
  issues: PrecheckIssue[]
  aiUsed?: boolean
  aiError?: string | null
  busy?: boolean
  onForce: () => void
  onClose: () => void
}) {
  const blockers = issues.filter((i) => i.severity === 'blocker')
  const warns = issues.filter((i) => i.severity !== 'blocker')
  return (
    <Modal title="发送前检查发现这些问题" onClose={onClose} width="max-w-md">
      <div className="space-y-3">
        {blockers.length > 0 && (
          <ul className="space-y-1.5">
            {blockers.map((i, idx) => (
              <li
                key={idx}
                className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 t-sm leading-relaxed text-red-700"
              >
                <ShieldAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                {i.message}
              </li>
            ))}
          </ul>
        )}
        {warns.length > 0 && (
          <ul className="space-y-1.5">
            {warns.map((i, idx) => (
              <li
                key={idx}
                className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 t-sm leading-relaxed text-amber-700"
              >
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                {i.message}
              </li>
            ))}
          </ul>
        )}
        {aiUsed ? (
          <p className="t-xs text-gray-400">以上含 AI 审查结果；规则检查始终开启。</p>
        ) : aiError ? (
          <p className="t-xs text-gray-400">AI 审查不可用（{aiError}），本次仅规则检查。</p>
        ) : null}
        <p className="t-xs text-gray-400">定时发送没有确认机会：同类问题会让定时草稿退回写信台并通知你。</p>
        <div className="flex justify-end gap-2">
          <button className={btnFix} onClick={onClose}>
            返回修改
          </button>
          <button className={btnForce} onClick={onForce} disabled={busy}>
            仍要发送
          </button>
        </div>
      </div>
    </Modal>
  )
}
