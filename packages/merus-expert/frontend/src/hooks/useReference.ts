// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
import { useQuery } from '@tanstack/react-query'
import { referenceApi } from '../lib/api/index'

export function useBillingCodes() {
  return useQuery({
    queryKey: ['billing-codes'],
    queryFn: () => referenceApi.getBillingCodes(),
    staleTime: 60 * 60 * 1000, // 1 hour cache
  })
}

export function useActivityTypes() {
  return useQuery({
    queryKey: ['activity-types'],
    queryFn: () => referenceApi.getActivityTypes(),
    staleTime: 60 * 60 * 1000,
  })
}
