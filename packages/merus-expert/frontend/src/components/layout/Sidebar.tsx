// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
import {
  LayoutDashboard, Bot, FolderSearch, FilePlus,
  Receipt, ClipboardList, Settings, ChevronLeft,
  ChevronRight, Scale,
} from 'lucide-react'
import { useNavigationStore } from '../../stores/navigationStore'
import { NavItem } from './NavItem'

const navItems = [
  { path: '/dashboard', label: 'Dashboard', icon: <LayoutDashboard className="w-5 h-5" /> },
  { path: '/ai', label: 'AI Assistant', icon: <Bot className="w-5 h-5" /> },
  { path: '/cases', label: 'Cases', icon: <FolderSearch className="w-5 h-5" /> },
  { path: '/new-matter', label: 'New Matter', icon: <FilePlus className="w-5 h-5" /> },
  { path: '/billing', label: 'Billing', icon: <Receipt className="w-5 h-5" /> },
  { path: '/activities', label: 'Activities', icon: <ClipboardList className="w-5 h-5" /> },
]

const bottomItems = [
  { path: '/settings', label: 'Settings', icon: <Settings className="w-5 h-5" /> },
]

export function Sidebar() {
  const { currentRoute, sidebarCollapsed, toggleSidebar } = useNavigationStore()

  const isActive = (path: string) => {
    if (path === '/cases') return currentRoute === '/cases' || currentRoute === '/cases/:id'
    return currentRoute === path
  }

  return (
    <aside
      className={`bg-navy-800 flex flex-col h-screen sticky top-0 transition-all duration-300 ${
        sidebarCollapsed ? 'w-16' : 'w-60'
      }`}
    >
      {/* Logo */}
      <div className="flex items-center gap-3 px-4 py-5 border-b border-white/10">
        <div className="p-1.5 bg-teal-500/20 rounded-lg flex-shrink-0">
          <Scale className="w-5 h-5 text-teal-400" />
        </div>
        {!sidebarCollapsed && (
          <div>
            <h1 className="text-sm font-semibold text-white">Merus Expert</h1>
            <p className="text-[11px] text-gray-500">MerusCase Platform</p>
          </div>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-2 py-3 space-y-1 overflow-y-auto scrollbar-thin">
        {navItems.map((item) => (
          <NavItem
            key={item.path}
            {...item}
            active={isActive(item.path)}
            collapsed={sidebarCollapsed}
          />
        ))}
      </nav>

      {/* Bottom section */}
      <div className="px-2 py-3 border-t border-white/10 space-y-1">
        {bottomItems.map((item) => (
          <NavItem
            key={item.path}
            {...item}
            active={isActive(item.path)}
            collapsed={sidebarCollapsed}
          />
        ))}
        <button
          onClick={toggleSidebar}
          className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm text-gray-500 hover:text-white hover:bg-white/5 transition-colors"
          title={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {sidebarCollapsed ? (
            <ChevronRight className="w-5 h-5" />
          ) : (
            <>
              <ChevronLeft className="w-5 h-5" />
              <span>Collapse</span>
            </>
          )}
        </button>
      </div>
    </aside>
  )
}
