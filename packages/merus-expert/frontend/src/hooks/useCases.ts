// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
import { useQuery } from '@tanstack/react-query'
import { casesApi } from '../lib/api/index'

export function useCaseList(params?: { status?: string; type?: string; limit?: number }) {
  return useQuery({
    queryKey: ['cases', params],
    queryFn: () => casesApi.list(params),
  })
}

export function useCaseDetail(caseId: string | undefined) {
  return useQuery({
    queryKey: ['case', caseId],
    queryFn: () => casesApi.getDetail(caseId!),
    enabled: !!caseId,
  })
}

export function useCaseBilling(caseId: string | undefined, params?: { date_gte?: string; date_lte?: string }) {
  return useQuery({
    queryKey: ['case-billing', caseId, params],
    queryFn: () => casesApi.getBilling(caseId!, params),
    enabled: !!caseId,
  })
}

export function useCaseActivities(caseId: string | undefined, limit?: number) {
  return useQuery({
    queryKey: ['case-activities', caseId, limit],
    queryFn: () => casesApi.getActivities(caseId!, limit),
    enabled: !!caseId,
  })
}

export function useCaseParties(caseId: string | undefined) {
  return useQuery({
    queryKey: ['case-parties', caseId],
    queryFn: () => casesApi.getParties(caseId!),
    enabled: !!caseId,
  })
}

export function useCaseSummary(caseId: string | undefined, params?: { start_date?: string; end_date?: string }) {
  return useQuery({
    queryKey: ['case-summary', caseId, params],
    queryFn: () => casesApi.getSummary(caseId!, params),
    enabled: !!caseId,
  })
}
