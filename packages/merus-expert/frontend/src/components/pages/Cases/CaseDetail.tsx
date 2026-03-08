// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
import { useState } from 'react'
import { ArrowLeft } from 'lucide-react'
import { Card, Badge, Tabs, LoadingSpinner, Button } from '../../ui'
import { useCaseDetail } from '../../../hooks/useCases'
import { CaseBillingTab, CaseActivitiesTab, CasePartiesTab } from './CaseDetailTabs'
import { navigate } from '../../../router'

const tabs = [
  { id: 'details', label: 'Details' },
  { id: 'billing', label: 'Billing' },
  { id: 'activities', label: 'Activities' },
  { id: 'parties', label: 'Parties' },
]

export function CaseDetail({ caseId }: { caseId: string }) {
  const [activeTab, setActiveTab] = useState('details')
  const { data, isLoading, error } = useCaseDetail(caseId)

  if (isLoading) {
    return (
      <div className="page-container">
        <LoadingSpinner text="Loading case..." />
      </div>
    )
  }

  if (error) {
    return (
      <div className="page-container text-red-500">
        Failed to load case: {error.message}
      </div>
    )
  }

  if (!data) {
    return <div className="page-container text-gray-500">Case not found</div>
  }

  return (
    <div className="page-container">
      <Button variant="ghost" onClick={() => navigate('/cases')} className="mb-4">
        <ArrowLeft className="w-4 h-4" /> Back to Cases
      </Button>

      <Card padding="lg" className="mb-4">
        <div className="flex items-start justify-between">
          <div>
            <h2 className="text-xl font-semibold text-gray-900">{data.primary_party_name}</h2>
            <p className="text-sm text-gray-500 mt-1">File #{data.file_number}</p>
          </div>
          <Badge variant={data.case_status?.toLowerCase() === 'active' ? 'success' : 'default'} dot>
            {data.case_status}
          </Badge>
        </div>
        <div className="mt-3 flex gap-4 text-sm text-gray-500">
          <span>Type: <strong className="text-gray-700">{data.case_type}</strong></span>
          <span>ID: <strong className="text-gray-700">{data.id}</strong></span>
        </div>
      </Card>

      <Tabs tabs={tabs} activeTab={activeTab} onChange={setActiveTab} className="mb-4" />

      {activeTab === 'details' && (
        <Card>
          <h3 className="text-sm font-medium text-gray-900 mb-3">Case Data</h3>
          <pre className="text-xs bg-gray-50 p-4 rounded-xl overflow-x-auto text-gray-600 max-h-96">
            {JSON.stringify(data.data, null, 2)}
          </pre>
        </Card>
      )}
      {activeTab === 'billing' && <CaseBillingTab caseId={caseId} />}
      {activeTab === 'activities' && <CaseActivitiesTab caseId={caseId} />}
      {activeTab === 'parties' && <CasePartiesTab caseId={caseId} />}
    </div>
  )
}
