// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { billingApi } from '../lib/api/index'
import { useUIStore } from '../stores/uiStore'
import type { BillTimeRequest, BillTimeResponse, AddCostRequest, AddCostResponse } from '../lib/types'

export function useBillTime() {
  const queryClient = useQueryClient()
  const addToast = useUIStore((s) => s.addToast)

  return useMutation<BillTimeResponse, Error, BillTimeRequest>({
    mutationFn: (data: BillTimeRequest) => billingApi.billTime(data),
    onSuccess: (res) => {
      if (res.success) {
        addToast('success', `Billed ${res.hours}h to ${res.case_name}`)
        queryClient.invalidateQueries({ queryKey: ['case-billing'] })
      } else {
        addToast('error', res.error || 'Failed to bill time')
      }
    },
    onError: (err) => addToast('error', err.message),
  })
}

export function useAddCost() {
  const queryClient = useQueryClient()
  const addToast = useUIStore((s) => s.addToast)

  return useMutation<AddCostResponse, Error, AddCostRequest>({
    mutationFn: (data: AddCostRequest) => billingApi.addCost(data),
    onSuccess: (res) => {
      if (res.success) {
        addToast('success', `Added $${res.amount} cost to ${res.case_name}`)
        queryClient.invalidateQueries({ queryKey: ['case-billing'] })
      } else {
        addToast('error', res.error || 'Failed to add cost')
      }
    },
    onError: (err) => addToast('error', err.message),
  })
}
