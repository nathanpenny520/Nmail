import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

/** 聊天气泡内的紧凑 Markdown 渲染（AI 回复/综述用）。 */
export default function Markdown({ text }: { text: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        p: ({ children }) => <p className="my-1.5 first:mt-0 last:mb-0">{children}</p>,
        ul: ({ children }) => <ul className="my-1.5 list-disc space-y-0.5 pl-4 first:mt-0 last:mb-0">{children}</ul>,
        ol: ({ children }) => <ol className="my-1.5 list-decimal space-y-0.5 pl-4 first:mt-0 last:mb-0">{children}</ol>,
        li: ({ children }) => <li className="leading-relaxed">{children}</li>,
        strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
        h1: ({ children }) => <h1 className="mb-1 mt-2 text-sm font-bold first:mt-0">{children}</h1>,
        h2: ({ children }) => <h2 className="mb-1 mt-2 text-[13px] font-bold first:mt-0">{children}</h2>,
        h3: ({ children }) => <h3 className="mb-1 mt-1.5 text-xs font-bold first:mt-0">{children}</h3>,
        blockquote: ({ children }) => (
          <blockquote className="my-1.5 border-l-2 border-current/30 pl-2 opacity-90">{children}</blockquote>
        ),
        a: ({ children, href }) => (
          <a href={href} target="_blank" rel="noopener noreferrer" className="underline underline-offset-2">
            {children}
          </a>
        ),
        code: ({ children }) => (
          <code className="rounded bg-black/10 px-1 py-0.5 font-mono text-[0.9em]">{children}</code>
        ),
        pre: ({ children }) => (
          <pre className="my-1.5 overflow-x-auto rounded bg-black/10 p-2 font-mono text-[0.9em]">{children}</pre>
        ),
        table: ({ children }) => (
          <table className="my-1.5 w-full border-collapse text-[0.95em]">{children}</table>
        ),
        th: ({ children }) => (
          <th className="border-b border-current/30 px-1.5 py-0.5 text-left font-semibold">{children}</th>
        ),
        td: ({ children }) => (
          <td className="border-b border-current/15 px-1.5 py-0.5 align-top">{children}</td>
        ),
        hr: () => <hr className="my-2 border-current/20" />,
      }}
    >
      {text}
    </ReactMarkdown>
  )
}
