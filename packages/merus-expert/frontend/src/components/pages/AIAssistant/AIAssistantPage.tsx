// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
import { useState, useRef, useEffect } from 'react'
import { Bot, Send, RotateCcw, Key } from 'lucide-react'
import { Card, Button } from '../../ui'
import { AgentMessage } from './AgentMessage'
import { StreamingIndicator } from './StreamingIndicator'
import { useAgent } from '../../../hooks/useAgent'
import { useSettingsStore } from '../../../stores/settingsStore'
import { navigate } from '../../../router'

// Example prompts shown on the empty-state welcome screen
const SUGGESTION_PROMPTS = [
  'Find the Smith case',
  'Show my active cases',
  'Bill 0.5 hours to case WC-2024-001',
]

export function AIAssistantPage() {
  // isConfigured is a getter function on the store — call it to derive the boolean
  const isConfigured = useSettingsStore((s) => s.isConfigured)()
  const { messages, events, streaming, error, sendMessage, reset } = useAgent()
  const [input, setInput] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)

  // Auto-scroll to bottom whenever messages or streaming events update
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, events])

  if (!isConfigured) {
    return (
      <div className="page-container">
        <Card className="max-w-md mx-auto mt-12 text-center">
          <div className="p-2 bg-amber-50 rounded-full w-12 h-12 flex items-center justify-center mx-auto mb-4">
            <Key className="w-6 h-6 text-amber-500" />
          </div>
          <h3 className="text-lg font-semibold text-gray-900 mb-2">API Key Required</h3>
          <p className="text-sm text-gray-500 mb-4">
            Configure your MerusCase API key to use the AI Assistant.
          </p>
          <Button onClick={() => navigate('/settings')}>Go to Settings</Button>
        </Card>
      </div>
    )
  }

  const handleSend = () => {
    const trimmed = input.trim()
    if (!trimmed || streaming) return
    sendMessage(trimmed)
    setInput('')
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  // Accumulate streamed text from in-progress text events
  let streamingText = ''
  for (const ev of events) {
    if (ev.type === 'text') streamingText += ev.content
  }

  return (
    <div className="flex flex-col h-[calc(100vh-73px)]">
      {/* Message list */}
      <div className="flex-1 overflow-y-auto scrollbar-thin p-6 space-y-4">
        {messages.length === 0 && !streaming && (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <div className="p-3 bg-teal-50 rounded-2xl mb-4">
              <Bot className="w-10 h-10 text-teal-500" />
            </div>
            <h3 className="text-lg font-semibold text-gray-900 mb-1">
              MerusCase AI Assistant
            </h3>
            <p className="text-sm text-gray-500 max-w-md">
              Ask me anything about your cases. I can search cases, check billing, add notes,
              bill time, and more.
            </p>
            <div className="flex flex-wrap gap-2 mt-4 justify-center">
              {SUGGESTION_PROMPTS.map((q) => (
                <button
                  key={q}
                  onClick={() => setInput(q)}
                  className="px-3 py-1.5 text-sm bg-gray-100 text-gray-700 rounded-full hover:bg-teal-50 hover:text-teal-700 transition-colors"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Completed conversation history */}
        {messages.map((msg, i) => (
          <AgentMessage
            key={i}
            role={msg.role}
            content={msg.content}
            // Tool call events are only relevant during streaming; settled messages carry plain text
            events={[]}
          />
        ))}

        {/* Live streaming response */}
        {streaming && (
          <>
            {events.length > 0 ? (
              <AgentMessage role="assistant" content={streamingText} events={events} />
            ) : (
              <StreamingIndicator />
            )}
          </>
        )}

        {error && (
          <div className="px-4 py-2 bg-red-50 border border-red-200 rounded-xl text-red-600 text-sm">
            {error}
          </div>
        )}

        {/* Invisible anchor used for auto-scrolling */}
        <div ref={bottomRef} />
      </div>

      {/* Input bar */}
      <div className="border-t border-gray-200 bg-white p-4">
        <div className="flex items-end gap-2 max-w-4xl mx-auto">
          <Button variant="ghost" onClick={reset} title="Reset conversation" size="sm">
            <RotateCcw className="w-4 h-4" />
          </Button>
          <div className="flex-1 flex items-end gap-2 bg-gray-50 rounded-xl border border-gray-200 focus-within:border-teal-300 focus-within:ring-2 focus-within:ring-teal-100 transition-all">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask the AI assistant..."
              disabled={streaming}
              rows={1}
              className="flex-1 px-4 py-3 bg-transparent resize-none outline-none text-gray-800 placeholder-gray-400 disabled:opacity-50 text-sm"
            />
            <button
              onClick={handleSend}
              disabled={!input.trim() || streaming}
              className="p-3 mr-1 mb-1 rounded-lg bg-teal-500 text-white hover:bg-teal-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              <Send className="w-4 h-4" />
            </button>
          </div>
        </div>
        <p className="text-xs text-gray-400 text-center mt-2">
          Press Enter to send, Shift+Enter for new line
        </p>
      </div>
    </div>
  )
}
