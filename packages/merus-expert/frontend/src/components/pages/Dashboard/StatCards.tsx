// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
import { FolderOpen, Clock, DollarSign, Users } from 'lucide-react'
import { StatCard, LoadingSpinner } from '../../ui'
import { useCaseList } from '../../../hooks/useCases'

export function StatCards() {
  const { data, isLoading } = useCaseList({ limit: 500 })

  if (isLoading) return <LoadingSpinner size="sm" />

  const totalCases = data?.count ?? 0
  // Derive active count from the returned cases slice — a dedicated analytics endpoint would give exact totals
  const activeCases = data?.cases?.filter((c) => c.case_status?.toLowerCase() === 'active').length ?? 0

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
      <StatCard
        icon={<FolderOpen className="w-5 h-5 text-teal-600" />}
        label="Total Cases"
        value={totalCases}
      />
      <StatCard
        icon={<Clock className="w-5 h-5 text-teal-600" />}
        label="Active Cases"
        value={activeCases}
      />
      <StatCard
        icon={<DollarSign className="w-5 h-5 text-teal-600" />}
        label="This Month"
        value="--"
      />
      <StatCard
        icon={<Users className="w-5 h-5 text-teal-600" />}
        label="Total Parties"
        value="--"
      />
    </div>
  )
}
