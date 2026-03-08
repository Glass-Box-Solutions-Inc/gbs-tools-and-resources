// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
import { useState } from 'react'
import { Key } from 'lucide-react'
import { SearchBar } from './SearchBar'
import { CaseList } from './CaseList'
import { Card, Button, LoadingSpinner } from '../../ui'
import { useCaseList } from '../../../hooks/useCases'
import { useSettingsStore } from '../../../stores/settingsStore'
import { navigate } from '../../../router'

export function CasesPage() {
  const isConfigured = useSettingsStore((s) => s.isConfigured)()
  const [searchQuery, setSearchQuery] = useState('')
  const { data, isLoading, error } = useCaseList(
    searchQuery ? { status: searchQuery } : { limit: 100 }
  )

  if (!isConfigured) {
    return (
      <div className="page-container">
        <Card className="max-w-md mx-auto mt-12 text-center">
          <div className="p-2 bg-amber-50 rounded-full w-12 h-12 flex items-center justify-center mx-auto mb-4">
            <Key className="w-6 h-6 text-amber-500" />
          </div>
          <h3 className="text-lg font-semibold text-gray-900 mb-2">API Key Required</h3>
          <p className="text-sm text-gray-500 mb-4">Configure your MerusCase API key to search cases.</p>
          <Button onClick={() => navigate('/settings')}>Go to Settings</Button>
        </Card>
      </div>
    )
  }

  return (
    <div className="page-container">
      <SearchBar onSearch={setSearchQuery} />
      <div className="mt-4">
        {isLoading ? (
          <LoadingSpinner text="Loading cases..." />
        ) : error ? (
          <Card className="text-center text-red-500 py-8">
            <p>Failed to load cases: {error.message}</p>
          </Card>
        ) : (
          <>
            {data?.count !== undefined && (
              <p className="text-sm text-gray-500 mb-3">{data.count} cases found</p>
            )}
            <CaseList cases={data?.cases ?? []} />
          </>
        )}
      </div>
    </div>
  )
}
