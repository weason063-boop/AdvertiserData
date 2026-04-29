import { useEffect, useMemo, useState, type ComponentType } from 'react'
import { AlertTriangle, Clock3, RefreshCw, WalletCards, X } from 'lucide-react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { apiJson, isApiHttpError } from './apiClient'
import type {
  ReceivableAgingBucket,
  ReceivableBillsResponse,
  ReceivableClientSummaryResponse,
  ReceivableClientSummaryRow,
  ReceivableCurrencyAmount,
  ReceivableSummary,
  ReceivableTopOverdue,
} from './billingTypes'
import { Skeleton } from './Skeleton'

type BillFilter = 'overdue' | 'outstanding' | 'all'
type ClientMetric = 'overdue' | 'outstanding'

interface ReceivablesPanelProps {
  active: boolean
  canSync: boolean
  onNotify: (message: string, type: 'info' | 'success' | 'error') => void
  onRequireAuth: () => void
}

interface ClientChartPoint {
  chart_label: string
  client_name: string
  amount: number
  currency: string
  currencyName: string
  color: string
  rank: number
  overdueDays: number
  flowText: string
  row: ReceivableClientSummaryRow
}

interface AgingChartPoint extends ReceivableAgingBucket {
  color: string
}

interface ClientTooltipProps {
  active?: boolean
  payload?: Array<{ payload?: ClientChartPoint }>
}

interface AgingTooltipProps {
  active?: boolean
  payload?: Array<{ payload?: AgingChartPoint }>
}

const FILTER_OPTIONS: Array<{ key: BillFilter; label: string }> = [
  { key: 'overdue', label: '逾期' },
  { key: 'outstanding', label: '未回款' },
  { key: 'all', label: '全部' },
]

const CLIENT_METRIC_OPTIONS: Array<{ key: ClientMetric; label: string }> = [
  { key: 'overdue', label: '逾期金额' },
  { key: 'outstanding', label: '未回款金额' },
]

const AGING_COLORS = ['#ef4444', '#f97316', '#d97706', '#7f1d1d']
const CURRENCY_COLORS: Record<string, string> = {
  USD: '#2563eb',
  RMB: '#059669',
  CNY: '#059669',
  EUR: '#d97706',
  AUD: '#0f766e',
}

const fmtAmount = (value: number) => new Intl.NumberFormat('en-US', {
  maximumFractionDigits: 2,
}).format(value)

const fmtAxisAmount = (value: number) => {
  if (Math.abs(value) >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`
  if (Math.abs(value) >= 1_000) return `${(value / 1_000).toFixed(0)}K`
  return fmtAmount(value)
}

const currencyTone = (code: string) => {
  const normalized = String(code || '').toUpperCase()
  if (normalized === 'USD') return 'usd'
  if (normalized === 'RMB' || normalized === 'CNY') return 'rmb'
  if (normalized === 'EUR') return 'eur'
  if (normalized === 'AUD') return 'aud'
  return 'other'
}

const currencyColor = (code: string) => CURRENCY_COLORS[String(code || '').toUpperCase()] || '#64748b'

const flowLabel = (flowType: string) => {
  if (flowType === 'bill_send') return '账单发送'
  if (flowType === 'client_advance') return '客户垫付'
  return flowType || '-'
}

const sumEntries = (entries: ReceivableCurrencyAmount[]) => (
  entries.reduce((sum, item) => sum + Math.abs(Number(item.amount) || 0), 0)
)

const getMetricEntries = (row: ReceivableClientSummaryRow, metric: ClientMetric) => (
  metric === 'overdue' ? row.overdue_amount_by_currency : row.outstanding_amount_by_currency
)

const getCurrencyCode = (item: ReceivableCurrencyAmount) => item.currency_code || item.currency

const getPrimaryEntry = (entries: ReceivableCurrencyAmount[]) => (
  [...entries]
    .filter((item) => Math.abs(Number(item.amount) || 0) > 0)
    .sort((left, right) => Math.abs(Number(right.amount) || 0) - Math.abs(Number(left.amount) || 0))[0]
)

const isRecord = (value: unknown): value is Record<string, unknown> => (
  typeof value === 'object' && value !== null
)

const getClientChartPoint = (value: unknown): ClientChartPoint | null => {
  const candidate = isRecord(value) && isRecord(value.payload) ? value.payload : value
  if (!isRecord(candidate)) return null
  if (typeof candidate.client_name !== 'string' || typeof candidate.amount !== 'number') return null
  if (!isRecord(candidate.row)) return null
  return candidate as unknown as ClientChartPoint
}

export function ReceivablesPanel({
  active,
  canSync,
  onNotify,
  onRequireAuth,
}: ReceivablesPanelProps) {
  const [summary, setSummary] = useState<ReceivableSummary | null>(null)
  const [clientRows, setClientRows] = useState<ReceivableClientSummaryRow[]>([])
  const [clientMetric, setClientMetric] = useState<ClientMetric>('overdue')
  const [selectedClient, setSelectedClient] = useState<ReceivableClientSummaryRow | null>(null)
  const [detailFilter, setDetailFilter] = useState<BillFilter>('all')
  const [detailRows, setDetailRows] = useState<ReceivableTopOverdue[]>([])
  const [summaryDetail, setSummaryDetail] = useState<{ status: 'outstanding' | 'overdue'; title: string } | null>(null)
  const [summaryDetailRows, setSummaryDetailRows] = useState<ReceivableTopOverdue[]>([])
  const [loading, setLoading] = useState(false)
  const [detailLoading, setDetailLoading] = useState(false)
  const [summaryDetailLoading, setSummaryDetailLoading] = useState(false)
  const [syncing, setSyncing] = useState(false)

  const loadData = async (nextMetric: ClientMetric = clientMetric) => {
    if (!active) return
    setLoading(true)
    try {
      const [{ data: summaryData }, { data: clientSummaryData }] = await Promise.all([
        apiJson<ReceivableSummary>('/api/feishu/receivables/summary'),
        apiJson<ReceivableClientSummaryResponse>(`/api/feishu/receivables/client-summary?metric=${nextMetric}&limit=100`),
      ])
      setSummary(summaryData)
      setClientRows(clientSummaryData.rows || [])
    } catch (error: unknown) {
      if (isApiHttpError(error) && error.status === 401) {
        onRequireAuth()
        return
      }
      const message = error instanceof Error && error.message ? error.message : '应收回款数据加载失败'
      onNotify(message, 'error')
    } finally {
      setLoading(false)
    }
  }

  const loadClientDetails = async (clientName: string, nextFilter: BillFilter = detailFilter) => {
    setDetailLoading(true)
    try {
      const query = new URLSearchParams({
        client_name: clientName,
        status: nextFilter,
        limit: '300',
      })
      const { data } = await apiJson<ReceivableBillsResponse>(`/api/feishu/receivables/bills?${query.toString()}`)
      setDetailRows(data.rows || [])
    } catch (error: unknown) {
      if (isApiHttpError(error) && error.status === 401) {
        onRequireAuth()
        return
      }
      const message = error instanceof Error && error.message ? error.message : '客户明细加载失败'
      onNotify(message, 'error')
    } finally {
      setDetailLoading(false)
    }
  }

  const loadSummaryDetails = async (status: 'outstanding' | 'overdue') => {
    setSummaryDetailLoading(true)
    try {
      const query = new URLSearchParams({
        status,
        limit: '500',
      })
      const { data } = await apiJson<ReceivableBillsResponse>(`/api/feishu/receivables/bills?${query.toString()}`)
      setSummaryDetailRows(data.rows || [])
    } catch (error: unknown) {
      if (isApiHttpError(error) && error.status === 401) {
        onRequireAuth()
        return
      }
      const message = error instanceof Error && error.message ? error.message : '汇总明细加载失败'
      onNotify(message, 'error')
    } finally {
      setSummaryDetailLoading(false)
    }
  }

  const handleSync = async () => {
    if (!canSync) {
      onNotify('当前账号没有飞书同步权限', 'error')
      return
    }
    setSyncing(true)
    try {
      const { data } = await apiJson<{ synced_records?: number; message?: string }>(
        '/api/feishu/receivables/sync',
        { method: 'POST' },
      )
      onNotify(data.message || `飞书应收数据同步完成，共 ${data.synced_records || 0} 条`, 'success')
      await loadData(clientMetric)
      if (selectedClient) {
        await loadClientDetails(selectedClient.client_name, detailFilter)
      }
      if (summaryDetail) {
        await loadSummaryDetails(summaryDetail.status)
      }
    } catch (error: unknown) {
      if (isApiHttpError(error) && error.status === 401) {
        onRequireAuth()
        return
      }
      const message = error instanceof Error && error.message ? error.message : '飞书应收数据同步失败'
      onNotify(message, 'error')
    } finally {
      setSyncing(false)
    }
  }

  const openClient = (row: ReceivableClientSummaryRow) => {
    setSelectedClient(row)
    setDetailFilter('all')
    void loadClientDetails(row.client_name, 'all')
  }

  const openSummaryDetail = (status: 'outstanding' | 'overdue') => {
    setSummaryDetail({
      status,
      title: status === 'overdue' ? '逾期账单金额' : '未回款金额',
    })
    setSummaryDetailRows([])
    void loadSummaryDetails(status)
  }

  useEffect(() => {
    if (!active) return
    void loadData(clientMetric)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- tab/metric change is the intended reload trigger
  }, [active, clientMetric])

  useEffect(() => {
    if (!selectedClient) return
    void loadClientDetails(selectedClient.client_name, detailFilter)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reload drawer detail when filter changes
  }, [detailFilter])

  const clientChartRows = useMemo<ClientChartPoint[]>(() => (
    clientRows
      .flatMap((row) => getMetricEntries(row, clientMetric).map((item) => {
        const currency = getCurrencyCode(item)
        return {
          row,
          chart_label: `${row.client_name}·${currency}`,
          client_name: row.client_name,
          amount: Number(item.amount) || 0,
          currency,
          currencyName: item.currency || currency,
          color: currencyColor(currency),
          overdueDays: row.max_overdue_days,
          flowText: `${clientMetric === 'overdue' ? row.overdue_count : row.outstanding_count}/${row.bill_count}`,
        }
      }))
      .filter((row) => Math.abs(row.amount) > 0)
      .sort((left, right) => right.amount - left.amount || right.overdueDays - left.overdueDays)
      .slice(0, 10)
      .map((row, index) => ({ ...row, rank: index + 1 }))
  ), [clientMetric, clientRows])

  const chartCurrencies = useMemo(() => {
    const seen = new Set<string>()
    return clientChartRows
      .filter((item) => {
        if (seen.has(item.currency)) return false
        seen.add(item.currency)
        return true
      })
      .map((item) => ({
        code: item.currency,
        name: item.currencyName,
        color: item.color,
      }))
  }, [clientChartRows])

  const agingData = useMemo<AgingChartPoint[]>(() => (
    (summary?.overdue.aging_buckets || []).map((bucket, index) => ({
      ...bucket,
      color: AGING_COLORS[index] || '#64748b',
    }))
  ), [summary])

  const topRiskClients = useMemo(() => (
    [...clientRows]
      .filter((row) => row.overdue_count > 0)
      .sort((left, right) => (
        right.max_overdue_days - left.max_overdue_days
        || sumEntries(right.overdue_amount_by_currency) - sumEntries(left.overdue_amount_by_currency)
      ))
      .slice(0, 5)
  ), [clientRows])

  const syncedAt = summary?.synced_at
    ? new Date(summary.synced_at).toLocaleString()
    : '尚未同步'

  const metricLabel = clientMetric === 'overdue' ? '逾期金额' : '未回款金额'

  if (!active) return null

  return (
    <section className="receivables-page">
      <div className="dashboard-control-wrap receivables-action-row">
        <span>同步 {syncedAt}</span>
        <button className="btn-action primary receivables-sync-btn" onClick={handleSync} disabled={syncing || loading}>
          <RefreshCw size={16} className={syncing ? 'animate-spin' : ''} />
          {syncing ? '同步中' : '同步飞书数据'}
        </button>
      </div>

      {loading && !summary ? (
        <>
          <div className="receivables-kpi-grid">
            <Skeleton width="100%" height={130} />
            <Skeleton width="100%" height={130} />
          </div>
          <Skeleton width="100%" height={460} />
        </>
      ) : (
        <>
          <div className="receivables-kpi-grid">
            <ReceivableMetricCard
              title="未回款金额"
              icon={WalletCards}
              tone="amber"
              entries={summary?.outstanding.amount_by_currency || []}
              emptyText="暂无未回款"
              onOpen={() => openSummaryDetail('outstanding')}
            />
            <ReceivableMetricCard
              title="逾期账单金额"
              icon={AlertTriangle}
              tone="red"
              entries={summary?.overdue.amount_by_currency || []}
              emptyText="暂无逾期"
              onOpen={() => openSummaryDetail('overdue')}
            />
          </div>

          <div className="receivables-visual-grid">
            <div className="chart-card receivables-aging-card">
              <div className="dashboard-card-header receivables-card-head">
                <h3>账龄结构</h3>
              </div>
              <div className="receivables-aging-content">
                <div className="receivables-aging-body">
                  {agingData.length ? (
                    <>
                      <div className="receivables-aging-chart">
                        <ResponsiveContainer width="100%" height={180} minWidth={0}>
                          <PieChart>
                            <Tooltip content={<AgingTooltip />} />
                            <Pie
                              data={agingData}
                              dataKey="count"
                              nameKey="label"
                              innerRadius={46}
                              outerRadius={70}
                              paddingAngle={3}
                              stroke="none"
                            >
                              {agingData.map((item) => (
                                <Cell key={item.key} fill={item.color} />
                              ))}
                            </Pie>
                        </PieChart>
                      </ResponsiveContainer>
                    </div>
                      <div className="receivables-aging-legend">
                        {agingData.map((item) => (
                          <div key={item.key} className="receivables-aging-item">
                            <span className="receivables-aging-dot" style={{ background: item.color }} />
                            <strong>{item.label}</strong>
                          </div>
                        ))}
                      </div>
                    </>
                  ) : (
                    <div className="receivables-empty">暂无逾期</div>
                  )}
                </div>

                {!!topRiskClients.length && (
                  <div className="receivables-aging-risk">
                    <h4>TOP 风险客户</h4>
                    <div className="receivables-risk-list">
                      {topRiskClients.map((item, index) => {
                        const primaryEntry = getPrimaryEntry(item.overdue_amount_by_currency)
                        return (
                          <button key={item.client_name} type="button" onClick={() => openClient(item)}>
                            <span className="receivables-risk-rank">TOP {index + 1}</span>
                            <strong>{item.client_name}</strong>
                            <AmountStrip entries={primaryEntry ? [primaryEntry] : []} compact />
                            <span className="receivables-risk-days">{item.max_overdue_days} 天</span>
                          </button>
                        )
                      })}
                    </div>
                  </div>
                )}
            </div>
            </div>

            <div className="chart-card receivables-bi-card">
              <div className="dashboard-card-header receivables-card-head">
                <h3>客户金额排行</h3>
                <div className="dashboard-workbench-tabs">
                  {CLIENT_METRIC_OPTIONS.map((option) => (
                    <button
                      key={option.key}
                      type="button"
                      className={`dashboard-workbench-tab ${clientMetric === option.key ? 'active' : ''}`}
                      onClick={() => setClientMetric(option.key)}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
              </div>

              {!!chartCurrencies.length && (
                <div className="receivables-currency-legend">
                  {chartCurrencies.map((currency) => (
                    <span key={currency.code}>
                      <i style={{ background: currency.color }} />
                      {currency.code}
                    </span>
                  ))}
                </div>
              )}

              {clientChartRows.length ? (
                <div className="receivables-bar-chart">
                  <ResponsiveContainer width="100%" height="100%" minWidth={0}>
                    <BarChart
                      data={clientChartRows}
                      layout="vertical"
                      margin={{ top: 8, right: 24, left: 10, bottom: 8 }}
                    >
                      <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#e2e8f0" />
                      <XAxis
                        type="number"
                        axisLine={false}
                        tickLine={false}
                        tickFormatter={(value) => fmtAxisAmount(Number(value))}
                        stroke="#64748b"
                        fontSize={12}
                        domain={[0, (dataMax: number) => Math.max(dataMax * 1.3, dataMax + 1)]}
                      />
                      <YAxis
                        type="category"
                        dataKey="chart_label"
                        axisLine={false}
                        tickLine={false}
                        width={150}
                        stroke="#334155"
                        fontSize={12}
                      />
                      <Tooltip content={<ClientBarTooltip />} cursor={{ fill: 'rgba(15, 23, 42, 0.04)' }} />
                      <Bar
                        dataKey="amount"
                        name={metricLabel}
                        radius={[0, 9, 9, 0]}
                        cursor="pointer"
                        onClick={(value: unknown) => {
                          const point = getClientChartPoint(value)
                          if (point) openClient(point.row)
                        }}
                      >
                        {clientChartRows.map((item) => (
                          <Cell key={`${item.client_name}-${item.currency}`} fill={item.color} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              ) : (
                <div className="receivables-empty">暂无数据</div>
              )}
            </div>
          </div>
        </>
      )}

      {summaryDetail && (
        <SummaryDetailPopup
          title={summaryDetail.title}
          entries={
            summaryDetail.status === 'overdue'
              ? summary?.overdue.amount_by_currency || []
              : summary?.outstanding.amount_by_currency || []
          }
          rows={summaryDetailRows}
          loading={summaryDetailLoading}
          amountMode={summaryDetail.status}
          onClose={() => {
            setSummaryDetail(null)
            setSummaryDetailRows([])
          }}
        />
      )}

      {selectedClient && (
        <ClientReceivableDrawer
          client={selectedClient}
          rows={detailRows}
          filter={detailFilter}
          loading={detailLoading}
          onFilterChange={setDetailFilter}
          onClose={() => {
            setSelectedClient(null)
            setDetailRows([])
          }}
        />
      )}
    </section>
  )
}

interface ReceivableMetricCardProps {
  title: string
  icon: ComponentType<{ size?: number }>
  tone: 'amber' | 'red'
  entries: ReceivableCurrencyAmount[]
  emptyText: string
  onOpen: () => void
}

function ReceivableMetricCard({
  title,
  icon: Icon,
  tone,
  entries,
  emptyText,
  onOpen,
}: ReceivableMetricCardProps) {
  return (
    <button
      type="button"
      className={`dashboard-kpi-card receivables-metric-card ${tone}`}
      onClick={onOpen}
      aria-label={title}
    >
      <div className="dashboard-kpi-header receivables-metric-head">
        <span className="dashboard-kpi-label">{title}</span>
        <div className={`dashboard-kpi-icon receivables-metric-icon ${tone}`}>
          <Icon size={18} />
        </div>
      </div>
      <div className="dashboard-kpi-body receivables-metric-body">
        <AmountStrip entries={entries} emptyText={emptyText} size="large" />
      </div>
    </button>
  )
}

function SummaryDetailPopup({
  title,
  entries,
  rows,
  loading,
  amountMode,
  onClose,
}: {
  title: string
  entries: ReceivableCurrencyAmount[]
  rows: ReceivableTopOverdue[]
  loading: boolean
  amountMode: 'outstanding' | 'overdue'
  onClose: () => void
}) {
  const [currencyFilter, setCurrencyFilter] = useState('')
  const [searchText, setSearchText] = useState('')
  const currencyOptions = useMemo(() => {
    const seen = new Set<string>()
    const options: Array<{ code: string; label: string }> = []
    const appendCurrency = (code: string, label: string) => {
      const normalized = String(code || label || '').trim()
      if (!normalized || seen.has(normalized)) return
      seen.add(normalized)
      options.push({ code: normalized, label: label || normalized })
    }
    entries.forEach((item) => appendCurrency(item.currency_code || item.currency, item.currency || item.currency_code))
    rows.forEach((row) => appendCurrency(row.currency_code || row.currency, row.currency || row.currency_code))
    return options
  }, [entries, rows])
  const filteredRows = useMemo(() => {
    const keyword = searchText.trim().toLowerCase()
    return rows.filter((row) => {
      const rowCurrency = row.currency_code || row.currency
      if (currencyFilter && rowCurrency !== currencyFilter) return false
      if (!keyword) return true
      return [
        row.client_name,
        row.project_name,
        row.application_no,
        row.record_id,
        row.approval_status,
        row.approval_node,
        flowLabel(row.flow_type),
        row.due_date,
      ].some((value) => String(value || '').toLowerCase().includes(keyword))
    })
  }, [currencyFilter, rows, searchText])

  return (
    <div className="receivables-floating-backdrop" onClick={onClose}>
      <div className="receivables-floating-panel" onClick={(event) => event.stopPropagation()}>
        <div className="receivables-floating-head">
          <div>
            <span>{title}</span>
            <AmountStrip entries={entries} compact />
          </div>
          <button type="button" className="receivables-drawer-close" onClick={onClose}>
            <X size={18} />
          </button>
        </div>

        <div className="receivables-floating-toolbar">
          <div className="receivables-floating-currencies">
            <button
              type="button"
              className={!currencyFilter ? 'active' : ''}
              onClick={() => setCurrencyFilter('')}
            >
              全部
            </button>
            {currencyOptions.map((item) => (
              <button
                key={item.code}
                type="button"
                className={`${currencyFilter === item.code ? 'active' : ''} ${currencyTone(item.code)}`}
                onClick={() => setCurrencyFilter(item.code)}
              >
                {item.code}
              </button>
            ))}
          </div>
          <input
            type="search"
            value={searchText}
            onChange={(event) => setSearchText(event.target.value)}
            placeholder="搜索客户/项目/编号"
            aria-label="搜索流程"
          />
        </div>

        <div className="receivables-floating-list">
          {loading ? (
            <Skeleton width="100%" height={300} />
          ) : filteredRows.length ? filteredRows.map((row) => (
            <ReceivableFlowCard
              key={row.record_id || `${row.flow_type}-${row.project_name}-${row.due_date}`}
              row={row}
              amountMode={amountMode}
            />
          )) : (
            <div className="receivables-empty">暂无匹配流程</div>
          )}
        </div>
      </div>
    </div>
  )
}

function ReceivableFlowCard({
  row,
  amountMode = 'outstanding',
}: {
  row: ReceivableTopOverdue
  amountMode?: 'outstanding' | 'overdue'
}) {
  const amount = amountMode === 'overdue' ? row.overdue_amount : row.outstanding_amount
  return (
    <div className="receivables-detail-card">
      <div className="receivables-detail-top">
        <strong>{flowLabel(row.flow_type)}</strong>
        <span
          className="receivables-detail-no"
          title={row.application_no || row.record_id || '-'}
        >
          编号 {row.application_no || row.record_id || '-'}
        </span>
        <span>{row.due_date || '-'}</span>
      </div>
      <div className="receivables-detail-project">
        {row.client_name}
        {row.project_name ? ` · ${row.project_name}` : ''}
      </div>
      <div className="receivables-detail-status">
        <span>{row.approval_status || '-'}</span>
        <span>{row.approval_node || '-'}</span>
      </div>
      <div className="receivables-detail-amounts">
        <AmountStrip
          entries={[{
            currency_code: row.currency_code,
            currency: row.currency,
            amount,
            count: 1,
          }]}
          compact
        />
        {row.overdue_amount > 0 && (
          <span className="receivables-overdue-days">
            <Clock3 size={14} />
            {row.overdue_days} 天
          </span>
        )}
      </div>
    </div>
  )
}

function AmountStrip({
  entries,
  emptyText = '-',
  size = 'normal',
  compact = false,
}: {
  entries: ReceivableCurrencyAmount[]
  emptyText?: string
  size?: 'normal' | 'large'
  compact?: boolean
}) {
  if (!entries.length) {
    return <span className="currency-empty">{emptyText}</span>
  }
  return (
    <span className={`currency-strip ${size} ${compact ? 'compact' : ''}`}>
      {entries.map((item) => (
        <span key={item.currency_code || item.currency} className={`currency-chip ${currencyTone(item.currency_code || item.currency)}`}>
          <b>{item.currency_code || item.currency}</b>
          {fmtAmount(item.amount)}
        </span>
      ))}
    </span>
  )
}

function ClientBarTooltip({ active, payload }: ClientTooltipProps) {
  const item = active ? payload?.[0]?.payload : null
  if (!item) return null
  return (
    <div className="receivables-tooltip">
      <strong>{item.client_name}</strong>
      <AmountStrip entries={[{
        currency_code: item.currency,
        currency: item.currency,
        amount: item.amount,
        count: 1,
      }]} compact />
      <span>{item.flowText} 流程</span>
      <span>{item.overdueDays ? `${item.overdueDays} 天` : '-'}</span>
    </div>
  )
}

function AgingTooltip({ active, payload }: AgingTooltipProps) {
  const item = active ? payload?.[0]?.payload : null
  if (!item) return null
  return (
    <div className="receivables-tooltip">
      <strong>{item.label}</strong>
      <AmountStrip entries={item.amount_by_currency} compact />
    </div>
  )
}

function ClientReceivableDrawer({
  client,
  rows,
  filter,
  loading,
  onFilterChange,
  onClose,
}: {
  client: ReceivableClientSummaryRow
  rows: ReceivableTopOverdue[]
  filter: BillFilter
  loading: boolean
  onFilterChange: (filter: BillFilter) => void
  onClose: () => void
}) {
  return (
    <div className="receivables-drawer-backdrop" onClick={onClose}>
      <aside className="receivables-drawer" onClick={(event) => event.stopPropagation()}>
        <div className="receivables-drawer-header">
          <div>
            <span>客户穿透</span>
            <h3>{client.client_name}</h3>
          </div>
          <button type="button" className="receivables-drawer-close" onClick={onClose}>
            <X size={18} />
          </button>
        </div>

        <div className="receivables-drawer-metrics">
          <div>
            <span>未回款</span>
            <AmountStrip entries={client.outstanding_amount_by_currency} compact />
          </div>
          <div>
            <span>逾期</span>
            <AmountStrip entries={client.overdue_amount_by_currency} compact />
          </div>
        </div>

        <div className="dashboard-workbench-tabs">
          {FILTER_OPTIONS.map((option) => (
            <button
              key={option.key}
              type="button"
              className={`dashboard-workbench-tab ${filter === option.key ? 'active' : ''}`}
              onClick={() => onFilterChange(option.key)}
            >
              {option.label}
            </button>
          ))}
        </div>

        <div className="receivables-detail-list">
          {loading ? (
            <Skeleton width="100%" height={260} />
          ) : rows.length ? rows.map((row) => (
            <ReceivableFlowCard
              key={row.record_id || `${row.flow_type}-${row.project_name}-${row.due_date}`}
              row={row}
              amountMode={filter === 'overdue' ? 'overdue' : 'outstanding'}
            />
          )) : (
            <div className="receivables-empty">暂无记录</div>
          )}
        </div>
      </aside>
    </div>
  )
}
