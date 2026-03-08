// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
import { useSettingsStore } from '../../stores/settingsStore'

const API_BASE = '/api'

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
    this.name = 'ApiError'
  }
}

function getHeaders(): Record<string, string> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  const apiKey = useSettingsStore.getState().apiKey
  if (apiKey) {
    headers['X-API-Key'] = apiKey
  }
  return headers
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: 'Unknown error' }))
    throw new ApiError(response.status, body.detail || body.error || `HTTP ${response.status}`)
  }
  return response.json()
}

export async function apiGet<T>(path: string, params?: Record<string, string | number | undefined>): Promise<T> {
  const url = new URL(`${API_BASE}${path}`, window.location.origin)
  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== '') {
        url.searchParams.set(key, String(value))
      }
    })
  }
  const response = await fetch(url.toString(), { headers: getHeaders() })
  return handleResponse<T>(response)
}

export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: getHeaders(),
    body: body ? JSON.stringify(body) : undefined,
  })
  return handleResponse<T>(response)
}

export function apiStreamUrl(path: string): string {
  return `${API_BASE}${path}`
}

export { API_BASE, getHeaders }
