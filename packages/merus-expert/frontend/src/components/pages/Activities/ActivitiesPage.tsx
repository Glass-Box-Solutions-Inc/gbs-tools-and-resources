// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
import { ClipboardList, Key } from 'lucide-react'
import { Card, Button } from '../../ui'
import { AddNoteForm } from './AddNoteForm'
import { ActivityTypesTable } from './ActivityTypesTable'
import { useSettingsStore } from '../../../stores/settingsStore'
import { navigate } from '../../../router'

export function ActivitiesPage() {
  // isConfigured is a getter function on the store — call it to derive the boolean
  const isConfigured = useSettingsStore((s) => s.isConfigured)()

  if (!isConfigured) {
    return (
      <div className="page-container">
        <Card className="max-w-md mx-auto mt-12 text-center">
          <div className="p-2 bg-amber-50 rounded-full w-12 h-12 flex items-center justify-center mx-auto mb-4">
            <Key className="w-6 h-6 text-amber-500" />
          </div>
          <h3 className="text-lg font-semibold text-gray-900 mb-2">API Key Required</h3>
          <p className="text-sm text-gray-500 mb-4">
            Configure your MerusCase API key to manage activities.
          </p>
          <Button onClick={() => navigate('/settings')}>Go to Settings</Button>
        </Card>
      </div>
    )
  }

  return (
    <div className="page-container">
      <div className="flex items-center gap-3 mb-6">
        <div className="p-2 bg-teal-50 rounded-xl">
          <ClipboardList className="w-5 h-5 text-teal-600" />
        </div>
        <div>
          <h2 className="page-title">Activities</h2>
          <p className="page-subtitle">Add notes and manage activity types</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <AddNoteForm />
        {/* Right column reserved for future activity-related widgets */}
        <div />
      </div>

      <div className="mt-6">
        <ActivityTypesTable />
      </div>
    </div>
  )
}
