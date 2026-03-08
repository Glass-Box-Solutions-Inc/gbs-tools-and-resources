// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
import type { ReactNode } from 'react'

interface CardProps {
  children: ReactNode
  className?: string
  glass?: boolean
  padding?: 'none' | 'sm' | 'md' | 'lg'
}

interface CardHeaderProps {
  children: ReactNode
  className?: string
}

interface CardFooterProps {
  children: ReactNode
  className?: string
}

const paddingMap = {
  none: '',
  sm: 'p-3',
  md: 'p-5',
  lg: 'p-6',
}

export function Card({ children, className = '', glass = false, padding = 'md' }: CardProps) {
  const base = glass
    ? 'bg-white/80 backdrop-blur-xl border border-white/20 shadow-xl rounded-2xl'
    : 'bg-white border border-gray-200 shadow-sm rounded-2xl'
  return <div className={`${base} ${paddingMap[padding]} ${className}`}>{children}</div>
}

export function CardHeader({ children, className = '' }: CardHeaderProps) {
  return <div className={`pb-4 border-b border-gray-100 ${className}`}>{children}</div>
}

export function CardFooter({ children, className = '' }: CardFooterProps) {
  return <div className={`pt-4 border-t border-gray-100 ${className}`}>{children}</div>
}
