// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
import type { ReactNode } from 'react'
import { navigate } from '../../router'

interface NavItemProps {
  path: string
  label: string
  icon: ReactNode
  active: boolean
  collapsed: boolean
}

export function NavItem({ path, label, icon, active, collapsed }: NavItemProps) {
  return (
    <button
      onClick={() => navigate(path)}
      className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all ${
        active
          ? 'bg-teal-500/20 text-teal-300'
          : 'text-gray-400 hover:text-white hover:bg-white/5'
      }`}
      title={collapsed ? label : undefined}
    >
      <span className="flex-shrink-0">{icon}</span>
      {!collapsed && <span>{label}</span>}
    </button>
  )
}
