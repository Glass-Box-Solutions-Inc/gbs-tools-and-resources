// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
import { Bot, User } from 'lucide-react'
import { ToolCallCard } from './ToolCallCard'
import type { AgentStreamEvent } from '../../../lib/types'

interface AgentMessageProps {
  role: 'user' | 'assistant'
  content: string
  events?: AgentStreamEvent[]
}

export function AgentMessage({ role, content, events = [] }: AgentMessageProps) {
  const isUser = role === 'user'

  // Pair each tool_call event with its corresponding tool_result by name
  const toolPairs: Array<{
    call: Extract<AgentStreamEvent, { type: 'tool_call' }>
    result?: Extract<AgentStreamEvent, { type: 'tool_result' }>
  }> = []

  for (const event of events) {
    if (event.type === 'tool_call') {
      toolPairs.push({ call: event })
    } else if (event.type === 'tool_result') {
      // Find the first unpaired call with a matching name and attach the result
      const pending = toolPairs.find((p) => p.call.name === event.name && !p.result)
      if (pending) pending.result = event
    }
  }

  return (
    <div className={`flex gap-3 ${isUser ? 'flex-row-reverse' : ''}`}>
      {/* Avatar */}
      <div
        className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center ${
          isUser ? 'bg-teal-100' : 'bg-gray-100'
        }`}
      >
        {isUser ? (
          <User className="w-4 h-4 text-teal-600" />
        ) : (
          <Bot className="w-4 h-4 text-gray-600" />
        )}
      </div>

      <div className={`max-w-[80%] space-y-2 ${isUser ? 'items-end' : ''}`}>
        {/* Tool call cards shown above the assistant text bubble */}
        {!isUser && toolPairs.length > 0 && (
          <div className="space-y-1.5">
            {toolPairs.map((pair, i) => (
              <ToolCallCard key={i} toolCall={pair.call} toolResult={pair.result} />
            ))}
          </div>
        )}

        {/* Text content bubble */}
        {content && (
          <div
            className={`rounded-2xl px-4 py-3 ${
              isUser
                ? 'bg-teal-500 text-white rounded-tr-sm'
                : 'bg-gray-100 text-gray-800 rounded-tl-sm'
            }`}
          >
            <p className="text-sm leading-relaxed whitespace-pre-wrap">{content}</p>
          </div>
        )}
      </div>
    </div>
  )
}
