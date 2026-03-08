// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
import { useState } from 'react'
import { Clock } from 'lucide-react'
import { Card, Button, Input } from '../../ui'
import { useBillTime } from '../../../hooks/useBilling'

export function BillTimeForm() {
  const billTime = useBillTime()
  const [form, setForm] = useState({
    case_search: '',
    hours: '',
    description: '',
    subject: '',
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.case_search || !form.hours || !form.description) return
    billTime.mutate(
      {
        case_search: form.case_search,
        hours: parseFloat(form.hours),
        description: form.description,
        subject: form.subject || undefined,
      },
      {
        onSuccess: (res) => {
          if (res.success) setForm({ case_search: '', hours: '', description: '', subject: '' })
        },
      },
    )
  }

  const updateField = (field: string, value: string) =>
    setForm((prev) => ({ ...prev, [field]: value }))

  return (
    <Card padding="lg">
      <div className="flex items-center gap-2 mb-4">
        <Clock className="w-5 h-5 text-teal-600" />
        <h3 className="text-lg font-semibold text-gray-900">Bill Time</h3>
      </div>
      <form onSubmit={handleSubmit} className="space-y-3">
        <Input
          label="Case (file number or party name)"
          value={form.case_search}
          onChange={(e) => updateField('case_search', e.target.value)}
          placeholder="e.g. WC-2024-001 or John Doe"
          required
        />
        <div className="grid grid-cols-2 gap-3">
          <Input
            label="Hours"
            type="number"
            step="0.1"
            min="0.1"
            value={form.hours}
            onChange={(e) => updateField('hours', e.target.value)}
            placeholder="0.5"
            required
          />
          <Input
            label="Subject (optional)"
            value={form.subject}
            onChange={(e) => updateField('subject', e.target.value)}
            placeholder="e.g. Initial Review"
          />
        </div>
        <Input
          label="Description"
          value={form.description}
          onChange={(e) => updateField('description', e.target.value)}
          placeholder="Describe the work performed"
          required
        />
        <Button type="submit" loading={billTime.isPending} className="w-full">
          Bill Time
        </Button>
      </form>
    </Card>
  )
}
