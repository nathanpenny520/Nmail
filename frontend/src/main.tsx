import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import './index.css'

const queryClient = new QueryClient()

// 应用内屏蔽系统右键菜单（v0.4 验收反馈）：自有右键菜单（树/邮件行）与原生菜单
// 冲突、且点错位置会弹出浏览器菜单——本地客户端不需要系统右键；
// 输入框/富文本编辑区内保留原生菜单（复制粘贴等系统行为）。
document.addEventListener('contextmenu', (e) => {
  const target = e.target as HTMLElement | null
  if (target?.closest('input, textarea, [contenteditable="true"], .ProseMirror')) return
  e.preventDefault()
})

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
)
