// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
import { useChat } from '../../hooks/useChat'
import { useChatStore } from '../../stores/chatStore'
import { MessageList } from './MessageList'
import { InputArea } from './InputArea'
import { TypingIndicator } from './TypingIndicator'
import { QuickChips } from './QuickChips'

interface ChatContainerProps {
  sessionId: string
}

/**
 * Main chat area component.
 * Renders messages, quick-reply chips, action buttons, and input area.
 */
export function ChatContainer({ sessionId }: ChatContainerProps) {
  const { messages, loading, error, sendMessage, isComplete, action, submitMatter } = useChat(sessionId)
  const { quickChips } = useChatStore()

  const handleSubmit = async () => {
    await submitMatter(false)
  }

  const handlePreview = async () => {
    await submitMatter(true)
  }

  return (
    <div className="flex flex-col h-full">
      {/* Messages Area */}
      <div className="flex-1 overflow-y-auto">
        <MessageList messages={messages} />
        {loading && <TypingIndicator />}
      </div>

      {/* Quick Chips */}
      <QuickChips
        chips={quickChips}
        onSelect={sendMessage}
        disabled={loading}
      />

      {/* Error Banner */}
      {error && (
        <div className="px-4 py-2 bg-red-50 border-t border-red-200 text-red-600 text-sm">
          {error}
        </div>
      )}

      {/* Completion Action Buttons - shown when conversation is complete */}
      {isComplete && action && (
        <div className="px-4 py-3 bg-teal-50 border-t border-teal-200">
          <div className="flex items-center gap-3">
            <div className="w-2 h-2 bg-teal-500 rounded-full flex-shrink-0"></div>
            <span className="text-teal-700 text-sm font-medium flex-1">
              All details collected. Ready to proceed?
            </span>
            <div className="flex gap-2">
              <button
                onClick={handleSubmit}
                disabled={loading}
                className="px-4 py-1.5 bg-teal-500 text-white text-sm rounded-lg hover:bg-teal-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors font-medium"
              >
                Submit
              </button>
              <button
                onClick={handlePreview}
                disabled={loading}
                className="px-4 py-1.5 bg-white text-teal-700 text-sm rounded-lg border border-teal-300 hover:bg-teal-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors font-medium"
              >
                Preview
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Input Area */}
      <div className="border-t border-gray-200">
        <InputArea
          onSend={sendMessage}
          disabled={loading}
          placeholder={
            isComplete
              ? "Type 'restart' to create another matter..."
              : 'Type your response...'
          }
        />
      </div>
    </div>
  )
}
