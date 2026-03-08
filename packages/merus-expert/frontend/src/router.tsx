// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
import { useEffect, type ReactNode } from 'react'
import { useNavigationStore } from './stores/navigationStore'

// Route definitions
export type Route =
  | '/dashboard'
  | '/ai'
  | '/cases'
  | '/new-matter'
  | '/billing'
  | '/activities'
  | '/settings'

interface RouteConfig {
  path: Route | string
  pattern?: RegExp
}

const routes: RouteConfig[] = [
  { path: '/dashboard' },
  { path: '/ai' },
  { path: '/cases', pattern: /^\/cases(\/\d+)?$/ },
  { path: '/new-matter' },
  { path: '/billing' },
  { path: '/activities' },
  { path: '/settings' },
]

export function matchRoute(pathname: string): { route: string; params: Record<string, string> } {
  // Check for case detail: /cases/:id
  const caseMatch = pathname.match(/^\/cases\/(\d+)$/)
  if (caseMatch) {
    return { route: '/cases/:id', params: { id: caseMatch[1] } }
  }

  // Check exact matches
  for (const r of routes) {
    if (r.path === pathname) {
      return { route: r.path, params: {} }
    }
  }

  // Default to dashboard
  return { route: '/dashboard', params: {} }
}

export function navigate(path: string) {
  window.history.pushState({}, '', path)
  useNavigationStore.getState().setRoute(path)
}

export function useRouter() {
  const { currentRoute, params, setRoute } = useNavigationStore()

  useEffect(() => {
    const handlePopState = () => {
      setRoute(window.location.pathname)
    }

    window.addEventListener('popstate', handlePopState)
    return () => window.removeEventListener('popstate', handlePopState)
  }, [setRoute])

  return { currentRoute, params, navigate }
}

export function Link({ to, children, className }: { to: string; children: ReactNode; className?: string }) {
  const handleClick = (e: React.MouseEvent) => {
    e.preventDefault()
    navigate(to)
  }

  return (
    <a href={to} onClick={handleClick} className={className}>
      {children}
    </a>
  )
}
