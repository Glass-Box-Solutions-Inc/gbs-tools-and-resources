// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
import { useState, useCallback } from 'react'
import { useChatStore } from '../stores/chatStore'
import { chatApi } from '../lib/api'
import type { Message } from '../lib/types'

export function useChat(sessionId: string) {
  const {
    messages,
    addMessage,
    updateState,
    isComplete,
    action,
    setQuickChips,
    setCollectedFields,
  } = useChatStore()

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const sendMessage = useCallback(
    async (content: string) => {
      if (!content.trim() || loading) return

      setLoading(true)
      setError(null)

      // Add user message immediately for optimistic UI
      const userMessage: Message = {
        role: 'user',
        content: content.trim(),
        timestamp: new Date(),
      }
      addMessage(userMessage)

      try {
        const response = await chatApi.sendMessage(sessionId, content.trim())

        // Add assistant response
        const assistantMessage: Message = {
          role: 'assistant',
          content: response.message,
          timestamp: new Date(),
        }
        addMessage(assistantMessage)

        // Update conversation state
        updateState(response.state, response.is_complete, response.action)

        // Store quick chips and collected fields from response
        setQuickChips(response.quick_chips ?? [])
        setCollectedFields(response.collected_fields ?? {})

      } catch (err) {
        const errorMessage = err instanceof Error ? err.message : 'Failed to send message'
        setError(errorMessage)

        addMessage({
          role: 'assistant',
          content: `Error: ${errorMessage}. Please try again.`,
          timestamp: new Date(),
        })
      } finally {
        setLoading(false)
      }
    },
    [sessionId, loading, addMessage, updateState, setQuickChips, setCollectedFields]
  )

  const submitMatter = useCallback(
    async (dryRun: boolean = true) => {
      setLoading(true)
      setError(null)

      try {
        const response = dryRun
          ? await chatApi.previewMatter(sessionId)
          : await chatApi.submitMatter(sessionId)

        const resultMessage: Message = {
          role: 'assistant',
          content: response.status === 'failed'
            ? `Error: ${response.error || response.message}`
            : response.message + (response.meruscase_url ? `\n\nMatter URL: ${response.meruscase_url}` : ''),
          timestamp: new Date(),
        }
        addMessage(resultMessage)

        return response

      } catch (err) {
        const errorMessage = err instanceof Error ? err.message : 'Failed to process matter'
        setError(errorMessage)
        throw err
      } finally {
        setLoading(false)
      }
    },
    [sessionId, addMessage]
  )

  return {
    messages,
    loading,
    error,
    isComplete,
    action,
    sendMessage,
    submitMatter,
  }
}
