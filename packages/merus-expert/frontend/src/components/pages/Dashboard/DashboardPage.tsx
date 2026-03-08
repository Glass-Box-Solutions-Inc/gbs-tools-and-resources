// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
import { LayoutDashboard, FolderSearch, FilePlus, Receipt, Bot, ClipboardList } from 'lucide-react'
import { StatCards } from './StatCards'
import { RecentActivity } from './RecentActivity'
import { Card } from '../../ui'
import { navigate } from '../../../router'
import { useSettingsStore } from '../../../stores/settingsStore'

const quickActions = [
  { label: 'Search Cases', icon: <FolderSearch className="w-5 h-5" />, path: '/cases' },
  { label: 'New Matter', icon: <FilePlus className="w-5 h-5" />, path: '/new-matter' },
  { label: 'Bill Time', icon: <Receipt className="w-5 h-5" />, path: '/billing' },
  { label: 'AI Assistant', icon: <Bot className="w-5 h-5" />, path: '/ai' },
  { label: 'Add Note', icon: <ClipboardList className="w-5 h-5" />, path: '/activities' },
]

export function DashboardPage() {
  const isConfigured = useSettingsStore((s) => s.isConfigured)()

  return (
    <div className="page-container">
      <div className="flex items-center gap-3 mb-6">
        <div className="p-2 bg-teal-50 rounded-xl">
          <LayoutDashboard className="w-5 h-5 text-teal-600" />
        </div>
        <div>
          <h2 className="page-title">Welcome back</h2>
          <p className="page-subtitle">Here&apos;s what&apos;s happening with your cases</p>
        </div>
      </div>

      {isConfigured && <StatCards />}

      {/* Quick Actions */}
      <div className="mt-6">
        <h3 className="text-sm font-medium text-gray-700 mb-3">Quick Actions</h3>
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
          {quickActions.map((action) => (
            <Card
              key={action.label}
              className="cursor-pointer hover:shadow-md hover:border-teal-200 transition-all"
              padding="sm"
            >
              <button
                onClick={() => navigate(action.path)}
                className="flex flex-col items-center gap-2 w-full py-2"
              >
                <div className="text-teal-600">{action.icon}</div>
                <span className="text-sm font-medium text-gray-700">{action.label}</span>
              </button>
            </Card>
          ))}
        </div>
      </div>

      {isConfigured && (
        <div className="mt-6">
          <RecentActivity />
        </div>
      )}

      {!isConfigured && (
        <Card className="mt-6 text-center" padding="lg">
          <p className="text-gray-500 mb-3">Connect your MerusCase API key to see dashboard stats and recent activity.</p>
          <button onClick={() => navigate('/settings')} className="btn-primary">Configure API Key</button>
        </Card>
      )}
    </div>
  )
}
