// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
import { create } from 'zustand'
import type { Message } from '../lib/types'

interface ChatStore {
  sessionId: string | null
  messages: Message[]
  conversationState: string
  isComplete: boolean
  action: string | null
  loading: boolean
  error: string | null
  quickChips: string[]
  collectedFields: Record<string, unknown>

  // Actions
  setSession: (sessionId: string) => void
  addMessage: (message: Message) => void
  setMessages: (messages: Message[]) => void
  updateState: (state: string, isComplete: boolean, action?: string) => void
  setLoading: (loading: boolean) => void
  setError: (error: string | null) => void
  setQuickChips: (chips: string[]) => void
  setCollectedFields: (fields: Record<string, unknown>) => void
  reset: () => void
}

const initialState = {
  sessionId: null,
  messages: [],
  conversationState: 'greeting',
  isComplete: false,
  action: null,
  loading: false,
  error: null,
  quickChips: [],
  collectedFields: {},
}

export const useChatStore = create<ChatStore>((set) => ({
  ...initialState,

  setSession: (sessionId) => set({ sessionId }),

  addMessage: (message) =>
    set((state) => ({
      messages: [...state.messages, message],
    })),

  setMessages: (messages) => set({ messages }),

  updateState: (conversationState, isComplete, action) =>
    set({
      conversationState,
      isComplete,
      action: action || null,
    }),

  setLoading: (loading) => set({ loading }),

  setError: (error) => set({ error }),

  setQuickChips: (quickChips) => set({ quickChips }),

  setCollectedFields: (collectedFields) => set({ collectedFields }),

  reset: () => set(initialState),
}))
