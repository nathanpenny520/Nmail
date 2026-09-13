import { useMutation } from '@tanstack/react-query'
import {
  AlarmClock, Eye, Loader2, Paperclip, Send, Sparkles, X,
} from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../../api/client'
import { useAIEnabled } from '../../api/useAI'
import { fmtSize } from '../../utils/format'
import type { Account, DraftAttachment, UserDraft } from '../../types'
import { useCompose } from './ComposeContext'
import RecipientChipsInput from './RecipientChipsInput'
import AiWriteDialog from './AiWriteDialog'
import { SignatureMenu, TemplateMenu, TemplateManager, SignatureEditor } from './InsertDialogs'
import { EditorSurface, EditorToolbar, useMailEditor } from './RichEditor'
import { Modal, toLocalInput } from './ui'

const fieldInput =
  'min-w-0 flex-1 rounded-md border border-transparent bg-transparent px-2 py-1.5 t-md outline-none transition-colors placeholder:text-gray-300 hover:border-gray-200 focus:border-indigo-400 focus:bg-white'

function fmtSendAt(iso: string): string {
  return new Date(iso).toLocaleString('zh-CN', {
    month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false,
  })
}

/**
 * 单个写信标签的编辑表单。内容变化 1s 防抖自动保存到 user_drafts；
 * 「写信」开出的空白标签未落库（ephemeral），首次编辑/显式保存才创建记录；
 * 附件选择即上传落盘（刷新/重启后随草稿恢复）；支持定时发送；
 * AI 写作对话框生成富文本直插正文。
 */
export default function ComposeForm({
  tabId, draft, accounts,
}: {
  tabId: string
  draft: UserDraft
  accounts: Account[]
}) {
  const { updateTab, requestClose, finishSent, cacheDraft, patchDraft, registerFlush, onEphemeralPersisted } =
    useCompose()
  const aiEnabled = useAIEnabled()

  const [accountId, setAccountId] = useState(draft.account_id)
  const [to, setTo] = useState(draft.to_addrs)
  const [cc, setCc] = useState(draft.cc_addrs)
  const [bcc, setBcc] = useState(draft.bcc_addrs)
  const [subject, setSubject] = useState(draft.subject)
  const [showCc, setShowCc] = useState(!!draft.cc_addrs.trim() || !!draft.bcc_addrs.trim())
  const [showBcc, setShowBcc] = useState(!!draft.bcc_addrs.trim())
  const [bodyHtml, setBodyHtml] = useState(draft.body_html)
  const [atts, setAtts] = useState<DraftAttachment[]>(draft.attachments ?? [])
  const [attBusy, setAttBusy] = useState(false)
  const [attError, setAttError] = useState('')
  const [aiOpen, setAiOpen] = useState(false)
  const [tplOpen, setTplOpen] = useState(false)
  const [sigOpen, setSigOpen] = useState(false)
  const [schedOpen, setSchedOpen] = useState(false)
  const [previewHtml, setPreviewHtml] = useState<string | null>(null)
  const [schedAt, setSchedAt] = useState(toLocalInput(new Date(Date.now() + 30 * 60 * 1000)))
  const [savedAt, setSavedAt] = useState('')
  const [saveError, setSaveError] = useState(false)

  // ── 草稿 id：ephemeral 标签为负数临时 id，首次保存后换绑真实 id ──
  const persistedIdRef = useRef(draft.id > 0 ? draft.id : 0)
  if (draft.id > 0) persistedIdRef.current = draft.id

  // 标签标题跟随主题/收件人
  useEffect(() => {
    updateTab(tabId, { title: subject.trim() || to.split(',')[0]?.trim() || '新邮件' })
  }, [subject, to, tabId, updateTab])

  // ── 自动保存 ──
  const payloadRef = useRef({ account_id: accountId, to_addrs: to, cc_addrs: cc, bcc_addrs: bcc, subject, body_html: bodyHtml })
  payloadRef.current = { account_id: accountId, to_addrs: to, cc_addrs: cc, bcc_addrs: bcc, subject, body_html: bodyHtml }
  const savedRef = useRef(
    JSON.stringify({
      account_id: draft.account_id,
      to_addrs: draft.to_addrs,
      cc_addrs: draft.cc_addrs,
      bcc_addrs: draft.bcc_addrs,
      subject: draft.subject,
      body_html: draft.body_html,
    }),
  )
  const saveTimer = useRef<number | undefined>(undefined)
  const retryTimer = useRef<number | undefined>(undefined)
  const retriedRef = useRef(false) // 每轮失败只自动重试一次，避免 404 时无限循环
  const deadRef = useRef(false)

  const doSave = useCallback(async () => {
    const p = payloadRef.current
    const serialized = JSON.stringify(p)
    // 未落库的空白标签：即使内容无变化，显式保存（存草稿/定时/发附件）也应创建记录
    if (serialized === savedRef.current && persistedIdRef.current > 0) return
    try {
      if (persistedIdRef.current > 0) {
        await api.updateUserDraft(persistedIdRef.current, p)
        patchDraft(persistedIdRef.current, p) // 缓存同步，空稿判断/标题等不拿过期快照
      } else {
        const { draft: real } = await api.createUserDraft({
          account_id: p.account_id,
          mode: draft.mode,
          in_reply_to: draft.in_reply_to,
          to_addrs: p.to_addrs,
          cc_addrs: p.cc_addrs,
          bcc_addrs: p.bcc_addrs,
          subject: p.subject,
          body_html: p.body_html,
        })
        persistedIdRef.current = real.id
        onEphemeralPersisted(draft.id, real) // tabId 不变换绑真实草稿，表单不重挂
      }
      savedRef.current = serialized
      retriedRef.current = false
      setSaveError(false)
      setSavedAt(new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false }))
      updateTab(tabId, { dirty: false })
    } catch {
      setSaveError(true) // 保持 dirty，后续改动会再次触发保存
      // 失败自动重试一次（如后端瞬时不可用）；草稿已删除等情况由重试再次失败终止
      if (!retriedRef.current && !deadRef.current) {
        retriedRef.current = true
        window.clearTimeout(retryTimer.current)
        retryTimer.current = window.setTimeout(() => void doSaveRef.current(), 5000)
      }
    }
  }, [draft.mode, draft.in_reply_to, draft.id, tabId, updateTab, patchDraft, onEphemeralPersisted])
  const doSaveRef = useRef(doSave)
  doSaveRef.current = doSave

  // 附件/发送/定时等需要真实草稿 id 的操作先确保持久化
  const ensureRef = useRef<Promise<void> | null>(null)
  const ensurePersisted = useCallback((): Promise<number> => {
    if (persistedIdRef.current > 0) return Promise.resolve(persistedIdRef.current)
    if (!ensureRef.current) {
      ensureRef.current = doSaveRef.current().finally(() => {
        ensureRef.current = null
      })
    }
    const inflight = ensureRef.current
    return inflight.then(() => {
      if (persistedIdRef.current > 0) return persistedIdRef.current
      throw new Error('草稿保存失败，请重试')
    })
  }, [])

  // 关闭决策/发送/定时前，Provider 可调用 flush 冲掉防抖窗口里的未保存内容
  useEffect(() => {
    registerFlush(tabId, () => doSaveRef.current())
    return () => registerFlush(tabId, null)
  }, [tabId, registerFlush])

  useEffect(() => {
    const serialized = JSON.stringify(payloadRef.current)
    if (serialized === savedRef.current) return
    updateTab(tabId, { dirty: true })
    window.clearTimeout(saveTimer.current)
    saveTimer.current = window.setTimeout(() => void doSaveRef.current(), 1000)
  }, [accountId, to, cc, bcc, subject, bodyHtml, tabId, updateTab])

  // 卸载兜底：切标签/收起工作台时把防抖窗口内的最后编辑同步上去。
  // 未落库且从未编辑的空白标签静默跳过——多开下每次切标签都会卸载前一个表单，
  // 不能把随手点开的空白页签落成空草稿（显式「保留草稿」路径不走此处，仍会落库）
  useEffect(
    () => () => {
      deadRef.current = true
      window.clearTimeout(saveTimer.current)
      window.clearTimeout(retryTimer.current)
      if (JSON.stringify(payloadRef.current) !== savedRef.current) {
        void doSaveRef.current().catch(() => {})
      }
    },
    [],
  )

  // ── 发送 ──
  const sendMutation = useMutation({
    mutationFn: async () => {
      const id = await ensurePersisted()
      return api.sendUserDraft(id)
    },
    onSuccess: () => finishSent(tabId),
  })
  const sendNowRef = useRef<() => void>(() => {})
  sendNowRef.current = () => {
    if (!sendMutation.isPending) sendMutation.mutate()
  }

  // ── 定时发送 ──
  const scheduleMutation = useMutation({
    mutationFn: async () => {
      const id = await ensurePersisted()
      return api.scheduleDraft(id, schedAt)
    },
    onSuccess: ({ draft: updated }) => {
      cacheDraft(updated)
      setSchedOpen(false)
    },
  })
  const unscheduleMutation = useMutation({
    mutationFn: () => api.unscheduleDraft(persistedIdRef.current),
    onSuccess: ({ draft: updated }) => cacheDraft(updated),
  })

  // ── 附件（选择即上传落盘）──
  const uploadAtts = async (files: File[]) => {
    if (!files.length || attBusy) return
    setAttBusy(true)
    setAttError('')
    try {
      const id = await ensurePersisted()
      const { draft: updated } = await api.uploadDraftAttachments(id, files)
      setAtts(updated.attachments)
      cacheDraft(updated)
    } catch (err) {
      setAttError(`附件上传失败：${(err as Error).message}`)
    } finally {
      setAttBusy(false)
    }
  }
  const removeAtt = async (attId: number) => {
    setAttError('')
    try {
      const { draft: updated } = await api.deleteDraftAttachment(persistedIdRef.current, attId)
      setAtts(updated.attachments)
      cacheDraft(updated)
    } catch (err) {
      setAttError(`附件删除失败：${(err as Error).message}`)
    }
  }

  const editor = useMailEditor(draft.body_html, setBodyHtml, () => sendNowRef.current())
  const isScheduled = draft.status === 'scheduled' && !!draft.send_at
  const submitDisabled = !to.trim() || sendMutation.isPending

  return (
    <div
      className="flex h-full flex-col bg-white"
      onKeyDown={(e) => {
        if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
          e.preventDefault()
          void doSaveRef.current()
        }
      }}
    >
      {/* 已定时横幅 */}
      {isScheduled && (
        <div className="flex shrink-0 items-center gap-2 border-b border-amber-200 bg-amber-50 px-4 py-1.5 t-sm text-amber-700">
          <AlarmClock className="h-3.5 w-3.5 shrink-0" />
          已定时 {fmtSendAt(draft.send_at!)} 自动发送（发送前仍可继续编辑）
          <button
            className="ml-auto rounded-md border border-amber-300 px-2 py-0.5 t-xs text-amber-700 hover:bg-amber-100 disabled:opacity-50"
            onClick={() => unscheduleMutation.mutate()}
            disabled={unscheduleMutation.isPending}
          >
            取消定时
          </button>
          {unscheduleMutation.isError && (
            <span className="t-xs text-red-500">{(unscheduleMutation.error as Error).message}</span>
          )}
        </div>
      )}

      {/* 字段区：收件人 / 抄送密送（默认折叠）/ 主题 / 附件。收件人走 chips+联想（v0.4 P4） */}
      <div className="shrink-0 divide-y divide-gray-100 border-b border-gray-100">
        <div className="flex items-center gap-1.5 px-4 py-1.5">
          <span className="w-11 shrink-0 t-sm text-gray-400">收件人</span>
          <RecipientChipsInput
            value={to}
            onChange={setTo}
            placeholder="输入地址或从通讯录联想，回车确认"
            autoFocus={draft.mode === 'new' && !to && !subject && !bodyHtml}
          />
          {!showCc && (
            <button
              className="shrink-0 whitespace-nowrap rounded-md px-1.5 py-0.5 t-sm text-indigo-500 hover:bg-indigo-50"
              onClick={() => setShowCc(true)}
            >
              抄送/密送
            </button>
          )}
        </div>
        {showCc && (
          <div className="flex items-center gap-1.5 px-4 py-1.5">
            <span className="w-11 shrink-0 t-sm text-gray-400">抄送</span>
            <RecipientChipsInput value={cc} onChange={setCc} />
            {!showBcc && (
              <button
                className="shrink-0 whitespace-nowrap rounded-md px-1.5 py-0.5 t-sm text-indigo-500 hover:bg-indigo-50"
                onClick={() => setShowBcc(true)}
                title="添加密送"
              >
                密送
              </button>
            )}
            <button
              className="shrink-0 whitespace-nowrap rounded-md px-1.5 py-0.5 t-sm text-gray-400 hover:bg-gray-50 hover:text-gray-600"
              onClick={() => {
                setShowCc(false)
                setShowBcc(false)
              }}
              title="收起抄送/密送（内容保留）"
            >
              收起
            </button>
          </div>
        )}
        {showCc && showBcc && (
          <div className="flex items-center gap-1.5 px-4 py-1.5">
            <span className="w-11 shrink-0 t-sm text-gray-400">密送</span>
            <RecipientChipsInput value={bcc} onChange={setBcc} />
            <button
              className="shrink-0 whitespace-nowrap rounded-md px-1.5 py-0.5 t-sm text-gray-400 hover:bg-gray-50 hover:text-gray-600"
              onClick={() => {
                setShowCc(false)
                setShowBcc(false)
              }}
              title="收起抄送/密送（内容保留）"
            >
              收起
            </button>
          </div>
        )}
        <div className="flex items-center gap-1.5 px-4 py-1.5">
          <span className="w-11 shrink-0 t-sm text-gray-400">主题</span>
          <input
            className={`${fieldInput} font-medium`}
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            placeholder="邮件主题"
          />
        </div>
        <div className="flex flex-wrap items-center gap-1.5 px-4 py-1.5">
          <label className="flex cursor-pointer items-center gap-1 whitespace-nowrap rounded-md px-1 py-0.5 t-sm text-gray-500 hover:text-indigo-600">
            {attBusy ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Paperclip className="h-3.5 w-3.5" />
            )}
            添加附件
            <input
              type="file"
              multiple
              className="hidden"
              onChange={(e) => {
                void uploadAtts(Array.from(e.target.files ?? []))
                e.target.value = ''
              }}
            />
          </label>
          {atts.map((a) => (
            <span
              key={a.id}
              className="inline-flex max-w-52 items-center gap-1 rounded-md bg-gray-100 px-2 py-0.5 t-xs text-gray-600"
            >
              <span className="truncate" title={a.filename}>
                {a.filename}
              </span>
              <span className="shrink-0 text-gray-400">{fmtSize(a.size)}</span>
              <button
                className="shrink-0 text-gray-400 hover:text-red-500"
                onClick={() => void removeAtt(a.id)}
                title="删除附件"
              >
                <X className="h-3 w-3" />
              </button>
            </span>
          ))}
          {attError && <span className="t-xs text-red-500">{attError}</span>}
        </div>
      </div>

      {/* AI 写作入口行（AI 停用时隐藏，回归传统写信） */}
      {aiEnabled && (
        <div className="flex shrink-0 items-center gap-1.5 border-b border-gray-100 px-3 py-1">
          <button
            className="inline-flex items-center gap-1 rounded-md border border-violet-200 bg-violet-50 px-2 py-0.5 t-sm font-medium text-violet-700 transition-colors hover:bg-violet-100 disabled:opacity-50"
            onClick={() => setAiOpen(true)}
            disabled={!editor}
          >
            <Sparkles className="h-3.5 w-3.5" />
            AI 写作
          </button>
          <span className="t-xs text-gray-400">按指令整篇生成，或对现有正文润色/翻译</span>
        </div>
      )}

      <EditorToolbar
        editor={editor}
        extra={
          <>
            <TemplateMenu editor={editor} onManage={() => setTplOpen(true)} />
            <SignatureMenu
              editor={editor}
              accounts={accounts}
              accountId={accountId}
              onManage={() => setSigOpen(true)}
            />
          </>
        }
      />
      <EditorSurface editor={editor} />

      {/* 底部操作条 */}
      <div className="flex shrink-0 flex-wrap items-center gap-2 border-t border-gray-200 bg-gray-50 px-4 py-2">
        <button
          className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-5 py-1.5 t-sm font-medium text-white transition-colors hover:bg-indigo-700 disabled:opacity-50"
          onClick={() => sendNowRef.current()}
          disabled={submitDisabled}
        >
          {sendMutation.isPending ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Send className="h-3.5 w-3.5" />
          )}
          {sendMutation.isPending ? '发送中…' : '发送'}
        </button>
        <button
          className="rounded-lg border border-gray-300 px-3 py-1.5 t-sm text-gray-700 transition-colors hover:bg-gray-100"
          onClick={() => {
            void doSaveRef.current().then(() => requestClose(tabId))
          }}
          title="保存并收起标签（草稿保留，下次启动自动恢复）"
        >
          存草稿
        </button>
        <button
          className="inline-flex items-center gap-1 rounded-lg border border-gray-300 px-3 py-1.5 t-sm text-gray-700 transition-colors hover:bg-gray-100"
          onClick={() => setSchedOpen(true)}
          title="定时发送：到点由后台自动发出"
        >
          <AlarmClock className="h-3.5 w-3.5" />
          定时
        </button>
        <button
          className="inline-flex items-center gap-1 rounded-lg border border-gray-300 px-3 py-1.5 t-sm text-gray-700 transition-colors hover:bg-gray-100 disabled:opacity-50"
          onClick={() => {
            void api.composePreview(bodyHtml).then((r) => setPreviewHtml(r.html))
          }}
          disabled={!bodyHtml.trim() || sendMutation.isPending}
          title="以收件人视角预览最终排版（与发送管线同参）"
        >
          <Eye className="h-3.5 w-3.5" />
          预览
        </button>
        <span className="flex-1" />
        {saveError ? (
          <span className="t-xs text-red-500">自动保存失败，请检查后端服务</span>
        ) : savedAt ? (
          <span className="t-xs text-gray-400">已保存 {savedAt}</span>
        ) : null}
        {sendMutation.isError && (
          <span className="max-w-64 truncate t-xs text-red-500" title={(sendMutation.error as Error).message}>
            {(sendMutation.error as Error).message}
          </span>
        )}
        <select
          className="max-w-56 rounded-lg border border-gray-300 bg-white px-2 py-1.5 t-sm outline-none focus:border-indigo-500"
          value={accountId}
          onChange={(e) => setAccountId(Number(e.target.value))}
          title="发件账号"
        >
          {accounts.map((a) => (
            <option key={a.id} value={a.id}>
              {a.email}
            </option>
          ))}
        </select>
      </div>

      {/* AI 写作对话框 */}
      {aiOpen && editor && <AiWriteDialog editor={editor} onClose={() => setAiOpen(false)} />}
      {tplOpen && <TemplateManager onClose={() => setTplOpen(false)} />}
      {sigOpen && <SignatureEditor accounts={accounts} onClose={() => setSigOpen(false)} />}

      {/* 收件人视角预览：与发送管线同参（消毒+内联化+wrap），沙箱 iframe 渲染 */}
      {previewHtml && (
        <Modal title="收件人视角预览" onClose={() => setPreviewHtml(null)} width="max-w-2xl">
          <iframe
            title="收件人视角预览"
            sandbox=""
            srcDoc={previewHtml}
            className="h-[60vh] w-full rounded-lg border border-gray-200 bg-white"
          />
          <p className="mt-2 t-xs text-gray-400">
            与发出内容同一处理管线（消毒 → 收件端样式内联化 → 基础样式外层）——这就是收件人看到的排版。
          </p>
        </Modal>
      )}

      {/* 定时发送对话框 */}
      {schedOpen && (
        <Modal title="定时发送" onClose={() => setSchedOpen(false)} width="max-w-sm">
          <div className="space-y-3">
            <input
              type="datetime-local"
              className="w-full rounded-lg border border-gray-300 px-3 py-2 t-sm outline-none focus:border-indigo-500"
              value={schedAt}
              onChange={(e) => setSchedAt(e.target.value)}
            />
            <p className="t-xs text-gray-400">
              到点由后台自动发送并通知你；发送前可继续编辑，也可随时取消定时。修改后会自动保存当前内容。
            </p>
            {scheduleMutation.isError && (
              <div className="t-sm text-red-500">{(scheduleMutation.error as Error).message}</div>
            )}
            <div className="flex justify-end gap-2">
              <button
                className="rounded-lg border border-gray-300 px-3 py-1.5 t-sm text-gray-700 hover:bg-gray-50"
                onClick={() => setSchedOpen(false)}
              >
                取消
              </button>
              <button
                className="rounded-lg bg-indigo-600 px-4 py-1.5 t-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
                onClick={() => scheduleMutation.mutate()}
                disabled={!schedAt || scheduleMutation.isPending}
              >
                {scheduleMutation.isPending ? '设置中…' : '确定定时'}
              </button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}
