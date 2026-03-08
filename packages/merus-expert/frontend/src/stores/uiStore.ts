// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
import { create } from 'zustand'

interface Toast {
  id: string
  type: 'success' | 'error' | 'info'
  message: string
}

interface UIStore {
  toasts: Toast[]
  modalOpen: string | null
  addToast: (type: Toast['type'], message: string) => void
  removeToast: (id: string) => void
  openModal: (modalId: string) => void
  closeModal: () => void
}

export const useUIStore = create<UIStore>((set) => ({
  toasts: [],
  modalOpen: null,

  addToast: (type, message) => {
    const id = Date.now().toString(36) + Math.random().toString(36).slice(2)
    set((state) => ({ toasts: [...state.toasts, { id, type, message }] }))
    // Auto-remove after 4 seconds
    setTimeout(() => {
      set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) }))
    }, 4000)
  },

  removeToast: (id) => set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) })),

  openModal: (modalId) => set({ modalOpen: modalId }),

  closeModal: () => set({ modalOpen: null }),
}))
