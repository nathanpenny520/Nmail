import { EditorContent, useEditor, useEditorState, type Editor } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import TextAlign from '@tiptap/extension-text-align'
import Highlight from '@tiptap/extension-highlight'
import Image from '@tiptap/extension-image'
import Placeholder from '@tiptap/extension-placeholder'
import { Table } from '@tiptap/extension-table'
import TableCell from '@tiptap/extension-table-cell'
import TableHeader from '@tiptap/extension-table-header'
import TableRow from '@tiptap/extension-table-row'
import { Color, FontFamily, FontSize, TextStyle } from '@tiptap/extension-text-style'
import {
  AlignCenter, AlignLeft, AlignRight, Baseline, Bold, Code2, Highlighter, ImagePlus,
  IndentDecrease, IndentIncrease, Italic, Link2, List, ListOrdered, Minus, Quote,
  Redo2, RemoveFormatting, Strikethrough, Table as TableIcon, Trash2, Underline, Undo2,
} from 'lucide-react'
import { useRef, useState } from 'react'
import ContextMenu, { type ContextMenuItem } from '../ContextMenu'
import { Modal } from './ui'

/** 编辑器内嵌图上限（base64 直发，超过提示改用附件） */
const MAX_IMAGE_BYTES = 1.5 * 1024 * 1024

/** 字体带跨平台回退：macOS/Windows 各有原生中文黑体类字体，收发两端都落到最接近的 */
const FONT_FAMILIES: { label: string; value: string }[] = [
  { label: '默认字体', value: '' },
  { label: '苹方', value: "'PingFang SC', 'Microsoft YaHei', sans-serif" },
  { label: '微软雅黑', value: "'Microsoft YaHei', 'PingFang SC', sans-serif" },
  { label: '宋体', value: "'SimSun', 'Songti SC', serif" },
  { label: '黑体', value: "'SimHei', 'Heiti SC', sans-serif" },
  { label: '楷体', value: "'KaiTi', 'Kaiti SC', serif" },
  { label: 'Arial', value: 'Arial, sans-serif' },
  { label: 'Georgia', value: 'Georgia, serif' },
  { label: 'Courier New', value: "'Courier New', monospace" },
]

/** 单元格底色扩展：以内联 style 落盘（nh3 白名单放行 style，收件端可见） */
const BgTableCell = TableCell.extend({
  addAttributes() {
    return {
      ...this.parent?.(),
      backgroundColor: {
        default: null,
        parseHTML: (el) => (el as HTMLElement).style?.backgroundColor || null,
        renderHTML: (attrs) =>
          (attrs as { backgroundColor?: string | null }).backgroundColor
            ? { style: `background-color:${(attrs as { backgroundColor: string }).backgroundColor}` }
            : {},
      },
    }
  },
})

/** 单元格底色候选（浅色系，正文字色 #1f2937 下对比度足够） */
const CELL_COLORS: { label: string; value: string | null }[] = [
  { label: '清除底色', value: null },
  { label: '浅黄', value: '#fef3c7' },
  { label: '浅蓝', value: '#dbeafe' },
  { label: '浅绿', value: '#dcfce7' },
  { label: '浅红', value: '#fee2e2' },
  { label: '浅紫', value: '#f3e8ff' },
  { label: '浅灰', value: '#f3f4f6' },
]

const FONT_SIZES = ['12px', '13px', '14px', '15px', '16px', '18px', '20px', '24px', '32px']

/**
 * 创建写信编辑器实例。onChange/onCtrlEnter 经 ref 转发，避免闭包过期。
 * StarterKit v3 已含 Underline/Link/History，链接点击在编辑器内不跳转。
 */
export function useMailEditor(initialHtml: string, onChange: (html: string) => void, onCtrlEnter: () => void) {
  const cbRef = useRef({ onChange, onCtrlEnter })
  cbRef.current = { onChange, onCtrlEnter }
  return useEditor({
    extensions: [
      StarterKit.configure({
        heading: { levels: [1, 2, 3] },
        link: { openOnClick: false, defaultProtocol: 'https' },
      }),
      TextStyle,
      Color,
      FontFamily,
      FontSize,
      Highlight.configure({ multicolor: true }),
      TextAlign.configure({ types: ['heading', 'paragraph'] }),
      Image.configure({ allowBase64: true }),
      Placeholder.configure({ placeholder: '写信正文…' }),
      Table.configure({ resizable: true }),
      TableRow,
      TableHeader,
      BgTableCell,
    ],
    content: initialHtml || '<p></p>',
    editorProps: {
      attributes: { class: 'mail-editor-content' },
      handleKeyDown: (_view, event) => {
        if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
          cbRef.current.onCtrlEnter()
          return true
        }
        return false
      },
    },
    onUpdate: ({ editor }) => cbRef.current.onChange(editor.getHTML()),
  })
}

function Sep() {
  return <span className="mx-0.5 h-4 w-px shrink-0 bg-gray-200" />
}

function TBtn({
  title, active, disabled, onClick, children,
}: {
  title: string
  active?: boolean
  disabled?: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      title={title}
      disabled={disabled}
      onMouseDown={(e) => e.preventDefault()}
      onClick={onClick}
      className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-md transition-colors disabled:opacity-30 ${
        active ? 'bg-indigo-100 text-indigo-700' : 'text-gray-600 hover:bg-gray-100'
      }`}
    >
      {children}
    </button>
  )
}

function pickColor(onPick: (color: string) => void, title: string, icon: React.ReactNode) {
  return (
    <label
      title={title}
      onMouseDown={(e) => e.preventDefault()}
      className="flex h-7 w-7 shrink-0 cursor-pointer items-center justify-center rounded-md text-gray-600 hover:bg-gray-100"
    >
      {icon}
      <input type="color" className="hidden" onChange={(e) => onPick(e.target.value)} />
    </label>
  )
}

/** 富文本工具栏，对齐常见网页邮箱：撤销重做 / 清格式 / 字体字号 / BISU / 颜色高亮 / 列表缩进对齐 / 引用代码表格链接图片；extra 渲染在行尾（模板/签名） */
export function EditorToolbar({ editor, extra }: { editor: Editor | null; extra?: React.ReactNode }) {
  const state = useEditorState({
    editor,
    selector: ({ editor: e }) =>
      e
        ? {
            canUndo: e.can().undo(),
            canRedo: e.can().redo(),
            bold: e.isActive('bold'),
            italic: e.isActive('italic'),
            underline: e.isActive('underline'),
            strike: e.isActive('strike'),
            blockquote: e.isActive('blockquote'),
            codeBlock: e.isActive('codeBlock'),
            bulletList: e.isActive('bulletList'),
            orderedList: e.isActive('orderedList'),
            alignLeft: e.isActive({ textAlign: 'left' }),
            alignCenter: e.isActive({ textAlign: 'center' }),
            alignRight: e.isActive({ textAlign: 'right' }),
            link: e.isActive('link'),
            inTable: e.isActive('table'),
            fontSize: (e.getAttributes('textStyle').fontSize as string | undefined) ?? '',
            fontFamily: (e.getAttributes('textStyle').fontFamily as string | undefined) ?? '',
          }
        : null,
  })
  const [linkOpen, setLinkOpen] = useState(false)
  if (!editor || !state) return null
  const chain = () => editor.chain().focus()

  return (
    <>
    <div className="flex flex-wrap items-center gap-0.5 border-b border-gray-100 px-2 py-1">
      <TBtn title="撤销" disabled={!state.canUndo} onClick={() => chain().undo().run()}>
        <Undo2 className="h-4 w-4" />
      </TBtn>
      <TBtn title="重做" disabled={!state.canRedo} onClick={() => chain().redo().run()}>
        <Redo2 className="h-4 w-4" />
      </TBtn>
      <TBtn title="清除格式" onClick={() => chain().clearNodes().unsetAllMarks().run()}>
        <RemoveFormatting className="h-4 w-4" />
      </TBtn>
      <Sep />
      <select
        className="h-7 max-w-24 rounded-md border border-transparent px-1 t-sm text-gray-600 hover:border-gray-200 focus:border-indigo-400 focus:outline-none"
        title="字体"
        value={state.fontFamily}
        onChange={(e) =>
          e.target.value ? chain().setFontFamily(e.target.value).run() : chain().unsetFontFamily().run()
        }
      >
        {FONT_FAMILIES.map((f) => (
          <option key={f.label} value={f.value}>
            {f.label}
          </option>
        ))}
      </select>
      <select
        className="h-7 max-w-20 rounded-md border border-transparent px-1 t-sm text-gray-600 hover:border-gray-200 focus:border-indigo-400 focus:outline-none"
        title="字号"
        value={state.fontSize}
        onChange={(e) =>
          e.target.value ? chain().setFontSize(e.target.value).run() : chain().unsetFontSize().run()
        }
      >
        {!state.fontSize && <option value="">字号</option>}
        {FONT_SIZES.map((s) => (
          <option key={s} value={s}>
            {parseInt(s, 10)}
          </option>
        ))}
      </select>
      <Sep />
      <TBtn title="加粗" active={state.bold} onClick={() => chain().toggleBold().run()}>
        <Bold className="h-4 w-4" />
      </TBtn>
      <TBtn title="斜体" active={state.italic} onClick={() => chain().toggleItalic().run()}>
        <Italic className="h-4 w-4" />
      </TBtn>
      <TBtn title="下划线" active={state.underline} onClick={() => chain().toggleUnderline().run()}>
        <Underline className="h-4 w-4" />
      </TBtn>
      <TBtn title="删除线" active={state.strike} onClick={() => chain().toggleStrike().run()}>
        <Strikethrough className="h-4 w-4" />
      </TBtn>
      {pickColor((c) => chain().setColor(c).run(), '文字颜色', <Baseline className="h-4 w-4" />)}
      {pickColor(
        (c) => chain().toggleHighlight({ color: c }).run(),
        '背景高亮',
        <Highlighter className="h-4 w-4" />,
      )}
      <Sep />
      <TBtn title="无序列表" active={state.bulletList} onClick={() => chain().toggleBulletList().run()}>
        <List className="h-4 w-4" />
      </TBtn>
      <TBtn title="有序列表" active={state.orderedList} onClick={() => chain().toggleOrderedList().run()}>
        <ListOrdered className="h-4 w-4" />
      </TBtn>
      <TBtn title="列表缩进" onClick={() => chain().sinkListItem('listItem').run()}>
        <IndentIncrease className="h-4 w-4" />
      </TBtn>
      <TBtn title="列表减缩进" onClick={() => chain().liftListItem('listItem').run()}>
        <IndentDecrease className="h-4 w-4" />
      </TBtn>
      <Sep />
      <TBtn title="左对齐" active={state.alignLeft} onClick={() => chain().setTextAlign('left').run()}>
        <AlignLeft className="h-4 w-4" />
      </TBtn>
      <TBtn title="居中" active={state.alignCenter} onClick={() => chain().setTextAlign('center').run()}>
        <AlignCenter className="h-4 w-4" />
      </TBtn>
      <TBtn title="右对齐" active={state.alignRight} onClick={() => chain().setTextAlign('right').run()}>
        <AlignRight className="h-4 w-4" />
      </TBtn>
      <Sep />
      <TBtn title="引用" active={state.blockquote} onClick={() => chain().toggleBlockquote().run()}>
        <Quote className="h-4 w-4" />
      </TBtn>
      <TBtn title="代码块" active={state.codeBlock} onClick={() => chain().toggleCodeBlock().run()}>
        <Code2 className="h-4 w-4" />
      </TBtn>
      <TBtn title="分隔线" onClick={() => chain().setHorizontalRule().run()}>
        <Minus className="h-4 w-4" />
      </TBtn>
      <Sep />
      <TBtn
        title={state.link ? '编辑链接' : '插入链接'}
        active={state.link}
        onClick={() => setLinkOpen(true)}
      >
        <Link2 className="h-4 w-4" />
      </TBtn>
      {pickColorImg(editor)}
      <TBtn
        title="插入表格"
        onClick={() => chain().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run()}
      >
        <TableIcon className="h-4 w-4" />
      </TBtn>
      {state.inTable && (
        <TBtn title="删除当前表格" onClick={() => chain().deleteTable().run()}>
          <Trash2 className="h-4 w-4" />
        </TBtn>
      )}
      {extra && (
        <>
          <Sep />
          <span className="flex-1" />
          {extra}
        </>
      )}
    </div>
      {linkOpen && <LinkDialog editor={editor} onClose={() => setLinkOpen(false)} />}
    </>
  )
}

/** 链接插入/编辑弹窗（替代 window.prompt）：地址规范化，清空保存=移除链接 */
function LinkDialog({ editor, onClose }: { editor: Editor; onClose: () => void }) {
  const [url, setUrl] = useState((editor.getAttributes('link').href as string | undefined) ?? '')
  const isLink = editor.isActive('link')
  const apply = () => {
    const trimmed = url.trim()
    if (!trimmed) {
      editor.chain().focus().extendMarkRange('link').unsetLink().run()
    } else {
      const href = /^(https?:\/\/|mailto:)/i.test(trimmed) ? trimmed : `https://${trimmed}`
      editor.chain().focus().extendMarkRange('link').setLink({ href }).run()
    }
    onClose()
  }
  return (
    <Modal title={isLink ? '编辑链接' : '插入链接'} onClose={onClose} width="max-w-md">
      <div className="space-y-3">
        <input
          className="w-full rounded-lg border border-gray-300 px-3 py-2 t-sm outline-none focus:border-indigo-500"
          placeholder="链接地址，如 example.com 或 https://…"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') apply()
          }}
          autoFocus
        />
        <div className="flex items-center justify-end gap-2">
          {isLink && (
            <button
              className="mr-auto rounded-lg px-3 py-1.5 t-sm text-red-500 hover:bg-red-50"
              onClick={() => {
                editor.chain().focus().extendMarkRange('link').unsetLink().run()
                onClose()
              }}
            >
              移除链接
            </button>
          )}
          <button
            className="rounded-lg border border-gray-300 px-3 py-1.5 t-sm text-gray-700 hover:bg-gray-50"
            onClick={onClose}
          >
            取消
          </button>
          <button
            className="rounded-lg bg-indigo-600 px-4 py-1.5 t-sm font-medium text-white hover:bg-indigo-700"
            onClick={apply}
          >
            确定
          </button>
        </div>
      </div>
    </Modal>
  )
}

/** 图片插入：本地文件转 base64 内嵌（超过上限提示改用附件） */
function pickColorImg(editor: Editor) {
  return (
    <label
      title="插入图片（本地图片内嵌发送）"
      onMouseDown={(e) => e.preventDefault()}
      className="flex h-7 w-7 shrink-0 cursor-pointer items-center justify-center rounded-md text-gray-600 hover:bg-gray-100"
    >
      <ImagePlus className="h-4 w-4" />
      <input
        type="file"
        accept="image/*"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0]
          e.target.value = ''
          if (!file) return
          if (file.size > MAX_IMAGE_BYTES) {
            window.alert('图片超过 1.5MB，建议以附件形式添加')
            return
          }
          const reader = new FileReader()
          reader.onload = () => {
            editor.chain().focus().setImage({ src: String(reader.result) }).run()
          }
          reader.readAsDataURL(file)
        }}
      />
    </label>
  )
}

/** 表格右键菜单条目：行列增删 / 表头切换 / 合并拆分 / 单元格底色 / 危险删除项 */
function tableMenuItems(editor: Editor): ContextMenuItem[] {
  const run = (fn: (c: ReturnType<Editor['chain']>) => void) => () =>
    fn(editor.chain().focus())
  const canDo = (fn: (c: ReturnType<Editor['can']>) => boolean) =>
    fn(editor.can())
  return [
    { label: '上方插入行', onSelect: run((c) => c.addRowBefore().run()) },
    { label: '下方插入行', onSelect: run((c) => c.addRowAfter().run()) },
    { label: '左侧插入列', onSelect: run((c) => c.addColumnBefore().run()) },
    { label: '右侧插入列', onSelect: run((c) => c.addColumnAfter().run()) },
    { label: '切换表头行', onSelect: run((c) => c.toggleHeaderRow().run()) },
    {
      label: '单元格底色',
      children: CELL_COLORS.map((c) => ({
        label: c.label,
        onSelect: () => editor.chain().focus().setCellAttribute('backgroundColor', c.value).run(),
      })),
    },
    { label: '合并单元格', disabled: !canDo((c) => c.mergeCells()), onSelect: run((c) => c.mergeCells().run()) },
    { label: '拆分单元格', disabled: !canDo((c) => c.splitCell()), onSelect: run((c) => c.splitCell().run()) },
    { label: '删除行', danger: true, onSelect: run((c) => c.deleteRow().run()) },
    { label: '删除列', danger: true, onSelect: run((c) => c.deleteColumn().run()) },
    { label: '删除表格', danger: true, onSelect: run((c) => c.deleteTable().run()) },
  ]
}

/** 编辑器内容区（工具栏之下的正文画布）。表格上右键出编辑菜单，其余区域保留原生菜单（复制粘贴）。 */
export function EditorSurface({ editor }: { editor: Editor | null }) {
  const [menu, setMenu] = useState<{ x: number; y: number } | null>(null)
  const onContextMenu = (e: React.MouseEvent) => {
    if (!editor || !editor.isActive('table')) return
    e.preventDefault()
    const pos = editor.view.posAtCoords({ left: e.clientX, top: e.clientY })
    if (pos) editor.commands.setTextSelection(pos.pos) // 光标落进所点单元格，菜单操作以它为基准
    setMenu({ x: e.clientX, y: e.clientY })
  }
  return (
    <div className="mail-editor min-h-0 flex-1 overflow-y-auto" onContextMenu={onContextMenu}>
      <EditorContent editor={editor} />
      {menu && editor && (
        <ContextMenu x={menu.x} y={menu.y} items={tableMenuItems(editor)} onClose={() => setMenu(null)} />
      )}
    </div>
  )
}
