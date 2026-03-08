// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
import { useState, useCallback, useRef } from 'react'
import { streamAgentChat } from '../lib/api/index'
import type { AgentMessage, AgentStreamEvent } from '../lib/types'

interface AgentState {
  messages: AgentMessage[]
  events: AgentStreamEvent[]
  streaming: boolean
  error: string | null
}

export function useAgent() {
  const [state, setState] = useState<AgentState>({
    messages: [],
    events: [],
    streaming: false,
    error: null,
  })
  const abortRef = useRef(false)

  const sendMessage = useCallback(async (content: string) => {
    abortRef.current = false
    const userMsg: AgentMessage = { role: 'user', content }
    const updatedMessages = [...state.messages, userMsg]

    setState((prev) => ({
      ...prev,
      messages: updatedMessages,
      events: [],
      streaming: true,
      error: null,
    }))

    let assistantContent = ''
    const events: AgentStreamEvent[] = []

    try {
      for await (const event of streamAgentChat(updatedMessages)) {
        if (abortRef.current) break

        events.push(event)

        if (event.type === 'text') {
          assistantContent += event.content
        }

        setState((prev) => ({
          ...prev,
          events: [...events],
        }))

        if (event.type === 'done' || event.type === 'error') {
          if (event.type === 'error') {
            setState((prev) => ({ ...prev, error: event.message }))
          }
          break
        }
      }

      if (assistantContent) {
        const assistantMsg: AgentMessage = { role: 'assistant', content: assistantContent }
        setState((prev) => ({
          ...prev,
          messages: [...updatedMessages, assistantMsg],
        }))
      }
    } catch (err) {
      setState((prev) => ({
        ...prev,
        error: err instanceof Error ? err.message : 'Stream failed',
      }))
    } finally {
      setState((prev) => ({ ...prev, streaming: false }))
    }
  }, [state.messages])

  const stop = useCallback(() => {
    abortRef.current = true
  }, [])

  const reset = useCallback(() => {
    abortRef.current = true
    setState({ messages: [], events: [], streaming: false, error: null })
  }, [])

  return {
    messages: state.messages,
    events: state.events,
    streaming: state.streaming,
    error: state.error,
    sendMessage,
    stop,
    reset,
  }
}
