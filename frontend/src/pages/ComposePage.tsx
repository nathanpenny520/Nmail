import { useQuery } from '@tanstack/react-query'
import { Pencil, Plus, X } from 'lucide-react'
import { useEffect } from 'react'
import { api } from '../api/client'
import ComposeForm from '../components/compose/ComposeForm'
import { useCompose } from '../components/compose/ComposeContext'

/**
 * 写信工作台：顶部多标签（对齐网页邮箱习惯），下方当前标签的编辑表单。
 * 标签状态在 ComposeProvider（App 级）持有，进出本页面不丢。
 */
export default function ComposePage() {
  const { tabs, activeId, drafts, setActive, requestClose, settleClose, pendingCloseId, openNew } = useCompose()
  const accountsQuery = useQuery({ queryKey: ['accounts'], queryFn: api.getAccounts })
  const accounts = accountsQuery.data?.accounts ?? []

  const activeTab = tabs.find((t) => t.draftId === activeId) ?? null
  const activeDraft = activeTab ? drafts[activeTab.draftId] : undefined

  // 从恢复的标签进来时自动激活第一个
  useEffect(() => {
    if (activeId == null && tabs.length > 0) setActive(tabs[0].draftId)
  }, [activeId, tabs, setActive])

  return (
    <div className="flex h-full flex-col bg-gray-50">
      {/* 标签条 */}
      <div className="flex shrink-0 items-center gap-1 overflow-x-auto border-b border-gray-200 bg-white px-2 pt-1.5">
        {tabs.map((tab) => (
          <div
            key={tab.draftId}
            onClick={() => setActive(tab.draftId)}
            className={`group flex max-w-56 shrink-0 cursor-pointer items-center gap-1.5 rounded-t-lg border border-b-0 px-3 py-1.5 t-sm transition-colors ${
              tab.draftId === activeId
                ? 'border-gray-200 bg-gray-50 font-medium text-indigo-700'
                : 'border-transparent text-gray-600 hover:bg-gray-50'
            }`}
            title={tab.title}
          >
            {tab.dirty && <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-amber-400" title="有未保存改动" />}
            <span className="truncate">{tab.title}</span>
            <button
              className="shrink-0 text-gray-400 opacity-0 transition-opacity hover:text-gray-700 group-hover:opacity-100"
              onClick={(e) => {
                e.stopPropagation()
                requestClose(tab.draftId)
              }}
              title="关闭标签"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        ))}
        <button
          className="flex shrink-0 items-center rounded-md px-1.5 py-1 t-sm text-gray-500 transition-colors hover:bg-gray-100 hover:text-indigo-600"
          onClick={() => void openNew()}
          title="再写一封"
        >
          <Plus className="h-4 w-4" />
        </button>
      </div>

      {/* 当前标签内容 */}
      <div className="min-h-0 flex-1">
        {activeTab && activeDraft ? (
          <ComposeForm key={activeTab.draftId} draft={activeDraft} accounts={accounts} />
        ) : (
          <div className="flex h-full flex-col items-center justify-center gap-3 t-sm text-gray-400">
            <Pencil className="h-8 w-8 text-gray-200" />
            <span>没有正在撰写的邮件</span>
            <button
              className="rounded-lg bg-indigo-600 px-4 py-1.5 t-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
              onClick={() => void openNew()}
              disabled={accounts.length === 0}
            >
              写新邮件
            </button>
          </div>
        )}
      </div>

      {/* 关闭未保存标签的确认 */}
      {pendingCloseId != null && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-6">
          <div className="w-full max-w-sm rounded-2xl bg-white p-5 shadow-2xl">
            <h3 className="t-md font-semibold">关闭前保存这封草稿？</h3>
            <p className="mt-1.5 t-sm text-gray-500">
              保留后草稿仍在，下次启动会在工作台自动恢复；丢弃则彻底删除。
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <button
                className="rounded-lg border border-gray-300 px-3 py-1.5 t-sm text-gray-700 hover:bg-gray-50"
                onClick={() => void settleClose(pendingCloseId, false)}
              >
                保留草稿
              </button>
              <button
                className="rounded-lg border border-red-200 px-3 py-1.5 t-sm text-red-600 hover:bg-red-50"
                onClick={() => void settleClose(pendingCloseId, true)}
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
