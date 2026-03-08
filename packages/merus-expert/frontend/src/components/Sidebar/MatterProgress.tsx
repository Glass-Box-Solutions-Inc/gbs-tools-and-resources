// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology

const FIELD_LABELS: Record<string, string> = {
  primary_party: 'Client Name',
  case_type: 'Case Type',
  attorney_responsible: 'Attorney',
  office: 'Office',
  venue_based_upon: 'Venue',
  client_email: 'Email',
  client_phone: 'Phone',
  has_billing: 'Billing',
  billing_amount_due: 'Amount Due',
  billing_description: 'Billing Desc.',
  initial_note: 'Initial Note',
}

const FIELD_ORDER = [
  'primary_party',
  'case_type',
  'attorney_responsible',
  'office',
  'venue_based_upon',
  'client_email',
  'client_phone',
  'has_billing',
  'billing_amount_due',
  'billing_description',
  'initial_note',
]

interface MatterProgressProps {
  collectedFields: Record<string, unknown>
}

/**
 * Sidebar component showing a live checklist of collected matter fields.
 * Updates in real-time as the user answers questions in chat.
 */
export function MatterProgress({ collectedFields }: MatterProgressProps) {
  const total = FIELD_ORDER.length
  const collected = FIELD_ORDER.filter((f) => collectedFields[f] !== undefined && collectedFields[f] !== null).length
  const pct = Math.round((collected / total) * 100)

  return (
    <div className="p-4 h-full flex flex-col">
      <h3 className="text-sm font-semibold text-gray-700 mb-1">Matter Progress</h3>
      <p className="text-xs text-gray-400 mb-3">{collected} of {total} fields collected</p>

      {/* Progress bar */}
      <div className="w-full bg-gray-100 rounded-full h-1.5 mb-4">
        <div
          className="bg-teal-500 h-1.5 rounded-full transition-all duration-500"
          style={{ width: `${pct}%` }}
        />
      </div>

      <div className="space-y-2 flex-1 overflow-y-auto">
        {FIELD_ORDER.map((field) => {
          const value = collectedFields[field]
          const hasValue = value !== undefined && value !== null && value !== false
          const displayValue = hasValue ? formatFieldValue(field, value) : null

          return (
            <div key={field} className="flex items-start gap-2 text-sm">
              <span
                className={`mt-0.5 flex-shrink-0 text-base leading-none ${
                  hasValue ? 'text-green-500' : 'text-gray-300'
                }`}
                aria-hidden="true"
              >
                {hasValue ? '✓' : '○'}
              </span>
              <div className="flex-1 min-w-0">
                <span className={`font-medium ${hasValue ? 'text-gray-700' : 'text-gray-400'}`}>
                  {FIELD_LABELS[field]}
                </span>
                {displayValue && (
                  <div className="text-gray-500 text-xs truncate mt-0.5" title={displayValue}>
                    {displayValue}
                  </div>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function formatFieldValue(field: string, value: unknown): string {
  if (field === 'has_billing') {
    return value ? 'Yes' : 'No'
  }
  if (field === 'billing_amount_due' && typeof value === 'number') {
    return `$${value.toLocaleString('en-US', { minimumFractionDigits: 2 })}`
  }
  return String(value)
}
