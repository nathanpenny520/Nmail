import type { ReactNode } from 'react'

/** 文档站外链统一样式：新标签打开 + indigo 下划线；URL 经 utils/links.ts 的 docsUrl() 生成。 */
export default function DocsLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a
      className="text-indigo-600 underline underline-offset-2"
      href={href}
      target="_blank"
      rel="noreferrer"
    >
      {children}
    </a>
  )
}
