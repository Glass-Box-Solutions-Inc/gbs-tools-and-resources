// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
import { useState, useEffect } from 'react'
import { MessageCircle } from 'lucide-react'
import { ChatContainer } from '../../Chat/ChatContainer'
import { MatterProgress } from '../../Sidebar/MatterProgress'
import { useChatStore } from '../../../stores/chatStore'
import { chatApi } from '../../../lib/api'
import { LoadingSpinner } from '../../ui'

export function NewMatterPage() {
  const { sessionId, setSession, addMessage, collectedFields } = useChatStore()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Initialize a new chat session on first mount if none exists
  useEffect(() => {
    if (!sessionId) {
      setLoading(true)
      chatApi
        .createSession()
        .then((res) => {
          setSession(res.session_id)
          addMessage({ role: 'assistant', content: res.message, timestamp: new Date() })
        })
        .catch((err) => {
          setError('Failed to start session. ' + (err instanceof Error ? err.message : String(err)))
        })
        .finally(() => setLoading(false))
    }
  }, [sessionId, setSession, addMessage])

  if (loading) {
    return (
      <div className="page-container">
        <LoadingSpinner text="Starting matter session..." />
      </div>
    )
  }

  if (error) {
    return (
      <div className="page-container text-center py-12">
        <p className="text-red-500 mb-3">{error}</p>
        <button onClick={() => window.location.reload()} className="btn-primary">
          Retry
        </button>
      </div>
    )
  }

  return (
    <div className="flex h-[calc(100vh-73px)]">
      {/* Chat panel */}
      <div className="flex-1 flex flex-col p-4 min-w-0">
        <div className="flex-1 bg-white rounded-2xl shadow-lg overflow-hidden flex flex-col">
          {sessionId ? (
            <ChatContainer sessionId={sessionId} />
          ) : (
            <div className="flex-1 flex items-center justify-center text-gray-500">
              <MessageCircle className="w-6 h-6 mr-2" />
              <span>Starting session...</span>
            </div>
          )}
        </div>
      </div>

      {/* Progress sidebar — hidden on small screens to preserve chat usability */}
      <aside className="hidden lg:flex flex-col w-72 p-4 pl-0">
        <div className="flex-1 bg-white rounded-2xl shadow-lg overflow-hidden">
          <MatterProgress collectedFields={collectedFields} />
        </div>
      </aside>
    </div>
  )
}
