// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
import { Table, TableHeader, TableRow, TableCell, Badge, LoadingSpinner, EmptyState } from '../../ui'
import { useActivityTypes } from '../../../hooks/useReference'

export function ActivityTypesTable() {
  const { data, isLoading } = useActivityTypes()

  if (isLoading) return <LoadingSpinner size="sm" text="Loading activity types..." />

  const types = data?.data ? Object.values(data.data) : []
  if (!types.length)
    return <EmptyState title="No activity types" description="No activity types available." />

  return (
    <div>
      <h3 className="text-sm font-medium text-gray-900 mb-3">
        Activity Types Reference ({data?.count ?? 0})
      </h3>
      <Table>
        <TableHeader columns={['Name', 'Billable']} />
        <tbody>
          {types.map((t) => (
            <TableRow key={t.id}>
              <TableCell className="font-medium">{t.name}</TableCell>
              <TableCell>
                <Badge variant={t.billable ? 'success' : 'default'}>
                  {t.billable ? 'Yes' : 'No'}
                </Badge>
              </TableCell>
            </TableRow>
          ))}
        </tbody>
      </Table>
    </div>
  )
}
