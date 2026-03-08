// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
import { useState } from 'react'
import { DollarSign } from 'lucide-react'
import { Card, Button, Input, Select } from '../../ui'
import { useAddCost } from '../../../hooks/useBilling'

const ledgerTypes = [
  { value: 'cost', label: 'Cost' },
  { value: 'fee', label: 'Fee' },
  { value: 'expense', label: 'Expense' },
]

export function AddCostForm() {
  const addCost = useAddCost()
  const [form, setForm] = useState({
    case_search: '',
    amount: '',
    description: '',
    ledger_type: 'cost',
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.case_search || !form.amount || !form.description) return
    addCost.mutate(
      {
        case_search: form.case_search,
        amount: parseFloat(form.amount),
        description: form.description,
        ledger_type: form.ledger_type,
      },
      {
        onSuccess: (res) => {
          if (res.success)
            setForm({ case_search: '', amount: '', description: '', ledger_type: 'cost' })
        },
      },
    )
  }

  const updateField = (field: string, value: string) =>
    setForm((prev) => ({ ...prev, [field]: value }))

  return (
    <Card padding="lg">
      <div className="flex items-center gap-2 mb-4">
        <DollarSign className="w-5 h-5 text-teal-600" />
        <h3 className="text-lg font-semibold text-gray-900">Add Cost</h3>
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
            label="Amount ($)"
            type="number"
            step="0.01"
            min="0.01"
            value={form.amount}
            onChange={(e) => updateField('amount', e.target.value)}
            placeholder="25.00"
            required
          />
          <Select
            label="Type"
            options={ledgerTypes}
            value={form.ledger_type}
            onChange={(e) => updateField('ledger_type', e.target.value)}
          />
        </div>
        <Input
          label="Description"
          value={form.description}
          onChange={(e) => updateField('description', e.target.value)}
          placeholder="e.g. WCAB Filing Fee"
          required
        />
        <Button type="submit" loading={addCost.isPending} className="w-full">
          Add Cost
        </Button>
      </form>
    </Card>
  )
}
