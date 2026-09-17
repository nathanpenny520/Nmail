import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { FileBox, Loader2, PenLine, Plus, Trash2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import type { Editor } from '@tiptap/react'
import { api } from '../../api/client'
import type { Account, ComposeTemplate } from '../../types'
import { Dropdown, Modal, menuItemCls } from './ui'

export const EXTRAS_KEY = ['compose-extras'] as const

/** 在编辑器末尾追加转换后的 HTML（签名习惯放落款处）。 */
async function insertHtml(editor: Editor, markdown: string, atEnd: boolean): Promise<void> {
  const { html } = await api.markdownToHtml(markdown)
  if (atEnd) editor.chain().focus().insertContentAt(editor.state.doc.content.size, html).run()
  else editor.chain().focus().insertContent(html).run()
}

/** 工具栏「插入模板」：选择即插入光标处；底部入口进管理弹窗。 */
export function TemplateMenu({ editor, onManage }: { editor: Editor | null; onManage: () => void }) {
  const { data } = useQuery({ queryKey: EXTRAS_KEY, queryFn: api.getComposeExtras })
  const templates = data?.templates ?? []
  return (
    <Dropdown
      align="right"
      label={
        <>
          <FileBox className="h-3.5 w-3.5" />
          插入模板
        </>
      }
      title="插入常用文案模板"
    >
      {templates.length === 0 && <div className="px-3 py-1.5 t-xs text-gray-400">还没有模板</div>}
      {templates.map((t) => (
        <button
          key={t.id}
          className={menuItemCls('max-w-64')}
          title={t.content.slice(0, 120)}
          onClick={() => {
            if (editor) void insertHtml(editor, t.content, false)
          }}
        >
          {t.name}
        </button>
      ))}
      <div className="my-1 border-t border-gray-100" />
      <button className={menuItemCls()} onClick={onManage}>
        管理模板…
      </button>
    </Dropdown>
  )
}

/** 工具栏「签名」：按账号插入落款；底部入口进编辑弹窗。 */
export function SignatureMenu({
  editor, accounts, accountId, onManage,
}: {
  editor: Editor | null
  accounts: Account[]
  accountId: number
  onManage: () => void
}) {
  const { data } = useQuery({ queryKey: EXTRAS_KEY, queryFn: api.getComposeExtras })
  const sigMap = new Map((data?.signatures ?? []).map((s) => [s.account_id, s.content]))
  return (
    <Dropdown
      align="right"
      label={
        <>
          <PenLine className="h-3.5 w-3.5" />
          签名
        </>
      }
      title="插入邮件签名"
    >
      {accounts.map((a) => (
        <button
          key={a.id}
          className={menuItemCls('max-w-64')}
          title={sigMap.get(a.id)?.slice(0, 120) ?? '该账号还没有签名'}
          onClick={() => {
            const content = sigMap.get(a.id)
            if (editor && content?.trim()) void insertHtml(editor, content, true)
          }}
        >
          {a.email}
          {!sigMap.get(a.id)?.trim() && <span className="ml-1 t-xs text-gray-400">（未设置）</span>}
        </button>
      ))}
      <div className="my-1 border-t border-gray-100" />
      <button className={menuItemCls()} onClick={onManage}>
        编辑签名…
      </button>
      {accountId > 0 && sigMap.get(accountId)?.trim() && (
        <button
          className={menuItemCls()}
          onClick={() => {
            if (editor) void insertHtml(editor, sigMap.get(accountId)!, true)
          }}
        >
          插入当前账号签名
        </button>
      )}
    </Dropdown>
  )
}

/** 模板管理：新建/编辑（Markdown 文本）/删除，整表保存。 */
export function TemplateManager({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient()
  const { data } = useQuery({ queryKey: EXTRAS_KEY, queryFn: api.getComposeExtras })
  const [items, setItems] = useState<ComposeTemplate[] | null>(null)
  const [editing, setEditing] = useState<ComposeTemplate | null>(null)
  const [error, setError] = useState('')
  const templates = items ?? data?.templates ?? []
  const signatures = data?.signatures ?? []

  const saveMutation = useMutation({
    mutationFn: (next: ComposeTemplate[]) =>
      api.updateComposeExtras({ templates: next, signatures }),
    onSuccess: (resp) => {
      queryClient.setQueryData(EXTRAS_KEY, resp)
      setItems(null)
      setEditing(null)
    },
    onError: (err: Error) => setError(err.message),
  })

  const saveEditing = () => {
    if (!editing || !editing.name.trim()) {
      setError('模板名称不能为空')
      return
    }
    const exists = templates.some((t) => t.id === editing.id)
    const next = exists
      ? templates.map((t) => (t.id === editing.id ? editing : t))
      : [...templates, editing]
    saveMutation.mutate(next)
  }

  return (
    <Modal title="管理模板" onClose={onClose} width="max-w-xl">
      {editing ? (
        <div className="space-y-2.5">
          <input
            className="w-full rounded-lg border border-gray-300 px-3 py-2 t-sm outline-none focus:border-indigo-500"
            placeholder="模板名称"
            value={editing.name}
            onChange={(e) => setEditing({ ...editing, name: e.target.value })}
            autoFocus
          />
          <textarea
            className="h-48 w-full resize-y rounded-lg border border-gray-300 px-3 py-2 t-sm leading-relaxed outline-none focus:border-indigo-500"
            placeholder={'模板内容，支持 Markdown（加粗 **x**、列表 -、链接等）。单个换行=分段；行尾打两个空格再换行=紧贴一行（同 Shift+Enter）'}
            value={editing.content}
            onChange={(e) => setEditing({ ...editing, content: e.target.value })}
          />
          {error && <div className="t-sm text-red-500">{error}</div>}
          <div className="flex justify-end gap-2">
            <button
              className="rounded-lg border border-gray-300 px-3 py-1.5 t-sm text-gray-700 hover:bg-gray-50"
              onClick={() => {
                setEditing(null)
                setError('')
              }}
            >
              取消
            </button>
            <button
              className="rounded-lg bg-indigo-600 px-4 py-1.5 t-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
              onClick={saveEditing}
              disabled={saveMutation.isPending}
            >
              保存
            </button>
          </div>
        </div>
      ) : (
        <div className="space-y-1">
          <button
            className="mb-2 inline-flex items-center gap-1 rounded-lg bg-indigo-600 px-3 py-1.5 t-sm font-medium text-white hover:bg-indigo-700"
            onClick={() =>
              setEditing({ id: `tpl-${Date.now()}`, name: '', content: '' })
            }
          >
            <Plus className="h-3.5 w-3.5" />
            新建模板
          </button>
          {templates.length === 0 && <div className="py-6 text-center t-sm text-gray-400">还没有模板，点上方新建</div>}
          {templates.map((t) => (
            <div key={t.id} className="flex items-center gap-2 rounded-lg border border-gray-100 px-3 py-2">
              <div className="min-w-0 flex-1">
                <div className="truncate t-sm font-medium text-gray-800">{t.name}</div>
                <div className="truncate t-xs text-gray-400">{t.content.slice(0, 80) || '（空）'}</div>
              </div>
              <button
                className="shrink-0 rounded-md px-2 py-1 t-sm text-indigo-600 hover:bg-indigo-50"
                onClick={() => setEditing(t)}
              >
                编辑
              </button>
              <button
                className="shrink-0 rounded-md px-2 py-1 t-sm text-red-500 hover:bg-red-50"
                title="删除模板"
                onClick={() => saveMutation.mutate(templates.filter((x) => x.id !== t.id))}
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
          ))}
          {error && <div className="t-sm text-red-500">{error}</div>}
        </div>
      )}
    </Modal>
  )
}

/** 签名编辑：按账号各存一段 Markdown，插入时转富文本。 */
export function SignatureEditor({ accounts, onClose }: { accounts: Account[]; onClose: () => void }) {
  const queryClient = useQueryClient()
  const { data } = useQuery({ queryKey: EXTRAS_KEY, queryFn: api.getComposeExtras })
  const [accountId, setAccountId] = useState(accounts[0]?.id ?? 0)
  const [content, setContent] = useState('')
  const [error, setError] = useState('')
  const [loadedFor, setLoadedFor] = useState<number | null>(null)

  // 切换账号时带入该账号已存的签名
  useEffect(() => {
    if (loadedFor === accountId) return
    const sig = (data?.signatures ?? []).find((s) => s.account_id === accountId)
    setContent(sig?.content ?? '')
    setLoadedFor(accountId)
  }, [accountId, data, loadedFor])

  const saveMutation = useMutation({
    mutationFn: () => {
      const others = (data?.signatures ?? []).filter((s) => s.account_id !== accountId)
      const next = content.trim()
        ? [...others, { account_id: accountId, content }]
        : others
      return api.updateComposeExtras({ templates: data?.templates ?? [], signatures: next })
    },
    onSuccess: (resp) => {
      queryClient.setQueryData(EXTRAS_KEY, resp)
      onClose()
    },
    onError: (err: Error) => setError(err.message),
  })

  return (
    <Modal title="编辑签名" onClose={onClose}>
      <div className="space-y-2.5">
        <select
          className="w-full rounded-lg border border-gray-300 px-3 py-2 t-sm outline-none focus:border-indigo-500"
          value={accountId}
          onChange={(e) => setAccountId(Number(e.target.value))}
        >
          {accounts.map((a) => (
            <option key={a.id} value={a.id}>
              {a.email}
            </option>
          ))}
        </select>
        <textarea
          className="h-40 w-full resize-y rounded-lg border border-gray-300 px-3 py-2 t-sm leading-relaxed outline-none focus:border-indigo-500"
          placeholder={'签名内容（插入在邮件末尾），支持 Markdown，例如：\n\n**张三**  \n产品部 · 某某科技  \n电话 138-0000-0000'}
          value={content}
          onChange={(e) => setContent(e.target.value)}
        />
        {error && <div className="t-sm text-red-500">{error}</div>}
        <div className="flex justify-end gap-2">
          <button
            className="rounded-lg border border-gray-300 px-3 py-1.5 t-sm text-gray-700 hover:bg-gray-50"
            onClick={onClose}
          >
            取消
          </button>
          <button
            className="inline-flex items-center gap-1 rounded-lg bg-indigo-600 px-4 py-1.5 t-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
            onClick={() => saveMutation.mutate()}
            disabled={saveMutation.isPending || accounts.length === 0}
          >
            {saveMutation.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            保存
          </button>
        </div>
      </div>
    </Modal>
  )
}
