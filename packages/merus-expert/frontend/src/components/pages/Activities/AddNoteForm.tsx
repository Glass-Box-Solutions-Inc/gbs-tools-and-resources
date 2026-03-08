// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
import { useState } from 'react'
import { StickyNote } from 'lucide-react'
import { Card, Button, Input } from '../../ui'
import { useAddNote } from '../../../hooks/useActivities'

export function AddNoteForm() {
  const addNote = useAddNote()
  const [form, setForm] = useState({
    case_search: '',
    subject: '',
    description: '',
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.case_search || !form.subject) return
    addNote.mutate(
      {
        case_search: form.case_search,
        subject: form.subject,
        description: form.description || undefined,
      },
      {
        onSuccess: (res) => {
          if (res.success) setForm({ case_search: '', subject: '', description: '' })
        },
      },
    )
  }

  const updateField = (field: string, value: string) =>
    setForm((prev) => ({ ...prev, [field]: value }))

  return (
    <Card padding="lg" className="max-w-xl">
      <div className="flex items-center gap-2 mb-4">
        <StickyNote className="w-5 h-5 text-teal-600" />
        <h3 className="text-lg font-semibold text-gray-900">Add Note</h3>
      </div>
      <form onSubmit={handleSubmit} className="space-y-3">
        <Input
          label="Case (file number or party name)"
          value={form.case_search}
          onChange={(e) => updateField('case_search', e.target.value)}
          placeholder="e.g. WC-2024-001 or John Doe"
          required
        />
        <Input
          label="Subject"
          value={form.subject}
          onChange={(e) => updateField('subject', e.target.value)}
          placeholder="e.g. Follow-up needed"
          required
        />
        <Input
          label="Description (optional)"
          value={form.description}
          onChange={(e) => updateField('description', e.target.value)}
          placeholder="Additional details..."
        />
        <Button type="submit" loading={addNote.isPending} className="w-full">
          Add Note
        </Button>
      </form>
    </Card>
  )
}
