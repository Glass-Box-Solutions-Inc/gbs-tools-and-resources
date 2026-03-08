// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
import { Table, TableHeader, TableRow, TableCell, Badge, EmptyState } from '../../ui'
import { FolderOpen } from 'lucide-react'
import { navigate } from '../../../router'
import type { CaseItem } from '../../../lib/types'

interface CaseListProps {
  cases: CaseItem[]
}

export function CaseList({ cases }: CaseListProps) {
  if (!cases.length) {
    return (
      <EmptyState
        icon={<FolderOpen className="w-8 h-8 text-gray-400" />}
        title="No cases found"
        description="Try a different search term or adjust your filters."
      />
    )
  }

  return (
    <Table>
      <TableHeader columns={['File Number', 'Primary Party', 'Type', 'Status']} />
      <tbody>
        {cases.map((c) => (
          <TableRow key={c.id} onClick={() => navigate(`/cases/${c.id}`)}>
            <TableCell className="font-medium text-teal-600">{c.file_number}</TableCell>
            <TableCell>{c.primary_party_name}</TableCell>
            <TableCell className="text-gray-500">{c.case_type}</TableCell>
            <TableCell>
              <Badge variant={c.case_status?.toLowerCase() === 'active' ? 'success' : 'default'} dot>
                {c.case_status || 'Unknown'}
              </Badge>
            </TableCell>
          </TableRow>
        ))}
      </tbody>
    </Table>
  )
}
