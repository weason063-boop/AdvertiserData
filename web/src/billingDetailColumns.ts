import type { BillingDetailMetrics } from './billingTypes'

export interface BillingDetailColumn {
  key: keyof BillingDetailMetrics
  label: string
  numeric?: boolean
}

export const BILLING_DETAIL_COLUMNS: BillingDetailColumn[] = [
  { key: 'bill_type', label: '账单类型' },
  { key: 'service_type', label: '服务类型' },
  { key: 'flow_consumption', label: '流水消耗', numeric: true },
  { key: 'managed_consumption', label: '代投消耗', numeric: true },
  { key: 'net_consumption', label: '汇总纯消耗', numeric: true },
  { key: 'service_fee', label: '服务费', numeric: true },
  { key: 'fixed_service_fee', label: '固定服务费', numeric: true },
  { key: 'coupon', label: 'COUPON', numeric: true },
  { key: 'dst', label: '监管运营费用/数字服务税(DST)', numeric: true },
  { key: 'total', label: '汇总', numeric: true },
]
