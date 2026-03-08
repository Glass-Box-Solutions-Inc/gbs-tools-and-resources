// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
import { Settings } from 'lucide-react'
import { ApiKeySection } from './ApiKeySection'

export function SettingsPage() {
  return (
    <div className="page-container">
      <div className="flex items-center gap-3 mb-6">
        <div className="p-2 bg-teal-50 rounded-xl">
          <Settings className="w-5 h-5 text-teal-600" />
        </div>
        <div>
          <h2 className="page-title">Settings</h2>
          <p className="page-subtitle">Manage your API connection and preferences</p>
        </div>
      </div>

      <div className="max-w-2xl space-y-6">
        <ApiKeySection />
      </div>
    </div>
  )
}
