// 键盘快捷键唯一数据源：设置页「快捷键」分类与 MailBrowser `?` 帮助面板共用。
// 改键位先改这里，再核对 docs/使用指南.md 的表格。
export interface ShortcutGroup {
  title: string
  items: { keys: string; desc: string }[]
}

export const SHORTCUT_GROUPS: ShortcutGroup[] = [
  {
    title: '列表导航',
    items: [
      { keys: 'j / ↓', desc: '下一封' },
      { keys: 'k / ↑', desc: '上一封' },
      { keys: 'Enter / o', desc: '打开' },
      { keys: 'x', desc: '勾选/取消' },
    ],
  },
  {
    title: '邮件操作',
    items: [
      { keys: 'e', desc: '归档' },
      { keys: '#', desc: '删除（废纸篓）' },
      { keys: 'c', desc: '写新邮件' },
    ],
  },
  {
    title: '搜索与帮助',
    items: [
      { keys: '/', desc: '聚焦搜索' },
      { keys: '?', desc: '本帮助' },
      { keys: 'Esc', desc: '关闭/返回列表' },
    ],
  },
  {
    title: '写信',
    items: [
      { keys: 'Ctrl/⌘+S', desc: '存草稿' },
      { keys: 'Ctrl/⌘+Enter', desc: '发送' },
    ],
  },
]
