// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
import { forwardRef, type SelectHTMLAttributes } from 'react'

interface SelectOption {
  value: string
  label: string
}

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label?: string
  error?: string
  options: SelectOption[]
  placeholder?: string
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(
  ({ label, error, options, placeholder, className = '', ...props }, ref) => {
    return (
      <div className="space-y-1">
        {label && (
          <label className="block text-sm font-medium text-gray-700">{label}</label>
        )}
        <select
          ref={ref}
          className={`w-full px-3 py-2 bg-white border rounded-lg text-sm transition-colors focus:outline-none focus:ring-2 focus:ring-teal-500/20 focus:border-teal-500 ${
            error ? 'border-red-300 focus:border-red-500 focus:ring-red-500/20' : 'border-gray-200'
          } ${className}`}
          {...props}
        >
          {placeholder && <option value="">{placeholder}</option>}
          {options.map((opt) => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
        {error && <p className="text-xs text-red-500">{error}</p>}
      </div>
    )
  }
)
Select.displayName = 'Select'
