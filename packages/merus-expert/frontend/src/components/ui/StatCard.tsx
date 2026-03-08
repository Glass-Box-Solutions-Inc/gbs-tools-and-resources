// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
import { TrendingUp, TrendingDown } from 'lucide-react'
import type { ReactNode } from 'react'

interface StatCardProps {
  icon: ReactNode
  label: string
  value: string | number
  trend?: { value: number; label: string }
  className?: string
}

export function StatCard({ icon, label, value, trend, className = '' }: StatCardProps) {
  return (
    <div className={`bg-white border border-gray-200 rounded-2xl p-5 shadow-sm ${className}`}>
      <div className="flex items-start justify-between">
        <div className="p-2 bg-teal-50 rounded-xl">{icon}</div>
        {trend && (
          <div className={`flex items-center gap-1 text-xs font-medium ${trend.value >= 0 ? 'text-green-600' : 'text-red-600'}`}>
            {trend.value >= 0 ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
            {Math.abs(trend.value)}%
          </div>
        )}
      </div>
      <div className="mt-3">
        <p className="text-2xl font-semibold text-gray-900">{value}</p>
        <p className="text-sm text-gray-500 mt-0.5">{label}</p>
      </div>
      {trend && <p className="text-xs text-gray-400 mt-1">{trend.label}</p>}
    </div>
  )
}
