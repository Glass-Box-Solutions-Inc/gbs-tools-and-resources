// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
import { useState } from 'react'
import { Eye, EyeOff, CheckCircle, XCircle } from 'lucide-react'
import { Card, Button, Input } from '../../ui'
import { useSettingsStore } from '../../../stores/settingsStore'
import { useUIStore } from '../../../stores/uiStore'

export function ApiKeySection() {
  const { apiKey, setApiKey } = useSettingsStore()
  const addToast = useUIStore((s) => s.addToast)
  const [inputValue, setInputValue] = useState(apiKey)
  const [showKey, setShowKey] = useState(false)
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<'success' | 'error' | null>(null)

  const handleSave = () => {
    setApiKey(inputValue.trim())
    addToast('success', 'API key saved')
    setTestResult(null)
  }

  const handleTest = async () => {
    setTesting(true)
    setTestResult(null)
    try {
      const res = await fetch('/api/reference/billing-codes', {
        headers: { 'X-API-Key': inputValue.trim() },
      })
      if (res.ok) {
        setTestResult('success')
        addToast('success', 'Connection successful!')
      } else {
        setTestResult('error')
        addToast('error', `Connection failed: HTTP ${res.status}`)
      }
    } catch {
      // Network-level failure — key may still be syntactically valid
      setTestResult('error')
      addToast('error', 'Connection failed: Network error')
    } finally {
      setTesting(false)
    }
  }

  return (
    <Card padding="lg">
      <h3 className="text-lg font-semibold text-gray-900 mb-1">MerusCase API Key</h3>
      <p className="text-sm text-gray-500 mb-4">
        Your API key is stored locally in your browser and never sent to our servers.
      </p>

      <div className="space-y-3">
        <div className="relative">
          <Input
            type={showKey ? 'text' : 'password'}
            value={inputValue}
            onChange={(e) => {
              setInputValue(e.target.value)
              setTestResult(null)
            }}
            placeholder="Enter your MerusCase API key"
          />
          <button
            onClick={() => setShowKey(!showKey)}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
            type="button"
            aria-label={showKey ? 'Hide API key' : 'Show API key'}
          >
            {showKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
          </button>
        </div>

        <div className="flex gap-2">
          <Button onClick={handleSave} disabled={!inputValue.trim()}>
            Save Key
          </Button>
          <Button
            variant="secondary"
            onClick={handleTest}
            loading={testing}
            disabled={!inputValue.trim()}
          >
            Test Connection
          </Button>
        </div>

        {testResult === 'success' && (
          <div className="flex items-center gap-2 text-green-600 text-sm">
            <CheckCircle className="w-4 h-4" />
            <span>Connected to MerusCase successfully</span>
          </div>
        )}
        {testResult === 'error' && (
          <div className="flex items-center gap-2 text-red-500 text-sm">
            <XCircle className="w-4 h-4" />
            <span>Connection failed. Check your API key.</span>
          </div>
        )}
      </div>
    </Card>
  )
}
