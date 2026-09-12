#!/usr/bin/env node
/**
 * 字号门禁（v0.4 P1，docs/REDESIGN_PLAN.md §9）：应用 UI 的字号只允许走 t-* 令牌，
 * 禁止 Tailwind 裸字号类（text-xs/sm/base/lg/xl/2xl/3xl）与任意值 text-[Npx]——
 * 裸类不跟随设置页的界面字号档位，是历史上「字号大小不一」的直接原因。
 * 白名单：渲染富文本内容的组件（AI Markdown / 邮件正文 iframe），它们有独立排版体系。
 */
import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

const SRC = fileURLToPath(new URL('../frontend/src', import.meta.url))
const WHITELIST = new Set(['components/Markdown.tsx', 'components/HtmlMail.tsx'])
const BAD = /\btext-(?:xs|sm|base|lg|xl|2xl|3xl)\b|text-\[\d+px\]/

const files = []
const walk = (dir) => {
  for (const name of readdirSync(dir, { withFileTypes: true })) {
    const p = join(dir, name.name)
    if (name.isDirectory()) walk(p)
    else if (name.name.endsWith('.tsx')) files.push(p)
  }
}
walk(SRC)

const hits = []
for (const f of files) {
  const rel = f.slice(SRC.length + 1).replaceAll('\\', '/')
  if (WHITELIST.has(rel)) continue
  readFileSync(f, 'utf8').split('\n').forEach((line, i) => {
    if (BAD.test(line)) hits.push(`${rel}:${i + 1}: ${line.trim().slice(0, 120)}`)
  })
}

if (hits.length) {
  console.error(`字号门禁：${hits.length} 处违规（应改用 t-* 令牌，见 docs/REDESIGN_PLAN.md §9）`)
  for (const h of hits) console.error('  ' + h)
  process.exit(1)
}
console.log(`字号门禁通过（${files.length} 个 tsx，白名单 ${WHITELIST.size} 个）`)
