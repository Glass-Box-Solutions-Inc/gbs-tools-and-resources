// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
import { forwardRef, type InputHTMLAttributes } from 'react'

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string
  error?: string
  helperText?: string
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, error, helperText, className = '', ...props }, ref) => {
    return (
      <div className="space-y-1">
        {label && (
          <label className="block text-sm font-medium text-gray-700">{label}</label>
        )}
        <input
          ref={ref}
          className={`w-full px-3 py-2 bg-white border rounded-lg text-sm transition-colors focus:outline-none focus:ring-2 focus:ring-teal-500/20 focus:border-teal-500 ${
            error ? 'border-red-300 focus:border-red-500 focus:ring-red-500/20' : 'border-gray-200'
          } ${className}`}
          {...props}
        />
        {error && <p className="text-xs text-red-500">{error}</p>}
        {helperText && !error && <p className="text-xs text-gray-400">{helperText}</p>}
      </div>
    )
  }
)
Input.displayName = 'Input'
