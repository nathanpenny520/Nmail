// 键盘快捷键唯一数据源：设置页「快捷键」分类与 MailBrowser `?` 帮助面板共用。
// 改键位先改这里，再核对 docs/使用指南.md 的表格。
export interface ShortcutItem {
  keys: string
  desc: string
  /** 物理键位备注（组合键如 ?=Shift+/、#=Shift+3），展示在说明后 */
  sub?: string
}

export interface ShortcutGroup {
  title: string
  /** 生效范围：主界面键位仅挂在「邮件」页签，写信组仅写信时响应 */
  scope: string
  items: ShortcutItem[]
}

export const SHORTCUT_GROUPS: ShortcutGroup[] = [
  {
    title: '列表导航',
    scope: '仅「邮件」页签',
    items: [
      { keys: 'j / ↓', desc: '下一封' },
      { keys: 'k / ↑', desc: '上一封' },
      { keys: 'Enter / o', desc: '打开' },
      { keys: 'x', desc: '勾选/取消' },
      { keys: 'Ctrl/⌘+A', desc: '全选/清空' },
    ],
  },
  {
    title: '邮件操作',
    scope: '仅「邮件」页签',
    items: [
      { keys: 'e', desc: '归档' },
      { keys: '# / Del', desc: '删除（废纸篓）', sub: '# 即 Shift+3' },
      { keys: 'c', desc: '写新邮件' },
      { keys: 'Shift+M', desc: '检查新邮件' },
    ],
  },
  {
    title: '读信界面',
    scope: '读信时',
    items: [
      { keys: 'r', desc: '回复' },
      { keys: 'a', desc: '全部回复' },
      { keys: 'f', desc: '转发' },
    ],
  },
  {
    title: '搜索与帮助',
    scope: '仅「邮件」页签',
    items: [
      { keys: '/', desc: '聚焦搜索' },
      { keys: '?', desc: '本帮助', sub: '即 Shift+/' },
      { keys: 'Esc', desc: '关闭/返回列表' },
    ],
  },
  {
    title: '写信',
    scope: '写信时',
    items: [
      { keys: 'Ctrl/⌘+S', desc: '存草稿' },
      { keys: 'Ctrl/⌘+Enter', desc: '发送' },
    ],
  },
]
