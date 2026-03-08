// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
import { Table, TableHeader, TableRow, TableCell, Badge, LoadingSpinner, EmptyState } from '../../ui'
import { useCaseBilling, useCaseActivities, useCaseParties } from '../../../hooks/useCases'

export function CaseBillingTab({ caseId }: { caseId: string }) {
  const { data, isLoading } = useCaseBilling(caseId)

  if (isLoading) return <LoadingSpinner size="sm" />

  const entries = data?.entries ? Object.values(data.entries) : []
  if (!entries.length) {
    return <EmptyState title="No billing entries" description="No billing records found for this case." />
  }

  return (
    <Table>
      <TableHeader columns={['Description', 'Amount', 'Date']} />
      <tbody>
        {entries.map((rawEntry: unknown, i: number) => {
          // Entries arrive as opaque objects from the MerusCase API; cast defensively
          const entry = rawEntry as Record<string, unknown>
          return (
            <TableRow key={i}>
              <TableCell>{String(entry.description ?? entry.memo ?? '--')}</TableCell>
              <TableCell className="font-medium">${Number(entry.amount ?? 0).toFixed(2)}</TableCell>
              <TableCell className="text-gray-500">{String(entry.date ?? entry.created_at ?? '--')}</TableCell>
            </TableRow>
          )
        })}
      </tbody>
    </Table>
  )
}

export function CaseActivitiesTab({ caseId }: { caseId: string }) {
  const { data, isLoading } = useCaseActivities(caseId)

  if (isLoading) return <LoadingSpinner size="sm" />

  const activities = data?.activities ?? []
  if (!activities.length) {
    return <EmptyState title="No activities" description="No activity records found for this case." />
  }

  return (
    <Table>
      <TableHeader columns={['Subject', 'Description', 'Date']} />
      <tbody>
        {activities.map((a) => (
          <TableRow key={a.id}>
            <TableCell className="font-medium">{a.subject}</TableCell>
            <TableCell className="text-gray-500">{a.description ?? '--'}</TableCell>
            <TableCell className="text-gray-500">{a.created_at ?? '--'}</TableCell>
          </TableRow>
        ))}
      </tbody>
    </Table>
  )
}

export function CasePartiesTab({ caseId }: { caseId: string }) {
  const { data, isLoading } = useCaseParties(caseId)

  if (isLoading) return <LoadingSpinner size="sm" />

  const parties = data?.parties ?? []
  if (!parties.length) {
    return <EmptyState title="No parties" description="No parties found for this case." />
  }

  return (
    <Table>
      <TableHeader columns={['Name', 'Type', 'Email', 'Phone']} />
      <tbody>
        {parties.map((p) => (
          <TableRow key={p.id}>
            <TableCell className="font-medium">{p.name}</TableCell>
            <TableCell><Badge>{p.type ?? 'Unknown'}</Badge></TableCell>
            <TableCell className="text-gray-500">{p.email ?? '--'}</TableCell>
            <TableCell className="text-gray-500">{p.phone ?? '--'}</TableCell>
          </TableRow>
        ))}
      </tbody>
    </Table>
  )
}
