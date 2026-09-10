import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { AITestResult, Settings } from '../types'

const inputClass =
  'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm outline-none transition-colors focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100'

export default function SettingsPage() {
  const queryClient = useQueryClient()
  const { data, isLoading, error } = useQuery({ queryKey: ['settings'], queryFn: api.getSettings })

  const [baseUrl, setBaseUrl] = useState('')
  const [model, setModel] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [pollMinutes, setPollMinutes] = useState(5)
  const [digestTime, setDigestTime] = useState('08:30')

  useEffect(() => {
    if (!data) return
    setBaseUrl(data.ai.base_url)
    setModel(data.ai.model)
    setPollMinutes(data.poll_interval_minutes)
    setDigestTime(data.digest_time)
  }, [data])

  const saveMutation = useMutation({
    mutationFn: api.updateSettings,
    onSuccess: (saved: Settings) => {
      queryClient.setQueryData(['settings'], saved)
      setApiKey('')
    },
  })

  const testMutation = useMutation({
    mutationFn: api.testAI,
  })

  const handleSave = () => {
    saveMutation.mutate({
      ai: { base_url: baseUrl, model, ...(apiKey ? { api_key: apiKey } : {}) },
      poll_interval_minutes: pollMinutes,
      digest_time: digestTime,
    })
  }

  const handleTest = () => {
    testMutation.mutate({
      base_url: baseUrl,
      model,
      ...(apiKey ? { api_key: apiKey } : {}),
    })
  }

  const handleClearKey = () => {
    saveMutation.mutate({ ai: { api_key: '' } })
  }

  if (isLoading) {
    return <div className="p-8 text-sm text-gray-400">加载设置中…</div>
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6 p-8">
      <h1 className="text-xl font-semibold">设置</h1>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          设置加载失败：{(error as Error).message}
        </div>
      )}

      {/* AI 端点 */}
      <section className="rounded-2xl border border-gray-200 bg-white p-6 shadow-sm">
        <h2 className="font-semibold">AI 端点（OpenAI 兼容）</h2>
        <p className="mt-1 text-xs leading-relaxed text-gray-500">
          填入任意 OpenAI 兼容服务：OpenAI、DeepSeek、OpenRouter，或本地 Ollama / LM Studio
          （如 <code>http://localhost:11434/v1</code>，密钥可留空）。云端端点会收到邮件正文；
          指向本地端点则 0 外发。
        </p>

        <div className="mt-4 space-y-4">
          <label className="block">
            <span className="mb-1 block text-sm text-gray-600">Base URL</span>
            <input
              className={inputClass}
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              placeholder="https://api.openai.com/v1"
            />
          </label>

          <label className="block">
            <span className="mb-1 block text-sm text-gray-600">
              API Key{' '}
              {data?.ai.api_key_set && (
                <span className="ml-1 text-xs text-emerald-600">已保存（留空则保持不变）</span>
              )}
            </span>
            <input
              className={inputClass}
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder={data?.ai.api_key_set ? '••••••••' : 'sk-…（本地模型可留空）'}
              autoComplete="off"
            />
          </label>

          <label className="block">
            <span className="mb-1 block text-sm text-gray-600">模型名</span>
            <input
              className={inputClass}
              value={model}
              onChange={(e) => setModel(e.target.value)}
              placeholder="gpt-4o-mini / deepseek-chat / qwen3:8b"
            />
          </label>
        </div>

        <div className="mt-5 flex items-center gap-3">
          <button
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-700 disabled:opacity-50"
            onClick={handleSave}
            disabled={saveMutation.isPending}
          >
            {saveMutation.isPending ? '保存中…' : '保存'}
          </button>
          <button
            className="rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50 disabled:opacity-50"
            onClick={handleTest}
            disabled={testMutation.isPending}
          >
            {testMutation.isPending ? '测试中…' : '测试连接'}
          </button>
          {data?.ai.api_key_set && (
            <button
              className="text-xs text-gray-400 underline-offset-2 hover:text-red-500 hover:underline"
              onClick={handleClearKey}
            >
              清除已存密钥
            </button>
          )}
          {saveMutation.isSuccess && !saveMutation.isPending && (
            <span className="text-xs text-emerald-600">已保存</span>
          )}
          {saveMutation.isError && (
            <span className="text-xs text-red-600">保存失败：{(saveMutation.error as Error).message}</span>
          )}
        </div>

        {testMutation.data && <TestResult result={testMutation.data} />}
      </section>

      {/* 通用 */}
      <section className="rounded-2xl border border-gray-200 bg-white p-6 shadow-sm">
        <h2 className="font-semibold">通用</h2>
        <div className="mt-4 grid grid-cols-2 gap-4">
          <label className="block">
            <span className="mb-1 block text-sm text-gray-600">
              轮询间隔（分钟）<span className="ml-1 text-xs text-gray-400">P1 生效</span>
            </span>
            <input
              className={inputClass}
              type="number"
              min={1}
              max={60}
              value={pollMinutes}
              onChange={(e) => setPollMinutes(Number(e.target.value))}
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-sm text-gray-600">
              每日摘要时间<span className="ml-1 text-xs text-gray-400">P3 生效</span>
            </span>
            <input
              className={inputClass}
              type="time"
              value={digestTime}
              onChange={(e) => setDigestTime(e.target.value)}
            />
          </label>
        </div>
      </section>
    </div>
  )
}

function TestResult({ result }: { result: AITestResult }) {
  if (result.ok) {
    return (
      <div className="mt-4 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
        连接成功 · 模型 <b>{result.model}</b> · 延迟 {result.latency_ms} ms
        {result.reply && <> · 回复「{result.reply}」</>}
      </div>
    )
  }
  return (
    <div className="mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
      <p className="font-medium">连接失败</p>
      <p className="mt-1 break-all text-xs">{result.error}</p>
    </div>
  )
}
