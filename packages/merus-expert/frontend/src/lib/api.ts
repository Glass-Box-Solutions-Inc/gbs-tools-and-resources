import type { SessionResponse, ChatResponse, MatterResponse } from './types'

const API_BASE = '/api'

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
    throw new Error(error.detail || `HTTP error ${response.status}`)
  }
  return response.json()
}

export const chatApi = {
  /**
   * Create a new chat session
   */
  async createSession(): Promise<SessionResponse> {
    const response = await fetch(`${API_BASE}/chat/session`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    })
    return handleResponse<SessionResponse>(response)
  },

  /**
   * Send a chat message
   */
  async sendMessage(sessionId: string, message: string): Promise<ChatResponse> {
    const response = await fetch(`${API_BASE}/chat/message`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: sessionId,
        message: message,
      }),
    })
    return handleResponse<ChatResponse>(response)
  },

  /**
   * Get chat history
   */
  async getHistory(sessionId: string): Promise<{
    session_id: string
    messages: Array<{ role: string; content: string; timestamp: string }>
    state: string
    collected_data: Record<string, unknown>
  }> {
    const response = await fetch(`${API_BASE}/chat/history/${sessionId}`)
    return handleResponse(response)
  },

  /**
   * Preview matter (dry-run)
   */
  async previewMatter(sessionId: string): Promise<MatterResponse> {
    const response = await fetch(`${API_BASE}/matter/preview`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: sessionId,
        dry_run: true,
      }),
    })
    return handleResponse<MatterResponse>(response)
  },

  /**
   * Submit matter to MerusCase
   */
  async submitMatter(sessionId: string): Promise<MatterResponse> {
    const response = await fetch(`${API_BASE}/matter/submit`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: sessionId,
        dry_run: false,
      }),
    })
    return handleResponse<MatterResponse>(response)
  },

  /**
   * Get collected data for session
   */
  async getCollectedData(sessionId: string): Promise<{
    session_id: string
    state: string
    collected_data: Record<string, unknown>
    matter_details: Record<string, unknown> | null
  }> {
    const response = await fetch(`${API_BASE}/matter/collected/${sessionId}`)
    return handleResponse(response)
  },
}
