// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { activitiesApi } from '../lib/api/index'
import { useUIStore } from '../stores/uiStore'
import type { AddNoteRequest, AddNoteResponse } from '../lib/types'

export function useAddNote() {
  const queryClient = useQueryClient()
  const addToast = useUIStore((s) => s.addToast)

  return useMutation<AddNoteResponse, Error, AddNoteRequest>({
    mutationFn: (data: AddNoteRequest) => activitiesApi.addNote(data),
    onSuccess: (res) => {
      if (res.success) {
        addToast('success', `Note added to ${res.case_name}`)
        queryClient.invalidateQueries({ queryKey: ['case-activities'] })
      } else {
        addToast('error', res.error || 'Failed to add note')
      }
    },
    onError: (err) => addToast('error', err.message),
  })
}
