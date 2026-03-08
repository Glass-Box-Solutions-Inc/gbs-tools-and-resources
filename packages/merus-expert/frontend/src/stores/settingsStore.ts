// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
import { create } from 'zustand'

const STORAGE_KEY = 'merus-expert-settings'

interface Settings {
  apiKey: string
  apiBaseUrl: string
}

interface SettingsStore extends Settings {
  setApiKey: (key: string) => void
  setApiBaseUrl: (url: string) => void
  isConfigured: () => boolean
  clearSettings: () => void
}

function loadSettings(): Settings {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored) {
      return JSON.parse(stored)
    }
  } catch {
    // Ignore parse errors
  }
  return { apiKey: '', apiBaseUrl: '' }
}

function saveSettings(settings: Settings) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(settings))
}

export const useSettingsStore = create<SettingsStore>((set, get) => ({
  ...loadSettings(),

  setApiKey: (apiKey: string) => {
    set({ apiKey })
    saveSettings({ apiKey, apiBaseUrl: get().apiBaseUrl })
  },

  setApiBaseUrl: (apiBaseUrl: string) => {
    set({ apiBaseUrl })
    saveSettings({ apiKey: get().apiKey, apiBaseUrl })
  },

  isConfigured: () => get().apiKey.length > 0,

  clearSettings: () => {
    set({ apiKey: '', apiBaseUrl: '' })
    localStorage.removeItem(STORAGE_KEY)
  },
}))
