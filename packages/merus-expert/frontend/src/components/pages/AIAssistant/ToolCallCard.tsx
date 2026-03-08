// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
import { useState } from 'react'
import { Wrench, ChevronDown, ChevronRight, CheckCircle, XCircle } from 'lucide-react'
import type { AgentStreamEvent } from '../../../lib/types'

interface ToolCallCardProps {
  toolCall: Extract<AgentStreamEvent, { type: 'tool_call' }>
  toolResult?: Extract<AgentStreamEvent, { type: 'tool_result' }>
}

export function ToolCallCard({ toolCall, toolResult }: ToolCallCardProps) {
  const [expanded, setExpanded] = useState(false)
  // A result is an error if its result object contains an "error" key
  const hasError = toolResult?.result?.error

  return (
    <div className="border border-gray-200 rounded-xl overflow-hidden bg-gray-50">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-gray-100 transition-colors"
      >
        <Wrench className="w-4 h-4 text-gray-500 flex-shrink-0" />
        <span className="text-sm font-medium text-gray-700 flex-1">{toolCall.name}</span>

        {/* Status indicator: pending pulse, success check, error cross */}
        {toolResult ? (
          hasError ? (
            <XCircle className="w-4 h-4 text-red-400" />
          ) : (
            <CheckCircle className="w-4 h-4 text-green-400" />
          )
        ) : (
          <span className="w-3 h-3 rounded-full bg-amber-400 animate-pulse" />
        )}

        {expanded ? (
          <ChevronDown className="w-4 h-4 text-gray-400" />
        ) : (
          <ChevronRight className="w-4 h-4 text-gray-400" />
        )}
      </button>

      {expanded && (
        <div className="px-3 pb-3 space-y-2">
          <div>
            <p className="text-xs font-medium text-gray-500 mb-1">Input</p>
            <pre className="text-xs bg-white p-2 rounded-lg border border-gray-200 overflow-x-auto max-h-40">
              {JSON.stringify(toolCall.input, null, 2)}
            </pre>
          </div>
          {toolResult && (
            <div>
              <p className="text-xs font-medium text-gray-500 mb-1">Result</p>
              <pre
                className={`text-xs p-2 rounded-lg border overflow-x-auto max-h-40 ${
                  hasError ? 'bg-red-50 border-red-200' : 'bg-white border-gray-200'
                }`}
              >
                {JSON.stringify(toolResult.result, null, 2)}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
