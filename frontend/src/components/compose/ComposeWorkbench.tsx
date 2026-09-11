import { Pencil } from 'lucide-react'
import ComposeForm from './ComposeForm'
import { useCompose } from './ComposeContext'

/**
 * 写信工作台主体：由 Layout 在写信标签激活时覆盖在主区上方。
 * 底层页面（收件箱等）保持挂载，这里只负责当前标签的表单与关闭确认。
 * 表单以 tabId 为 key：懒持久化换绑真实草稿 id 时表单不重挂、光标不丢。
 */
export default function ComposeWorkbench() {
  const { tabs, drafts, activeTabId, accounts, openNew, pendingCloseTabId, settleClose } = useCompose()

  const activeTab = tabs.find((t) => t.tabId === activeTabId) ?? null
  const activeDraft = activeTab ? drafts[activeTab.draftId] : undefined

  return (
    <div className="flex h-full flex-col bg-gray-50">
      <div className="min-h-0 flex-1">
        {activeTab && activeDraft ? (
          <ComposeForm key={activeTab.tabId} tabId={activeTab.tabId} draft={activeDraft} accounts={accounts} />
        ) : (
          <div className="flex h-full flex-col items-center justify-center gap-3 t-sm text-gray-400">
            <Pencil className="h-8 w-8 text-gray-200" />
            <span>没有正在撰写的邮件</span>
            <button
              className="rounded-lg bg-indigo-600 px-4 py-1.5 t-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
              onClick={() => openNew()}
              disabled={accounts.length === 0}
            >
              写新邮件
            </button>
          </div>
        )}
      </div>

      {/* 关闭未保存标签的确认 */}
      {pendingCloseTabId != null && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-6">
          <div className="w-full max-w-sm rounded-2xl bg-white p-5 shadow-2xl">
            <h3 className="t-md font-semibold">关闭前保存这封草稿？</h3>
            <p className="mt-1.5 t-sm text-gray-500">
              保留后草稿仍在草稿箱，下次启动会在工作台自动恢复；丢弃则彻底删除。
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <button
                className="rounded-lg border border-gray-300 px-3 py-1.5 t-sm text-gray-700 hover:bg-gray-50"
                onClick={() => void settleClose(pendingCloseTabId, false)}
              >
                保留草稿
              </button>
              <button
                className="rounded-lg border border-red-200 px-3 py-1.5 t-sm text-red-600 hover:bg-red-50"
                onClick={() => void settleClose(pendingCloseTabId, true)}
              >
                丢弃草稿
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
