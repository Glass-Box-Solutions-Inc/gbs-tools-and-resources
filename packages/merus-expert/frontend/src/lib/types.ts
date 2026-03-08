// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
// API Response Types

export interface SessionResponse {
  session_id: string
  state: string
  created_at: string
  message: string
}

export interface ChatResponse {
  session_id: string
  message: string
  state: string
  is_complete: boolean
  action?: string
  quick_chips: string[]
  collected_fields: Record<string, unknown>
}

export interface MatterResponse {
  session_id: string
  matter_id?: number
  status: string
  message: string
  meruscase_url?: string
  screenshot_path?: string
  filled_values?: Record<string, unknown>
  error?: string
}

// Message Types
export interface Message {
  role: 'user' | 'assistant' | 'system'
  content: string
  timestamp: Date
}

// Collected field for matter progress display
export interface CollectedField {
  key: string
  label: string
  value: unknown
  hasValue: boolean
}

// Chat State
export interface ChatState {
  sessionId: string | null
  messages: Message[]
  conversationState: string
  isComplete: boolean
  action: string | null
  loading: boolean
  error: string | null
  quickChips: string[]
  collectedFields: Record<string, unknown>
}

// ─── Case Types ───
export interface CaseItem {
  id: string
  file_number: string
  primary_party_name: string
  case_status: string
  case_type: string
  data?: Record<string, unknown>
}

export interface CaseListResponse {
  cases: CaseItem[]
  count: number
}

export interface CaseDetailResponse {
  id: string
  file_number: string
  primary_party_name: string
  case_status: string
  case_type: string
  data: Record<string, unknown>
}

export interface CaseBillingResponse {
  case_id: string
  entries: Record<string, unknown>
  total_entries: number
}

export interface CaseActivitiesResponse {
  case_id: string
  activities: Activity[]
  count: number
}

export interface Activity {
  id: string
  subject: string
  description?: string
  created_at?: string
  [key: string]: unknown
}

export interface Party {
  id: string
  name: string
  type?: string
  email?: string
  phone?: string
  [key: string]: unknown
}

export interface CasePartiesResponse {
  case_id: string
  parties: Party[]
}

export interface BillingSummaryResponse {
  case_id: string
  case_name: string
  total_amount: number
  total_entries: number
  entries: Record<string, unknown>
  start_date?: string
  end_date?: string
}

// ─── Billing Types ───
export interface BillTimeRequest {
  case_search: string
  hours: number
  description: string
  subject?: string
  activity_type_id?: number
  billing_code_id?: number
}

export interface BillTimeResponse {
  success: boolean
  activity_id?: string
  case_id?: string
  case_name?: string
  hours?: number
  minutes?: number
  description?: string
  error?: string
}

export interface AddCostRequest {
  case_search: string
  amount: number
  description: string
  ledger_type?: string
}

export interface AddCostResponse {
  success: boolean
  ledger_id?: number
  case_id?: string
  case_name?: string
  amount?: number
  description?: string
  type?: string
  error?: string
}

// ─── Activities Types ───
export interface AddNoteRequest {
  case_search: string
  subject: string
  description?: string
  activity_type_id?: number
}

export interface AddNoteResponse {
  success: boolean
  activity_id?: string
  case_id?: string
  case_name?: string
  subject?: string
  error?: string
}

// ─── Reference Types ───
export interface BillingCode {
  id: number
  code: string
  description: string
  [key: string]: unknown
}

export interface ActivityType {
  id: number
  name: string
  billable?: boolean
  [key: string]: unknown
}

export interface ReferenceDataResponse<T> {
  data: Record<string, T>
  count: number
}

// ─── Agent Types ───
export interface AgentMessage {
  role: 'user' | 'assistant'
  content: string
}

export interface AgentChatRequest {
  messages: AgentMessage[]
  max_iterations?: number
}

export type AgentStreamEvent =
  | { type: 'text'; content: string }
  | { type: 'tool_call'; name: string; input: Record<string, unknown> }
  | { type: 'tool_result'; name: string; result: Record<string, unknown> }
  | { type: 'done' }
  | { type: 'error'; message: string }
