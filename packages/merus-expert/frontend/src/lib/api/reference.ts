// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
import { apiGet } from './client'
import type { ReferenceDataResponse, BillingCode, ActivityType } from '../types'

export const referenceApi = {
  getBillingCodes(): Promise<ReferenceDataResponse<BillingCode>> {
    return apiGet<ReferenceDataResponse<BillingCode>>('/reference/billing-codes')
  },

  getActivityTypes(): Promise<ReferenceDataResponse<ActivityType>> {
    return apiGet<ReferenceDataResponse<ActivityType>>('/reference/activity-types')
  },
}
