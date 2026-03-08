import { useEffect, useRef } from 'react'
import { MessageBubble } from './MessageBubble'
import type { Message } from '../../lib/types'

interface MessageListProps {
  messages: Message[]
}

export function MessageList({ messages }: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null)

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  if (messages.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-gray-400">
        <p>Starting conversation...</p>
      </div>
    )
  }

  return (
    <div className="p-4 space-y-4">
      {messages.map((message, index) => (
        <MessageBubble key={index} message={message} />
      ))}
      <div ref={bottomRef} />
    </div>
  )
}
