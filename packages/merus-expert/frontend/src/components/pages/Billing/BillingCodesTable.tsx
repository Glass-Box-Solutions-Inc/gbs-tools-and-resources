// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
import { Table, TableHeader, TableRow, TableCell, LoadingSpinner, EmptyState } from '../../ui'
import { useBillingCodes } from '../../../hooks/useReference'

export function BillingCodesTable() {
  const { data, isLoading } = useBillingCodes()

  if (isLoading) return <LoadingSpinner size="sm" text="Loading billing codes..." />

  const codes = data?.data ? Object.values(data.data) : []
  if (!codes.length)
    return <EmptyState title="No billing codes" description="No billing codes available." />

  return (
    <div>
      <h3 className="text-sm font-medium text-gray-900 mb-3">
        Billing Codes Reference ({data?.count ?? 0})
      </h3>
      <Table>
        <TableHeader columns={['Code', 'Description']} />
        <tbody>
          {codes.map((code) => (
            <TableRow key={code.id}>
              <TableCell className="font-mono font-medium text-teal-600">{code.code}</TableCell>
              <TableCell className="text-gray-600">{code.description}</TableCell>
            </TableRow>
          ))}
        </tbody>
      </Table>
    </div>
  )
}
