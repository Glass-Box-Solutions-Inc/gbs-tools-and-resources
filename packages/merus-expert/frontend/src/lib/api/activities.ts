// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
import { apiPost } from './client'
import type { AddNoteRequest, AddNoteResponse } from '../types'

export const activitiesApi = {
  addNote(data: AddNoteRequest): Promise<AddNoteResponse> {
    return apiPost<AddNoteResponse>('/activities/note', data)
  },
}
