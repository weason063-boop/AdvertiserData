import { ArrowLeft } from 'lucide-react'
import { useEffect, useState } from 'react'
import { apiJson, isApiHttpError } from './apiClient'
import { BILLING_DETAIL_COLUMNS, type BillingDetailColumn } from './billingDetailColumns'
import type { ClientHistoryResponse, ClientHistoryRow } from './billingTypes'
import { EmptyState } from './EmptyState'
import { Skeleton } from './Skeleton'

interface ClientHistoryDetailPanelProps {
  active: boolean
  isAuthenticated: boolean
  clientName: string | null
  formatNumber: (value: string | number) => string
  onBack: () => void
  onNotify?: (message: string, type: 'info' | 'success' | 'error') => void
  onRequireAuth?: () => void
}

const renderFieldValue = (value: string | null | undefined) => {
  const text = String(value || '').trim()
  return text || '未配置'
}

const renderMetricCell = (
  row: ClientHistoryRow,
  column: BillingDetailColumn,
  formatNumber: (value: string | number) => string,
) => {
  const value = row[column.key]
  if (column.numeric) {
    return formatNumber(typeof value === 'number' ? value : 0)
  }
  return renderFieldValue(typeof value === 'string' ? value : '')
}

export function ClientHistoryDetailPanel({
  active,
  isAuthenticated,
  clientName,
  formatNumber,
  onBack,
  onNotify,
  onRequireAuth,
}: ClientHistoryDetailPanelProps) {
  const [data, setData] = useState<ClientHistoryResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [errorMessage, setErrorMessage] = useState('')

  useEffect(() => {
    if (!active || !isAuthenticated || !clientName) return

    const controller = new AbortController()
    setData(null)
    setErrorMessage('')
    setLoading(true)

    apiJson<ClientHistoryResponse>(
      `/api/dashboard/client/${encodeURIComponent(clientName)}/history`,
      { signal: controller.signal },
      { throwOnHttpError: false },
    )
      .then(({ data: payload, res }) => {
        if (controller.signal.aborted) return

        if (res.status === 401) {
          onRequireAuth?.()
          return
        }

        if (!res.ok) {
          const nextError = '加载客户历史账单失败'
          setErrorMessage(nextError)
          onNotify?.(nextError, 'error')
          return
        }

        setData(payload)
        setErrorMessage('')
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return
        if (isApiHttpError(error) && error.status === 401) {
          onRequireAuth?.()
          return
        }
        const nextError = error instanceof Error ? error.message : '加载客户历史账单失败'
        setErrorMessage(nextError)
        onNotify?.(nextError, 'error')
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setLoading(false)
        }
      })

    return () => controller.abort()
  }, [active, clientName, isAuthenticated, onNotify, onRequireAuth])

  if (!active) return null

  if (!isAuthenticated) {
    return (
      <EmptyState
        title="请先登录"
        description="登录后即可查看客户历史账单明细。"
      />
    )
  }

  if (!clientName) {
    return (
      <EmptyState
        title="先选择一个客户"
        description="从账单明细页点击客户简称，即可进入该客户的历史详情。"
      />
    )
  }

  const rows = data?.rows ?? []
  const summary = data?.summary ?? null
  const summaryRangeLabel = summary?.first_month && summary?.latest_month
    ? (summary.first_month === summary.latest_month
        ? summary.latest_month
        : `${summary.first_month} 至 ${summary.latest_month}`)
    : '暂无统计区间'
  const summaryCards = summary ? [
    { key: 'total_total', label: '累计汇总金额', value: summary.total_total, emphasis: true },
    { key: 'total_consumption', label: '累计总消耗', value: summary.total_consumption },
    { key: 'total_service_fee', label: '累计总服务费', value: summary.total_service_fee },
    { key: 'total_net_consumption', label: '累计汇总纯消耗', value: summary.total_net_consumption },
    { key: 'total_variable_service_fee', label: '累计服务费', value: summary.total_variable_service_fee },
    { key: 'total_fixed_service_fee', label: '累计固定服务费', value: summary.total_fixed_service_fee },
  ] : []

  return (
    <section className="client-history-section">
      <div className="ledger-page-shell">
        <div className="module-card">
          <div className="client-history-header">
          <div className="client-history-title-block" style={{ flexDirection: 'row', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
            <button type="button" className="client-history-back-btn" onClick={onBack}>
              <ArrowLeft size={16} />
              账单明细
            </button>
            <span style={{ color: 'var(--border-strong)' }}>/</span>
            <h3 style={{ margin: 0, fontSize: '1.06rem' }}>{clientName} 的历史记录</h3>
          </div>
          </div>

          {loading ? (
            <div className="client-history-skeleton">
              <Skeleton variant="rect" height={96} />
              <Skeleton variant="rect" height={320} />
            </div>
          ) : errorMessage ? (
            <EmptyState title="历史账单加载失败" description={errorMessage} />
          ) : (
            <>
              {rows.length === 0 ? (
                <EmptyState
                  title="该客户暂无历史记录"
                  description="当前没有可展示的历史账单明细。"
                />
              ) : (
                <>
                  {summaryCards.length > 0 ? (
                    <section className="client-history-summary-section">
                      <div className="client-history-summary-head">
                        <div className="client-history-summary-copy">
                          <span className="client-history-kicker">汇总概览</span>
                          <p className="client-history-period">统计区间：{summaryRangeLabel}</p>
                        </div>
                        <span className="client-history-summary-meta">共 {rows.length} 个账单月</span>
                      </div>
                      <div className="client-history-summary-grid">
                        {summaryCards.map((card) => (
                          <article
                            key={card.key}
                            className={`client-history-summary-card${card.emphasis ? ' is-emphasis' : ''}`}
                          >
                            <span className="summary-label">{card.label}</span>
                            <strong>{formatNumber(card.value)}</strong>
                          </article>
                        ))}
                      </div>
                    </section>
                  ) : null}

                  <div className="table-wrapper">
                    <div className="data-table-container client-history-table-wrap">
                      <table className="data-table client-history-table">
                        <thead>
                          <tr>
                            <th className="col-month">月份</th>
                            {BILLING_DETAIL_COLUMNS.map((column) => (
                              <th key={column.key} className={column.numeric ? 'cell-number' : 'cell-type'}>
                                {column.label}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {rows.map((row) => (
                            <tr key={row.month}>
                              <td className="cell-name">{row.month}</td>
                              {BILLING_DETAIL_COLUMNS.map((column) => (
                                <td key={column.key} className={column.numeric ? 'cell-number' : 'cell-type'}>
                                  {renderMetricCell(row, column, formatNumber)}
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </>
              )}
            </>
          )}
        </div>
      </div>
    </section>
  )
}
