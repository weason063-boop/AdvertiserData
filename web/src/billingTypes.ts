export interface Client {
  id: number
  name: string
  business_type: string
  department: string
  entity: string
  fee_clause: string
  updated_at: string
}

export interface ResultRow {
  [key: string]: string | number
}

export interface CalculationResult {
  columns: string[]
  data: ResultRow[]
  total: number
}

export interface SyncResult {
  count: number
  message: string
  time: string
}

export interface OperationAuditLog {
  id: number
  category: string
  action: string
  actor: string
  status: string
  input_file?: string | null
  output_file?: string | null
  result_ref?: string | null
  error_message?: string | null
  metadata?: Record<string, unknown> | null
  created_at: string
}
