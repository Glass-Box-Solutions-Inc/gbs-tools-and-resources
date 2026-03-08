// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
import type { ReactNode } from 'react'

interface TableProps {
  children: ReactNode
  className?: string
}

interface TableHeaderProps {
  columns: string[]
  className?: string
}

interface TableRowProps {
  children: ReactNode
  className?: string
  onClick?: () => void
}

interface TableCellProps {
  children: ReactNode
  className?: string
}

export function Table({ children, className = '' }: TableProps) {
  return (
    <div className={`overflow-x-auto rounded-xl border border-gray-200 ${className}`}>
      <table className="w-full text-sm">{children}</table>
    </div>
  )
}

export function TableHeader({ columns, className = '' }: TableHeaderProps) {
  return (
    <thead className={`bg-gray-50 border-b border-gray-200 ${className}`}>
      <tr>
        {columns.map((col) => (
          <th key={col} className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
            {col}
          </th>
        ))}
      </tr>
    </thead>
  )
}

export function TableRow({ children, className = '', onClick }: TableRowProps) {
  return (
    <tr
      className={`border-b border-gray-100 last:border-0 ${onClick ? 'cursor-pointer hover:bg-gray-50' : ''} ${className}`}
      onClick={onClick}
    >
      {children}
    </tr>
  )
}

export function TableCell({ children, className = '' }: TableCellProps) {
  return <td className={`px-4 py-3 ${className}`}>{children}</td>
}
