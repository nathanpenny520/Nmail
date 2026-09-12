import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import FolderTree, { type TreeSelection } from '../components/FolderTree'
import MailBrowser from '../components/MailBrowser'
import DraftsPage from './DraftsPage'
import UserDraftsPage from './UserDraftsPage'

function selectionFromParams(view: string | null): TreeSelection {
  switch (view) {
    case 'review':
      return { type: 'review' }
    case 'mydrafts':
      return { type: 'mydrafts' }
    case 'archived':
      return { type: 'archived' }
    default:
      return { type: 'inbox', accountId: null }
  }
}

/**
 * 邮件基座页（v0.4，REDESIGN_PLAN §3/§4）：左侧文件夹树 + 内容区。
 * P1 树为只读骨架（智能视图 + 账号 INBOX）；草稿合并（P3）与服务器文件夹（P2）陆续并入。
 * 视图初值取 URL（承接旧路由重定向的深链），之后由树驱动；key 换绑即重挂列表，天然重置分页/选中。
 */
export default function MailPage() {
  const [searchParams] = useSearchParams()
  const [sel, setSel] = useState<TreeSelection>(() => selectionFromParams(searchParams.get('view')))

  return (
    <div className="flex h-full min-w-0">
      <FolderTree selection={sel} onSelect={setSel} />
      <div className="min-w-0 flex-1">
        {sel.type === 'inbox' && (
          <MailBrowser key={`inbox-${sel.accountId ?? 'all'}`} archived={false} initialAccountId={sel.accountId} />
        )}
        {sel.type === 'archived' && <MailBrowser key="archived" archived />}
        {sel.type === 'review' && <DraftsPage />}
        {sel.type === 'mydrafts' && <UserDraftsPage />}
      </div>
    </div>
  )
}
