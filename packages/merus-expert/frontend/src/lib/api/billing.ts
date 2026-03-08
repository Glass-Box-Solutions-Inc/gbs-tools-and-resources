// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
import { apiPost } from './client'
import type { BillTimeRequest, BillTimeResponse, AddCostRequest, AddCostResponse } from '../types'

export const billingApi = {
  billTime(data: BillTimeRequest): Promise<BillTimeResponse> {
    return apiPost<BillTimeResponse>('/billing/time', data)
  },

  addCost(data: AddCostRequest): Promise<AddCostResponse> {
    return apiPost<AddCostResponse>('/billing/cost', data)
  },
}
