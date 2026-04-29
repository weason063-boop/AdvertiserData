export interface Client {
  id: number
  name: string
  business_type: string
  department: string
  entity: string
  fee_clause: string
  payment_term: string
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

export interface DashboardStats {
  consumption: number
  fee: number
  month: string
  consumption_mom: number
  fee_mom: number
  consumption_yoy: number
  fee_yoy: number
}

export interface DashboardTrendPoint {
  month: string
  total_consumption: number
  total_service_fee: number
}

export interface DashboardTopClient {
  client_name: string
  consumption: number
  service_fee: number
}

export interface ReceivableCurrencyAmount {
  currency_code: string
  currency: string
  amount: number
  count: number
}

export interface ReceivableAgingBucket {
  key: string
  label: string
  min_days: number
  max_days?: number | null
  count: number
  amount_by_currency: ReceivableCurrencyAmount[]
}

export interface ReceivableTopOverdue {
  record_id?: string
  table_name?: string | null
  application_no?: string | null
  client_name: string
  project_name?: string | null
  flow_type: string
  approval_status?: string | null
  approval_node?: string | null
  currency: string
  currency_code: string
  amount: number
  outstanding_amount: number
  overdue_amount: number
  overdue_days: number
  due_date?: string | null
  owner_name?: string | null
}

export interface ReceivableSummary {
  total_records: number
  active_records: number
  outstanding: {
    count: number
    amount_by_currency: ReceivableCurrencyAmount[]
  }
  overdue: {
    count: number
    amount_by_currency: ReceivableCurrencyAmount[]
    max_overdue_days: number
    aging_buckets?: ReceivableAgingBucket[]
  }
  by_flow: Array<{
    flow_type: string
    count: number
    outstanding: ReceivableCurrencyAmount[]
    overdue: ReceivableCurrencyAmount[]
  }>
  top_overdue: ReceivableTopOverdue[]
  synced_at?: string | null
}

export interface ReceivableBillsResponse {
  status: 'overdue' | 'outstanding' | 'all'
  limit: number
  client_name?: string | null
  rows: ReceivableTopOverdue[]
}

export interface ReceivableClientSummaryRow {
  client_name: string
  owner_names: string[]
  bill_count: number
  outstanding_count: number
  overdue_count: number
  outstanding_amount_by_currency: ReceivableCurrencyAmount[]
  overdue_amount_by_currency: ReceivableCurrencyAmount[]
  max_overdue_days: number
}

export interface ReceivableClientSummaryResponse {
  metric: 'overdue' | 'outstanding'
  limit: number
  rows: ReceivableClientSummaryRow[]
}

export interface DashboardData {
  stats: DashboardStats | null
  trend: DashboardTrendPoint[]
  top_clients?: DashboardTopClient[]
}

export interface SyncResult {
  count: number
  message: string
  time: string
  line_count?: number
  client_count?: number
  new_client_count?: number
  unchanged_count?: number
  pending_count?: number
  new_clients?: string[]
}

export interface ContractChangeReview {
  id: number
  client_name: string
  source_type: string
  source_token: string
  sync_batch_id: string
  status: 'pending' | 'approved' | 'ignored'
  change_fields: string[]
  current_business_type: string | null
  new_business_type: string | null
  current_department: string | null
  new_department: string | null
  current_entity: string | null
  new_entity: string | null
  current_fee_clause: string | null
  new_fee_clause: string | null
  current_payment_term: string | null
  new_payment_term: string | null
  reviewed_at: string | null
  reviewed_by: string | null
  created_at: string
  updated_at: string
}

export interface BillingDetailMetrics {
  bill_type: string
  service_type: string
  flow_consumption: number
  managed_consumption: number
  net_consumption: number
  service_fee: number
  fixed_service_fee: number
  coupon: number
  dst: number
  total: number
  consumption: number
  service_fee_total: number
}

export interface LatestMonthClientRow extends BillingDetailMetrics {
  client_name: string
  month: string | null
  entity: string | null
  owner: string | null
  bill_amount: number
  note: string | null
}

export interface LatestMonthClientsResponse {
  latest_month: string | null
  rows: LatestMonthClientRow[]
}

export interface ClientProfile {
  client_name: string
  business_type: string | null
  department: string | null
  entity: string | null
  fee_clause: string | null
  payment_term: string | null
}

export interface ClientHistoryRow extends BillingDetailMetrics {
  month: string
}

export interface ClientHistoryResponse {
  profile: ClientProfile
  rows: ClientHistoryRow[]
  summary: {
    first_month: string | null
    latest_month: string | null
    total_consumption: number
    total_service_fee: number
    total_flow_consumption: number
    total_managed_consumption: number
    total_net_consumption: number
    total_variable_service_fee: number
    total_fixed_service_fee: number
    total_coupon: number
    total_dst: number
    total_total: number
  }
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
