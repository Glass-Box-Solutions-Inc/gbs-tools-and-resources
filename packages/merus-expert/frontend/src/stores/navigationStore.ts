// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
import { create } from 'zustand'
import { matchRoute } from '../router'

interface NavigationStore {
  currentRoute: string
  params: Record<string, string>
  sidebarCollapsed: boolean
  setRoute: (pathname: string) => void
  toggleSidebar: () => void
  setSidebarCollapsed: (collapsed: boolean) => void
}

export const useNavigationStore = create<NavigationStore>((set) => ({
  currentRoute: matchRoute(window.location.pathname).route,
  params: matchRoute(window.location.pathname).params,
  sidebarCollapsed: false,

  setRoute: (pathname: string) => {
    const { route, params } = matchRoute(pathname)
    set({ currentRoute: route, params })
  },

  toggleSidebar: () => set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),

  setSidebarCollapsed: (collapsed: boolean) => set({ sidebarCollapsed: collapsed }),
}))
