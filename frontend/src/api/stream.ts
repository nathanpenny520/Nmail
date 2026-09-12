/** SSE Agent 事件流客户端（v0.4 P6）：每个 data: 帧是一个 JSON 事件对象。 */
export async function streamAgentEvents(
  url: string,
  body: unknown,
  onEvent: (event: Record<string, unknown>) => void,
): Promise<void> {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok || !res.body) {
    let detail = `HTTP ${res.status}`
    try {
      const bodyJson = await res.json()
      detail = typeof bodyJson.detail === 'string' ? bodyJson.detail : detail
    } catch {
      // 非 JSON 错误体
    }
    throw new Error(detail)
  }
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let sep: number
    while ((sep = buffer.indexOf('\n\n')) !== -1) {
      const raw = buffer.slice(0, sep).trim()
      buffer = buffer.slice(sep + 2)
      if (!raw.startsWith('data:')) continue
      const data = raw.slice(5).trim()
      if (data === '[DONE]') return
      try {
        const parsed = JSON.parse(data)
        if (parsed.error && parsed.type !== 'error') throw new Error(parsed.error)
        onEvent(parsed)
      } catch (err) {
        if (err instanceof SyntaxError) continue // 非 JSON 帧忽略
        throw err
      }
    }
  }
}

/** SSE 流式聊天客户端：逐段回调增量文本；中途错误以异常抛出（前端可见）。 */
export async function streamChat(
  url: string,
  body: unknown,
  onDelta: (text: string) => void,
): Promise<void> {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok || !res.body) {
    let detail = `HTTP ${res.status}`
    try {
      const bodyJson = await res.json()
      detail = typeof bodyJson.detail === 'string' ? bodyJson.detail : detail
    } catch {
      // 非 JSON 错误体
    }
    throw new Error(detail)
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let sep: number
    while ((sep = buffer.indexOf('\n\n')) !== -1) {
      const raw = buffer.slice(0, sep).trim()
      buffer = buffer.slice(sep + 2)
      if (!raw.startsWith('data:')) continue
      const data = raw.slice(5).trim()
      if (data === '[DONE]') return
      try {
        const parsed = JSON.parse(data)
        if (parsed.error) throw new Error(parsed.error)
        if (parsed.delta) onDelta(parsed.delta)
      } catch (err) {
        if (err instanceof SyntaxError) continue // 非 JSON 行跳过
        throw err
      }
    }
  }
}
