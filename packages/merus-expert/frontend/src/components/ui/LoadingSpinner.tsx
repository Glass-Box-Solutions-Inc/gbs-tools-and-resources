// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
import { Loader2 } from 'lucide-react'

interface LoadingSpinnerProps {
  text?: string
  className?: string
  size?: 'sm' | 'md' | 'lg'
}

const sizeStyles = {
  sm: 'w-4 h-4',
  md: 'w-8 h-8',
  lg: 'w-12 h-12',
}

export function LoadingSpinner({ text, className = '', size = 'md' }: LoadingSpinnerProps) {
  return (
    <div className={`flex flex-col items-center justify-center py-8 ${className}`}>
      <Loader2 className={`${sizeStyles[size]} text-teal-500 animate-spin`} />
      {text && <p className="mt-3 text-sm text-gray-500">{text}</p>}
    </div>
  )
}
