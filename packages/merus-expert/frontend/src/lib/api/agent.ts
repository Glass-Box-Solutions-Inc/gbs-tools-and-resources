// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
import { getHeaders } from './client'
import type { AgentMessage, AgentStreamEvent } from '../types'

const API_BASE = '/api'

export async function* streamAgentChat(
  messages: AgentMessage[],
  maxIterations?: number
): AsyncGenerator<AgentStreamEvent> {
  const response = await fetch(`${API_BASE}/agent/chat`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify({ messages, max_iterations: maxIterations }),
  })

  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: 'Stream error' }))
    yield { type: 'error', message: err.detail || `HTTP ${response.status}` }
    return
  }

  const reader = response.body?.getReader()
  if (!reader) {
    yield { type: 'error', message: 'No response body' }
    return
  }

  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        const trimmed = line.trim()
        if (!trimmed || !trimmed.startsWith('data: ')) continue
        const json = trimmed.slice(6)
        if (json === '[DONE]') return
        try {
          yield JSON.parse(json) as AgentStreamEvent
        } catch {
          // Skip malformed JSON lines
        }
      }
    }
  } finally {
    reader.releaseLock()
  }
}
