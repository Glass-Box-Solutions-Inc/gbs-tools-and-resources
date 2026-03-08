// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
import { apiGet } from './client'
import type {
  CaseListResponse,
  CaseItem,
  CaseDetailResponse,
  CaseBillingResponse,
  CaseActivitiesResponse,
  CasePartiesResponse,
  BillingSummaryResponse,
} from '../types'

export const casesApi = {
  list(params?: { status?: string; type?: string; limit?: number }): Promise<CaseListResponse> {
    return apiGet<CaseListResponse>('/cases', params)
  },

  search(query: string, limit?: number): Promise<CaseItem> {
    return apiGet<CaseItem>('/cases/search', { query, limit })
  },

  getDetail(caseId: string): Promise<CaseDetailResponse> {
    return apiGet<CaseDetailResponse>(`/cases/${caseId}`)
  },

  getBilling(caseId: string, params?: { date_gte?: string; date_lte?: string }): Promise<CaseBillingResponse> {
    return apiGet<CaseBillingResponse>(`/cases/${caseId}/billing`, params)
  },

  getActivities(caseId: string, limit?: number): Promise<CaseActivitiesResponse> {
    return apiGet<CaseActivitiesResponse>(`/cases/${caseId}/activities`, { limit })
  },

  getParties(caseId: string): Promise<CasePartiesResponse> {
    return apiGet<CasePartiesResponse>(`/cases/${caseId}/parties`)
  },

  getSummary(caseId: string, params?: { start_date?: string; end_date?: string }): Promise<BillingSummaryResponse> {
    return apiGet<BillingSummaryResponse>(`/cases/${caseId}/summary`, params)
  },
}
