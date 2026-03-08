// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
import { Clock } from 'lucide-react'
import { Card, Badge, LoadingSpinner } from '../../ui'
import { useCaseList } from '../../../hooks/useCases'
import { navigate } from '../../../router'

export function RecentActivity() {
  const { data, isLoading } = useCaseList({ limit: 10 })

  return (
    <Card padding="none">
      <div className="px-5 py-4 border-b border-gray-100">
        <h3 className="text-sm font-medium text-gray-900">Recent Cases</h3>
      </div>
      {isLoading ? (
        <LoadingSpinner size="sm" />
      ) : !data?.cases?.length ? (
        <p className="p-5 text-sm text-gray-400 text-center">No recent cases</p>
      ) : (
        <div className="divide-y divide-gray-100">
          {data.cases.slice(0, 8).map((c) => (
            <button
              key={c.id}
              onClick={() => navigate(`/cases/${c.id}`)}
              className="flex items-center gap-3 px-5 py-3 w-full text-left hover:bg-gray-50 transition-colors"
            >
              <Clock className="w-4 h-4 text-gray-400 flex-shrink-0" />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-gray-900 truncate">{c.primary_party_name}</p>
                <p className="text-xs text-gray-500">{c.file_number}</p>
              </div>
              <Badge variant={c.case_status?.toLowerCase() === 'active' ? 'success' : 'default'} dot>
                {c.case_status || 'Unknown'}
              </Badge>
            </button>
          ))}
        </div>
      )}
    </Card>
  )
}
