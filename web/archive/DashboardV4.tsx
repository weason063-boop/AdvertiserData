import { useEffect, useMemo, useState, type ComponentType } from 'react'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Activity, BarChart3, DollarSign, TrendingDown, TrendingUp } from 'lucide-react'
import { ClientTrendModal } from './ClientTrendModal'
import { MonthTopClientsModal } from './MonthTopClientsModal'
import { Skeleton } from './Skeleton'
import { EmptyState } from './EmptyState'
import { InsightsPanel } from './InsightsPanel'
import { apiJson } from './apiClient'

type MetricMode = 'consumption' | 'fee'
type Granularity = 'month' | 'quarter'
type ViewMode = 'report' | 'analysis'
type SortMode = 'delta' | 'delta_pct' | 'rank'

interface DashboardData {
  stats: {
    consumption: number
    fee: number
    month: string
    consumption_mom: number
    fee_mom: number
    consumption_yoy: number
    fee_yoy: number
  } | null
  trend: Array<{ month: string; total_consumption: number; total_service_fee: number }>
  top_clients?: Array<{ client_name: string; consumption: number; service_fee: number }>
}

interface DashboardProps {
  data: DashboardData
  loading?: boolean
}

interface CompareClient {
  client_name: string
  consumption: number
  service_fee: number
  rank?: number
  prev_consumption?: number | null
  prev_service_fee?: number | null
  consumption_delta?: number | null
  fee_delta?: number | null
  rank_change?: number | null
}

interface CompareResp {
  month?: string
  quarter?: string
  prev_month?: string | null
  prev_quarter?: string | null
  clients: CompareClient[]
}

interface SeriesPoint {
  key: string
  label: string
  total_consumption: number
  total_service_fee: number
}

interface NormalizedClient extends CompareClient {
  rank: number
}

const fmtMoney = (value: number) => new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  maximumFractionDigits: 0,
}).format(value)

const fmtPct = (value: number) => `${value >= 0 ? '+' : '-'}${Math.abs(value).toFixed(1)}%`

const fmtCompact = (value: number) => (Math.abs(value) >= 1000
  ? `$${(value / 1000).toFixed(1)}k`
  : `$${value.toFixed(0)}`)

const prevYearMonth = (month: string) => {
  const [y, m] = month.split('-').map(Number)
  return `${y - 1}-${String(m).padStart(2, '0')}`
}

const quarterKey = (month: string) => {
  const [yearText, monthText] = month.split('-')
  const year = Number(yearText)
  const m = Number(monthText)
  if (m >= 3 && m <= 5) return `${year}-Q1`
  if (m >= 6 && m <= 8) return `${year}-Q2`
  if (m >= 9 && m <= 11) return `${year}-Q3`
  if (m === 12) return `${year}-Q4`
  return `${year - 1}-Q4`
}

const prevYearQuarter = (quarter: string) => {
  const [yearText, qText] = quarter.split('-Q')
  return `${Number(yearText) - 1}-Q${Number(qText)}`
}

const windowOpts = (granularity: Granularity) => (granularity === 'month' ? [6, 12] : [1, 2, 3, 4])

export function Dashboard({ data, loading }: DashboardProps) {
  const { stats, trend, top_clients = [] } = data
  const [metric, setMetric] = useState<MetricMode>('consumption')
  const [granularity, setGranularity] = useState<Granularity>('month')
  const [windowSize, setWindowSize] = useState<number>(12)
  const [view, setView] = useState<ViewMode>('report')
  const [sort, setSort] = useState<SortMode>('delta')
  const [selectedClient, setSelectedClient] = useState<string | null>(null)
  const [selectedMonth, setSelectedMonth] = useState<string | null>(null)
  const [compare, setCompare] = useState<CompareResp | null>(null)

  const monthSeries = useMemo<SeriesPoint[]>(() => trend.map((item) => ({
    key: item.month,
    label: item.month,
    total_consumption: item.total_consumption,
    total_service_fee: item.total_service_fee,
  })), [trend])

  const quarterSeries = useMemo<SeriesPoint[]>(() => {
    const map = new Map<string, SeriesPoint>()
    monthSeries.forEach((item) => {
      const key = quarterKey(item.key)
      const current = map.get(key)
      if (current) {
        current.total_consumption += item.total_consumption
        current.total_service_fee += item.total_service_fee
      } else {
        map.set(key, {
          key,
          label: key,
          total_consumption: item.total_consumption,
          total_service_fee: item.total_service_fee,
        })
      }
    })
    return [...map.values()].sort((a, b) => a.key.localeCompare(b.key))
  }, [monthSeries])

  const series = granularity === 'month' ? monthSeries : quarterSeries
  const currentPeriod = series.length ? series[series.length - 1] : null

  useEffect(() => {
    const options = windowOpts(granularity)
    if (!options.includes(windowSize)) {
      setWindowSize(options[options.length - 1])
    }
  }, [granularity, windowSize])

  useEffect(() => {
    if (!currentPeriod) return
    const controller = new AbortController()
    const path = granularity === 'month'
      ? `/api/dashboard/month/${encodeURIComponent(currentPeriod.key)}/top-clients?limit=10&compare_prev=true`
      : `/api/dashboard/quarter/${encodeURIComponent(currentPeriod.key)}/top-clients?limit=10&compare_prev=true`

    apiJson<CompareResp>(path, { signal: controller.signal }, { throwOnHttpError: false })
      .then(({ data: payload, res }) => {
        if (!res.ok) return
        if (payload?.clients) setCompare(payload)
      })
      .catch(() => undefined)

    return () => controller.abort()
  }, [currentPeriod?.key, granularity])

  const lookup = useMemo(() => new Map(series.map((item) => [item.key, item])), [series])
  const windowed = useMemo(() => series.slice(-Math.min(windowSize, series.length)), [series, windowSize])

  const trendData = useMemo(() => windowed.map((item) => {
    const prevKey = granularity === 'month' ? prevYearMonth(item.key) : prevYearQuarter(item.key)
    const prev = lookup.get(prevKey)
    return {
      periodKey: item.key,
      label: item.label,
      curr: metric === 'consumption' ? item.total_consumption : item.total_service_fee,
      prev: prev ? (metric === 'consumption' ? prev.total_consumption : prev.total_service_fee) : null as number | null,
    }
  }), [windowed, granularity, lookup, metric])

  const hasYoY = trendData.some((item) => item.prev !== null)

  if (loading) {
    return (
      <div className="dashboard">
        <div className="chart-card"><Skeleton width="100%" height={54} /></div>
        <div className="dashboard-kpi-grid">
          <div className="stat-card"><Skeleton width="100%" height={120} /></div>
          <div className="stat-card"><Skeleton width="100%" height={120} /></div>
        </div>
        <div className="chart-card"><Skeleton width="100%" height={320} /></div>
      </div>
    )
  }

  if (!stats) {
    return (
      <div style={{ height: 'calc(100vh - 180px)' }}>
        <EmptyState
          title="暂无账单数据"
          description="请上传消耗数据开始分析"
          icon={<BarChart3 size={48} strokeWidth={1} />}
        />
      </div>
    )
  }

  const clients: NormalizedClient[] = compare?.clients?.length
    ? compare.clients.map((item, i) => ({ ...item, rank: item.rank ?? i + 1 }))
    : top_clients.map((item, i) => ({
      ...item,
      rank: i + 1,
      prev_consumption: null,
      prev_service_fee: null,
      consumption_delta: null,
      fee_delta: null,
      rank_change: null,
    }))

  const total = metric === 'consumption' ? stats.consumption : stats.fee
  const currentLabel = currentPeriod?.label || stats.month
  const prevLabel = granularity === 'month' ? (compare?.prev_month || '') : (compare?.prev_quarter || '')

  const compareRows = [...clients].map((item, i) => {
    const curr = metric === 'consumption' ? item.consumption : item.service_fee
    const prev = metric === 'consumption' ? (item.prev_consumption ?? null) : (item.prev_service_fee ?? null)
    const delta = metric === 'consumption' ? (item.consumption_delta ?? null) : (item.fee_delta ?? null)
    return {
      name: item.client_name,
      rank: item.rank ?? i + 1,
      curr,
      prev,
      delta,
      deltaPct: prev && prev !== 0 && delta !== null ? (delta / prev) * 100 : null as number | null,
      rankChange: item.rank_change ?? null as number | null,
      share: total > 0 ? (curr / total) * 100 : 0,
    }
  })

  const sortable = (value: number | null) => (typeof value === 'number' ? value : Number.NEGATIVE_INFINITY)
  if (sort === 'delta') compareRows.sort((a, b) => sortable(b.delta) - sortable(a.delta))
  if (sort === 'delta_pct') compareRows.sort((a, b) => sortable(b.deltaPct) - sortable(a.deltaPct))
  if (sort === 'rank') compareRows.sort((a, b) => sortable(b.rankChange) - sortable(a.rankChange))

  return (
    <div className="dashboard">
      <div className="chart-card dashboard-control-bar">
        <div className="dashboard-control-main">
          <div className="dashboard-control-item">
            <span className="dashboard-control-title">指标</span>
            <div className="dashboard-chip-group">
              <button type="button" className={`dashboard-chip ${metric === 'consumption' ? 'active' : ''}`} onClick={() => setMetric('consumption')}>消耗金额</button>
              <button type="button" className={`dashboard-chip ${metric === 'fee' ? 'active' : ''}`} onClick={() => setMetric('fee')}>服务费</button>
            </div>
          </div>

          <div className="dashboard-control-item">
            <span className="dashboard-control-title">时间维度</span>
            <div className="dashboard-chip-group">
              <button type="button" className={`dashboard-chip ${granularity === 'month' ? 'active' : ''}`} onClick={() => setGranularity('month')}>月度</button>
              <button type="button" className={`dashboard-chip ${granularity === 'quarter' ? 'active' : ''}`} onClick={() => setGranularity('quarter')}>季度</button>
            </div>
          </div>

          <div className="dashboard-control-item">
            <span className="dashboard-control-title">{granularity === 'month' ? '月度窗口' : '季度窗口'}</span>
            <div className="dashboard-chip-group">
              {windowOpts(granularity).map((window) => (
                <button key={window} type="button" className={`dashboard-chip ${windowSize === window ? 'active' : ''}`} onClick={() => setWindowSize(window)}>
                  {granularity === 'month' ? `${window}个月` : `${window}季度`}
                </button>
              ))}
            </div>
          </div>

        </div>

        <div className="dashboard-control-side">
          <div className="dashboard-control-item dashboard-control-item-right">
            <span className="dashboard-control-title">视图</span>
            <div className="dashboard-chip-group">
              <button type="button" className={`dashboard-chip ${view === 'report' ? 'active' : ''}`} onClick={() => setView('report')}>汇报</button>
              <button type="button" className={`dashboard-chip ${view === 'analysis' ? 'active' : ''}`} onClick={() => setView('analysis')}>分析</button>
            </div>
          </div>
        </div>
      </div>

      <div className="dashboard-kpi-grid">
        <StatCard title="本期总消耗" value={stats.consumption} mom={stats.consumption_mom} yoy={stats.consumption_yoy} icon={Activity} color="blue" />
        <StatCard title="本期服务费" value={stats.fee} mom={stats.fee_mom} yoy={stats.fee_yoy} icon={DollarSign} color="purple" />
      </div>

      <div className={view === 'report' ? 'dashboard-report-grid' : 'dashboard-analysis-grid'}>
        <div className="chart-card dashboard-main-trend-card">
          <div className="dashboard-card-header">
            <h3>{metric === 'consumption' ? '消耗金额' : '服务费'}趋势对比</h3>
          </div>

          <div className="chart-container">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart
                data={trendData}
                onClick={(event: unknown) => {
                  if (granularity !== 'month') return
                  const payload = (event as { activePayload?: Array<{ payload?: { periodKey?: string } }> } | undefined)?.activePayload
                  const key = payload?.[0]?.payload?.periodKey
                  if (key) setSelectedMonth(key)
                }}
              >
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E2E8F0" />
                <XAxis dataKey="label" axisLine={false} tickLine={false} fontSize={12} tickMargin={14} stroke="#64748B" />
                <YAxis axisLine={false} tickLine={false} fontSize={12} tickFormatter={(value) => fmtCompact(Number(value))} stroke="#64748B" />
                <Tooltip formatter={(value: unknown, name: string | number | undefined) => [fmtMoney(Number(value || 0)), name === 'curr' ? '本期' : '去年同期']} />
                <Line type="monotone" dataKey="curr" stroke="#4F46E5" strokeWidth={3} dot={{ r: 3 }} />
                {hasYoY && <Line type="monotone" dataKey="prev" stroke="#0EA5E9" strokeWidth={2.5} strokeDasharray="6 4" dot={false} />}
              </LineChart>
            </ResponsiveContainer>
          </div>

          {!hasYoY && <div className="dashboard-hint">暂无去年同期数据，已隐藏同比虚线</div>}
          {granularity === 'quarter' && <div className="dashboard-hint">季度规则：Q1=3-5月，Q2=6-8月，Q3=9-11月，Q4=12月-次年2月</div>}
        </div>

        {view === 'report' && (
          <div className="chart-card dashboard-top-share-card">
            <div className="dashboard-card-header"><h3>{currentLabel} TOP 客户贡献</h3></div>
            <div className="top-share-list">
              {compareRows.slice(0, 6).map((row, i) => (
                <button type="button" key={row.name} className="top-share-row" onClick={() => setSelectedClient(row.name)}>
                  <div className="top-share-main"><span>{i + 1}. {row.name}</span><span>{fmtMoney(row.curr)}</span></div>
                  <div className="top-share-track"><div className="top-share-fill" style={{ width: `${Math.min(row.share, 100)}%` }} /></div>
                  <span className="top-share-pct">{row.share.toFixed(1)}%</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {view === 'analysis' && (
          <div className="chart-card dashboard-top-compare-card">
            <div className="dashboard-card-header">
              <h3>{currentLabel} TOP 客户对比</h3>
              <div className="dashboard-chip-group">
                <button type="button" className={`dashboard-chip ${sort === 'delta_pct' ? 'active' : ''}`} onClick={() => setSort('delta_pct')}>按增幅</button>
                <button type="button" className={`dashboard-chip ${sort === 'delta' ? 'active' : ''}`} onClick={() => setSort('delta')}>按增量</button>
                <button type="button" className={`dashboard-chip ${sort === 'rank' ? 'active' : ''}`} onClick={() => setSort('rank')}>按排名变化</button>
              </div>
            </div>

            <div className="dashboard-hint" style={{ marginBottom: '0.55rem' }}>
              对比基准：{prevLabel || (granularity === 'month' ? '上月无可用数据' : '上季度无可用数据')}
            </div>

            <div className="dashboard-compare-table-wrap">
              <table className="dashboard-compare-table">
                <thead>
                  <tr>
                    <th>排名</th>
                    <th>客户</th>
                    <th>本期</th>
                    <th>{granularity === 'month' ? '上月' : '上季度'}</th>
                    <th>增量</th>
                    <th>增幅</th>
                    <th>排名变化</th>
                    <th>占比</th>
                  </tr>
                </thead>
                <tbody>
                  {compareRows.map((row) => (
                    <tr key={row.name} onClick={() => setSelectedClient(row.name)}>
                      <td>{row.rank}</td>
                      <td className="client-col">{row.name}</td>
                      <td>{fmtMoney(row.curr)}</td>
                      <td>{row.prev === null ? '—' : fmtMoney(row.prev)}</td>
                      <td className={row.delta !== null && row.delta >= 0 ? 'positive' : 'negative'}>{row.delta === null ? '—' : fmtMoney(row.delta)}</td>
                      <td className={row.deltaPct !== null && row.deltaPct >= 0 ? 'positive' : 'negative'}>{row.deltaPct === null ? '—' : fmtPct(row.deltaPct)}</td>
                      <td className={row.rankChange !== null && row.rankChange >= 0 ? 'positive' : 'negative'}>{row.rankChange === null ? '—' : row.rankChange > 0 ? `+${row.rankChange}` : `${row.rankChange}`}</td>
                      <td>{row.share.toFixed(1)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>

      {view === 'analysis' && <div className="dashboard-insights"><InsightsPanel /></div>}
      {selectedClient && <ClientTrendModal clientName={selectedClient} onClose={() => setSelectedClient(null)} />}
      {selectedMonth && <MonthTopClientsModal month={selectedMonth} onClose={() => setSelectedMonth(null)} />}
    </div>
  )
}

interface StatCardProps {
  title: string
  value: number
  mom: number
  yoy: number
  icon: ComponentType<{ size?: number }>
  color: 'blue' | 'purple'
}

const StatCard = ({ title, value, mom, yoy, icon: Icon, color }: StatCardProps) => (
  <div className="stat-card dashboard-stat-card">
    <div className="dashboard-stat-inline">
      <div className="dashboard-stat-left">
        <span className="stat-title">{title}</span>
        <span className="stat-value">{fmtMoney(value)}</span>
      </div>

      <div className="dashboard-stat-deltas">
        <div className={`stat-change ${mom >= 0 ? 'up' : 'down'}`}>
          {mom >= 0 ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
          <span>环比 {fmtPct(mom)}</span>
        </div>
        <div className={`stat-change ${yoy >= 0 ? 'up' : 'down'}`}>
          <span>同比 {fmtPct(yoy)}</span>
        </div>
      </div>

      <div className={`stat-icon ${color}`}>
        <Icon size={17} />
      </div>
    </div>
  </div>
)
