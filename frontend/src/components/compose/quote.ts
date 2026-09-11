import type { EmailDetail } from '../../types'

export interface ComposePrefill {
  to_addrs: string
  cc_addrs: string
  subject: string
  body_html: string
}

function escapeHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

function prefix(subject: string, mark: string): string {
  const trimmed = subject.trim()
  if (!trimmed) return mark
  return trimmed.toLowerCase().startsWith(mark.toLowerCase().slice(0, 3)) ? trimmed : `${mark} ${trimmed}`
}

/**
 * 回复/转发预填：引用块用 TipTap 原生支持的语义标签（blockquote/p/br/b），
 * 不依赖内联样式——编辑器解析时会丢弃未注册的 style 属性，样式交给 CSS 与收件方客户端。
 */
export function buildComposeInit(mode: 'reply' | 'replyAll' | 'forward', base: EmailDetail): ComposePrefill {
  const date = base.date ? new Date(base.date).toLocaleString('zh-CN', { hour12: false }) : ''
  const sender = base.sender_name ? `${base.sender_name} <${base.sender_email}>` : base.sender_email
  const head = [
    `-------- ${mode === 'forward' ? '转发邮件' : '原始邮件'} --------`,
    `发件人: ${sender}`,
    `日期: ${date}`,
    `主题: ${base.subject || '（无主题）'}`,
  ]
  const quoteBody = escapeHtml((base.body_text || '').slice(0, 2000)).replace(/\n/g, '<br>')
  const bodyHtml =
    `<p><br></p><blockquote><p><b>${head.map(escapeHtml).join('<br>')}</b></p><p>${quoteBody || '<br>'}</p></blockquote>`

  if (mode === 'reply') {
    return { to_addrs: base.sender_email, cc_addrs: '', subject: prefix(base.subject, 'Re:'), body_html: bodyHtml }
  }
  if (mode === 'replyAll') {
    const others = base.recipients.filter((r) => r !== base.sender_email && r !== base.account_email)
    return {
      to_addrs: base.sender_email,
      cc_addrs: others.join(', '),
      subject: prefix(base.subject, 'Re:'),
      body_html: bodyHtml,
    }
  }
  return { to_addrs: '', cc_addrs: '', subject: prefix(base.subject, 'Fwd:'), body_html: bodyHtml }
}
