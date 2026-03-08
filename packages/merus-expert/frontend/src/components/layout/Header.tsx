// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
import { useNavigationStore } from '../../stores/navigationStore'

const pageTitles: Record<string, { title: string; subtitle: string }> = {
  '/dashboard': { title: 'Dashboard', subtitle: 'Overview of your MerusCase activity' },
  '/ai': { title: 'AI Assistant', subtitle: 'Chat with your MerusCase AI agent' },
  '/cases': { title: 'Cases', subtitle: 'Search and manage case files' },
  '/cases/:id': { title: 'Case Detail', subtitle: 'View case information' },
  '/new-matter': { title: 'New Matter', subtitle: 'Create a new matter in MerusCase' },
  '/billing': { title: 'Billing', subtitle: 'Bill time and add costs' },
  '/activities': { title: 'Activities', subtitle: 'Add notes and view activity types' },
  '/settings': { title: 'Settings', subtitle: 'Configure your API connection' },
}

export function Header() {
  const { currentRoute } = useNavigationStore()
  const page = pageTitles[currentRoute] || pageTitles['/dashboard']

  return (
    <header className="border-b border-gray-200 bg-white/60 backdrop-blur-sm px-6 py-4">
      <h1 className="text-xl font-semibold text-gray-900">{page.title}</h1>
      <p className="text-sm text-gray-500 mt-0.5">{page.subtitle}</p>
    </header>
  )
}
