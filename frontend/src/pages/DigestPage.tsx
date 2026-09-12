import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Download, Loader2, RefreshCw, Sparkles } from 'lucide-react'
import { useEffect, useMemo, useRef } from 'react'
import { Link } from 'react-router-dom'
import * as echarts from 'echarts/core'
import { BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { api } from '../api/client'
import { useAIEnabled } from '../api/useAI'
import { categoryColorMap, useCategories } from '../api/useMeta'
import Markdown from '../components/Markdown'

echarts.use([BarChart, GridComponent, TooltipComponent, CanvasRenderer])

const INK = { primary: '#0b0b0b', secondary: '#52514e', muted: '#898781', grid: '#e1e0d9' }

function Chart({ option, height }: { option: echarts.EChartsCoreOption; height: number }) {
  const ref = useRef<HTMLDivElement>(null)
  const chartRef = useRef<echarts.ECharts | null>(null)

  useEffect(() => {
    if (!ref.current) return
    const chart = echarts.init(ref.current)
    chartRef.current = chart
    const ro = new ResizeObserver(() => chart.resize())
    ro.observe(ref.current)
    return () => {
      ro.disconnect()
      chart.dispose()
      chartRef.current = null
    }
  }, [])

  useEffect(() => {
    chartRef.current?.setOption(option, true)
  }, [option])

  return <div ref={ref} style={{ height, width: '100%' }} />
}

export default function DigestPage() {
  const queryClient = useQueryClient()
  const aiEnabled = useAIEnabled()
  const categories = useCategories()
  const { data, isLoading } = useQuery({
    queryKey: ['digest'],
    queryFn: api.getDigest,
  })

  const generateMutation = useMutation({
    mutationFn: api.generateDigest,
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['digest'] }),
  })

  const digest = data?.digest ?? null

  const trendOption = useMemo<echarts.EChartsCoreOption>(() => {
    if (!digest) return {}
    return {
      grid: { left: 8, right: 8, top: 24, bottom: 0, containLabel: true },
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      xAxis: {
        type: 'category',
        data: digest.trend.map((t) => t.day.slice(5)),
        axisLine: { lineStyle: { color: '#c3c2b7' } },
        axisTick: { show: false },
        axisLabel: { color: INK.muted, fontSize: 11 },
      },
      yAxis: {
        type: 'value',
        splitLine: { lineStyle: { color: INK.grid } },
        axisLabel: { color: INK.muted, fontSize: 11 },
      },
      series: [{
        type: 'bar',
        data: digest.trend.map((t) => t.count),
        itemStyle: { color: '#2a78d6', borderRadius: [3, 3, 0, 0] },
        barMaxWidth: 22,
        label: { show: true, position: 'top', color: INK.secondary, fontSize: 11 },
      }],
    }
  }, [digest])

  const categoryOption = useMemo<echarts.EChartsCoreOption>(() => {
    if (!digest) return {}
    const entries = Object.entries(digest.by_category)
    // 颜色与徽章同源（/api/meta 下发；色序已过调色板校验器：CVD ΔE 14.5）
    const labelOf = Object.fromEntries(categories.map((c) => [c.key, c.label]))
    const colors = categoryColorMap(categories)
    return {
      grid: { left: 8, right: 40, top: 4, bottom: 0, containLabel: true },
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      xAxis: {
        type: 'value',
        splitLine: { lineStyle: { color: INK.grid } },
        axisLabel: { color: INK.muted, fontSize: 11 },
      },
      yAxis: {
        type: 'category',
        inverse: true,
        data: entries.map(([k]) => labelOf[k] ?? k),
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: INK.secondary, fontSize: 12 },
      },
      series: [{
        type: 'bar',
        data: entries.map(([k, v]) => ({
          value: v,
          itemStyle: { color: colors[k] ?? '#898781', borderRadius: [0, 3, 3, 0] },
        })),
        barMaxWidth: 16,
        label: { show: true, position: 'right', color: INK.secondary, fontSize: 11 },
      }],
    }
  }, [digest, categories])

  const exportMd = () => {
    if (!digest) return
    const d = digest
    const lines = [
      `# Nmail 每日摘要 · ${d.date}`,
      '',
      d.ai_overview && `> ${d.ai_overview}`,
      '',
      `**概览**：新邮件 ${d.overview.new_today} · 未读 ${d.overview.unread} · 需回复 ${d.overview.need_reply} · AI 已归档营销 ${d.overview.auto_archived}`,
      '',
      '## 需要回复',
      ...(d.need_reply.length
        ? d.need_reply.map((i) => `- ${i.sender}「${i.subject}」—— ${i.reason}${i.has_draft ? '（草稿待审）' : ''}`)
        : ['- 无']),
      '',
      '## 重要邮件',
      ...(d.important.length
        ? d.important.map((i) => `- [${i.importance}] ${i.sender}「${i.subject}」`)
        : ['- 无']),
      '',
      '## 近 7 天趋势',
      ...d.trend.map((t) => `- ${t.day}: ${t.count}`),
    ]
    const blob = new Blob([lines.join('\n')], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `nmail-digest-${d.date}.md`
    a.click()
    URL.revokeObjectURL(url)
  }

  if (isLoading) {
    return <div className="p-8 t-md text-gray-400">加载摘要中…</div>
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6 p-8">
      <div className="flex items-center justify-between">
        <h1 className="t-lg font-semibold">
          每日摘要
          {digest && <span className="ml-2 t-md font-normal text-gray-400">{digest.date}</span>}
        </h1>
        <div className="flex items-center gap-2">
          {digest && (
            <button
              className="inline-flex items-center gap-1.5 rounded-lg border border-gray-300 px-3 py-1.5 t-sm text-gray-700 hover:bg-gray-50"
              onClick={exportMd}
            >
              <Download className="h-3.5 w-3.5" /> 导出 Markdown
            </button>
          )}
          {aiEnabled && (
            <button
              className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-1.5 t-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
              onClick={() => generateMutation.mutate()}
              disabled={generateMutation.isPending}
            >
              {generateMutation.isPending
                ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                : <RefreshCw className="h-3.5 w-3.5" />}
              {digest ? '重新生成' : '生成今日摘要'}
            </button>
          )}
        </div>
      </div>

      {!aiEnabled && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 t-md text-amber-800">
          AI 功能已停用（设置 - AI 配置可开启），暂停生成摘要；历史摘要仍可查看与导出。
        </div>
      )}

      {generateMutation.isError && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 t-md text-red-700">
          生成失败：{(generateMutation.error as Error).message}
        </div>
      )}

      {!digest ? (
        <div className="rounded-2xl border border-dashed border-gray-200 px-6 py-16 text-center">
          <Sparkles className="mx-auto h-8 w-8 text-indigo-200" />
          <p className="mt-3 t-md text-gray-400">
            还没有摘要。每天 {data?.dates.length === 0 ? '定时自动生成' : ''}，也可以现在手动生成一份。
          </p>
        </div>
      ) : (
        <>
          {/* AI 综述 */}
          {digest.ai_overview && (
            <div className="rounded-2xl border border-violet-200 bg-violet-50/60 p-5">
              <div className="flex items-center gap-2 t-sm font-semibold text-violet-700">
                <Sparkles className="h-3.5 w-3.5" /> AI 综述
              </div>
              <div className="mt-1 t-md leading-relaxed text-gray-800">
                <Markdown text={digest.ai_overview} />
              </div>
            </div>
          )}

          {/* 概览数字 */}
          <div className="grid grid-cols-4 gap-3">
            {[
              { label: '今日新邮件', value: digest.overview.new_today },
              { label: '未读', value: digest.overview.unread },
              { label: '需回复', value: digest.overview.need_reply },
              { label: 'AI 已归档营销', value: digest.overview.auto_archived },
            ].map((tile) => (
              <div key={tile.label} className="rounded-2xl border border-gray-200 bg-white p-4 text-center shadow-sm">
                <div className="t-lg font-semibold tracking-tight text-gray-900">{tile.value}</div>
                <div className="mt-1 t-sm text-gray-400">{tile.label}</div>
              </div>
            ))}
          </div>

          {/* 图表行 */}
          <div className="grid grid-cols-2 gap-4">
            <div className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm">
              <h2 className="t-md font-medium text-gray-700">近 7 天新邮件</h2>
              <div className="mt-3">
                <Chart option={trendOption} height={200} />
              </div>
            </div>
            <div className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm">
              <h2 className="t-md font-medium text-gray-700">今日分类分布</h2>
              <div className="mt-3">
                <Chart option={categoryOption} height={200} />
              </div>
            </div>
          </div>

          {/* 需要回复 */}
          <div className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm">
            <h2 className="t-md font-medium text-gray-700">
              需要回复（{digest.need_reply.length}）
            </h2>
            {digest.need_reply.length === 0 ? (
              <p className="mt-3 t-sm text-gray-400">没有等你回复的邮件，很清净。</p>
            ) : (
              <ul className="mt-3 divide-y divide-gray-50">
                {digest.need_reply.map((item) => (
                  <li key={item.email_id} className="flex items-center gap-3 py-2.5">
                    <div className="min-w-0 flex-1">
                      <div className="truncate t-md text-gray-800">{item.subject || '（无主题）'}</div>
                      <div className="mt-0.5 t-sm text-gray-400">
                        {item.sender}
                        {item.reason && ` · ${item.reason}`}
                      </div>
                    </div>
                    {item.has_draft && (
                      <Link
                        to="/drafts"
                        className="shrink-0 rounded-lg border border-violet-200 bg-violet-50 px-2.5 py-1 t-sm font-medium text-violet-700 hover:bg-violet-100"
                      >
                        草稿待审
                      </Link>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* 重要邮件 */}
          <div className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm">
            <h2 className="t-md font-medium text-gray-700">重要邮件</h2>
            {digest.important.length === 0 ? (
              <p className="mt-3 t-sm text-gray-400">近期没有重要邮件。</p>
            ) : (
              <ul className="mt-3 divide-y divide-gray-50">
                {digest.important.map((item) => (
                  <li key={item.email_id} className="flex items-center gap-3 py-2.5">
                    <span
                      className={`shrink-0 rounded px-1.5 py-0.5 t-xs font-bold ${
                        item.importance === 'critical'
                          ? 'bg-red-100 text-red-700'
                          : 'bg-amber-100 text-amber-700'
                      }`}
                    >
                      {item.importance === 'critical' ? '紧急' : '重要'}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="truncate t-md text-gray-800">{item.subject || '（无主题）'}</div>
                      <div className="mt-0.5 t-sm text-gray-400">{item.sender}</div>
                    </div>
                    <Link
                      to={`/?focus=${item.email_id}`}
                      className="shrink-0 t-sm text-indigo-600 hover:underline"
                    >
                      查看
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* 各账号 */}
          {digest.by_account.length > 1 && (
            <div className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm">
              <h2 className="t-md font-medium text-gray-700">各账号今日</h2>
              <div className="mt-3 space-y-2">
                {digest.by_account.map((a) => (
                  <div key={a.email} className="flex items-center gap-3 t-sm">
                    <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: a.color }} />
                    <span className="w-52 truncate text-gray-600">{a.email}</span>
                    <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-gray-100">
                      <div
                        className="h-full rounded-full"
                        style={{
                          backgroundColor: a.color,
                          width: `${Math.max(3, (a.count / Math.max(...digest.by_account.map((x) => x.count), 1)) * 100)}%`,
                        }}
                      />
                    </div>
                    <span className="w-20 text-right text-gray-400">
                      {a.count} 封 · {a.unread} 未读
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
