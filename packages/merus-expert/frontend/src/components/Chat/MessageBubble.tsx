// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
import { Bot, User } from 'lucide-react'
import type { Message } from '../../lib/types'

interface MessageBubbleProps {
  message: Message
}

/**
 * Renders a single chat message with full markdown support:
 * - **bold** text
 * - *italic* text
 * - `---` horizontal rules
 * - Lines starting with `- ` rendered as list items
 */
export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === 'user'

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

      {/* Message Content */}
      <div
        className={`max-w-[75%] rounded-2xl px-4 py-3 ${
          isUser
            ? 'bg-teal-500 text-white rounded-tr-sm'
            : 'bg-gray-100 text-gray-800 rounded-tl-sm'
        }`}
      >
        <div className="text-sm leading-relaxed">
          {renderMarkdown(message.content, isUser)}
        </div>
        <div
          className={`text-xs mt-1 ${
            isUser ? 'text-teal-200' : 'text-gray-400'
          }`}
        >
          {formatTime(message.timestamp)}
        </div>
      </div>
    </div>
  )
}

/**
 * Render markdown content as React nodes.
 * Handles: --- (hr), **bold**, *italic*, - lists, plain text.
 */
function renderMarkdown(content: string, isUser: boolean): React.ReactNode[] {
  const lines = content.split('\n')
  const result: React.ReactNode[] = []
  let listItems: string[] = []
  let keyCounter = 0

  const flushList = () => {
    if (listItems.length > 0) {
      result.push(
        <ul key={`list-${keyCounter++}`} className="list-disc list-inside space-y-0.5 my-1">
          {listItems.map((item, i) => (
            <li key={i}>{parseInline(item, isUser)}</li>
          ))}
        </ul>
      )
      listItems = []
    }
  }

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]

    // Horizontal rule
    if (line.trim() === '---') {
      flushList()
      result.push(
        <hr
          key={`hr-${keyCounter++}`}
          className={`my-2 border-0 border-t ${isUser ? 'border-teal-400' : 'border-gray-300'}`}
        />
      )
      continue
    }

    // List item
    if (line.startsWith('- ')) {
      listItems.push(line.slice(2))
      continue
    }

    // Flush any pending list
    flushList()

    // Empty line = paragraph break
    if (line.trim() === '') {
      result.push(<br key={`br-${keyCounter++}`} />)
      continue
    }

    // Regular line with inline formatting
    result.push(
      <span key={`line-${keyCounter++}`} className="block">
        {parseInline(line, isUser)}
      </span>
    )
  }

  // Flush remaining list
  flushList()

  return result
}

/**
 * Parse inline markdown: **bold**, *italic*, backtick code.
 */
function parseInline(text: string, isUser: boolean): React.ReactNode[] {
  // Split on **bold**, *italic* patterns
  const parts = text.split(/(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/g)

  return parts.map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return (
        <strong key={i} className={`font-semibold ${isUser ? 'text-white' : 'text-gray-900'}`}>
          {part.slice(2, -2)}
        </strong>
      )
    }
    if (part.startsWith('*') && part.endsWith('*') && part.length > 2) {
      return (
        <em key={i} className="italic">
          {part.slice(1, -1)}
        </em>
      )
    }
    if (part.startsWith('`') && part.endsWith('`')) {
      return (
        <code
          key={i}
          className={`px-1 py-0.5 rounded text-xs font-mono ${
            isUser ? 'bg-teal-400 text-teal-100' : 'bg-gray-200 text-gray-700'
          }`}
        >
          {part.slice(1, -1)}
        </code>
      )
    }
    return part
  })
}

function formatTime(date: Date): string {
  return new Intl.DateTimeFormat('en-US', {
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  }).format(date)
}
