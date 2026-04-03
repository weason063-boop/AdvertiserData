import { useEffect, useMemo, useState, type ComponentType } from 'react'
import { Area, AreaChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Activity, BarChart3, DollarSign, TrendingDown, TrendingUp } from 'lucide-react'
import { ClientTrendModal } from './ClientTrendModal'
import { MonthTopClientsModal } from './MonthTopClientsModal'
import { Skeleton } from './Skeleton'
import { EmptyState } from './EmptyState'
import { InsightsPanel } from './InsightsPanel'
import { apiJson } from './apiClient'

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
  trend: Array<{
    month: string
    total_consumption: number
    total_service_fee: number
  }>
  top_clients?: Array<{
    client_name: string
    consumption: number
    service_fee: number
  }>
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

interface CompareResponse {
  month: string
  prev_month?: string | null
  clients: CompareClient[]
}

type MetricMode = 'consumption' | 'fee'
type WindowSize = 3 | 6 | 12
type ViewMode = 'report' | 'analysis'
type CompareSort = 'delta' | 'delta_pct' | 'rank'

const formatCurrency = (val: number) => new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  maximumFractionDigits: 0,
}).format(val)

const formatCompact = (val: number) => {
  if (Math.abs(val) >= 1000000) return `$${(val / 1000000).toFixed(1)}m`
  if (Math.abs(val) >= 1000) return `$${(val / 1000).toFixed(1)}k`
  return `$${val.toFixed(0)}`
}

const formatPercent = (val: number) => `${val >= 0 ? '+' : '-'}${Math.abs(val).toFixed(1)}%`

const getPrevYearMonth = (month: string) => {
  const [year, mon] = month.split('-').map(Number)
  if (!Number.isFinite(year) || !Number.isFinite(mon)) return month
  return `${year - 1}-${String(mon).padStart(2, '0')}`
}

const getTrendMetric = (item: DashboardData['trend'][number], metric: MetricMode) =>
  metric === 'consumption' ? item.total_consumption : item.total_service_fee

const getClientMetric = (item: CompareClient, metric: MetricMode) =>
  metric === 'consumption' ? item.consumption : item.service_fee

const getClientPrevMetric = (item: CompareClient, metric: MetricMode) =>
  metric === 'consumption' ? (item.prev_consumption ?? null) : (item.prev_service_fee ?? null)

const getClientDeltaMetric = (item: CompareClient, metric: MetricMode) =>
  metric === 'consumption' ? (item.consumption_delta ?? null) : (item.fee_delta ?? null)

export function Dashboard({ data, loading }: DashboardProps) {
  const { stats, trend, top_clients = [] } = data
  const [selectedClient, setSelectedClient] = useState<string | null>(null)
  const [selectedMonth, setSelectedMonth] = useState<string | null>(null)
  const [metricMode, setMetricMode] = useState<MetricMode>('consumption')
  const [windowSize, setWindowSize] = useState<WindowSize>(12)
  const [viewMode, setViewMode] = useState<ViewMode>('report')
  const [compareSort, setCompareSort] = useState<CompareSort>('delta')
  const [compareData, setCompareData] = useState<CompareResponse | null>(null)

  useEffect(() => {
    if (!stats?.month) return
    const controller = new AbortController()
    apiJson<CompareResponse>(`/api/dashboard/month/${encodeURIComponent(stats.month)}/top-clients?limit=10&compare_prev=true`, {
      signal: controller.signal,
    }, {
      throwOnHttpError: false,
    })
      .then(({ data: payload, res }) => {
        if (!res.ok) return
        if (payload && Array.isArray(payload.clients)) setCompareData(payload)
      })
      .catch(() => undefined)
    return () => controller.abort()
  }, [stats?.month])

  const trendLookup = useMemo(() => {
    const map = new Map<string, DashboardData['trend'][number]>()
    trend.forEach(item => map.set(item.month, item))
    return map
  }, [trend])

  const trendWindow = useMemo(() => trend.slice(-Math.min(windowSize, trend.length)), [trend, windowSize])

  const trendData = useMemo(() => trendWindow.map(item => {
    const prev = trendLookup.get(getPrevYearMonth(item.month))
    return {
      month: item.month,
      current: getTrendMetric(item, metricMode),
      prevYear: prev ? getTrendMetric(prev, metricMode) : null as number | null,
    }
  }), [trendLookup, trendWindow, metricMode])

  const hasYoY = trendData.some(item => item.prevYear !== null)

  const clients: CompareClient[] = useMemo(() => {
    if (compareData?.clients?.length) return compareData.clients
    return top_clients.map((item, idx) => ({ ...item, rank: idx + 1 }))
  }, [compareData, top_clients])

  if (loading) {
    return (
      <div className="dashboard">
        <div className="chart-card"><Skeleton width="100%" height={46} /></div>
        <div className="dashboard-kpi-grid">
          <div className="stat-card"><Skeleton width="100%" height={160} /></div>
          <div className="stat-card"><Skeleton width="100%" height={160} /></div>
        </div>
        <div className="chart-card"><Skeleton width="100%" height={320} /></div>
      </div>
    )
  }

  if (!stats) {
    return (
      <div style={{ height: 'calc(100vh - 180px)' }}>
        <EmptyState title="暂无账单数据" description="请上传消耗数据开始分析" icon={<BarChart3 size={48} strokeWidth={1} />} />
      </div>
    )
  }

  const totalMetric = metricMode === 'consumption' ? stats.consumption : stats.fee

  const topShareRows = clients.slice(0, 6).map(item => {
    const value = getClientMetric(item, metricMode)
    return {
      name: item.client_name,
      value,
      share: totalMetric > 0 ? (value / totalMetric) * 100 : 0,
    }
  })

  const compareRows = [...clients].map((item, idx) => {
    const current = getClientMetric(item, metricMode)
    const prev = getClientPrevMetric(item, metricMode)
    const delta = getClientDeltaMetric(item, metricMode)
    return {
      name: item.client_name,
      rank: item.rank ?? idx + 1,
      current,
      prev,
      delta,
      deltaPct: prev && prev !== 0 && delta !== null ? (delta / prev) * 100 : null as number | null,
      rankChange: item.rank_change ?? null as number | null,
      share: totalMetric > 0 ? (current / totalMetric) * 100 : 0,
    }
  })

  const sortable = (v: number | null) => typeof v === 'number' ? v : Number.NEGATIVE_INFINITY
  if (compareSort === 'delta') compareRows.sort((a, b) => sortable(b.delta) - sortable(a.delta))
  if (compareSort === 'delta_pct') compareRows.sort((a, b) => sortable(b.deltaPct) - sortable(a.deltaPct))
  if (compareSort === 'rank') compareRows.sort((a, b) => sortable(b.rankChange) - sortable(a.rankChange))

  return (
    <div className="dashboard">
      <div className="chart-card dashboard-control-bar">
        <div className="dashboard-chip-group">
          <button type="button" className={`dashboard-chip ${metricMode === 'consumption' ? 'active' : ''}`} onClick={() => setMetricMode('consumption')}>消耗金额</button>
          <button type="button" className={`dashboard-chip ${metricMode === 'fee' ? 'active' : ''}`} onClick={() => setMetricMode('fee')}>服务费</button>
        </div>
        <div className="dashboard-chip-group">
          {[3, 6, 12].map((w) => (
            <button key={w} type="button" className={`dashboard-chip ${windowSize === w ? 'active' : ''}`} onClick={() => setWindowSize(w as WindowSize)}>{w}个月</button>
          ))}
        </div>
        <div className="dashboard-chip-group">
          <button type="button" className={`dashboard-chip ${viewMode === 'report' ? 'active' : ''}`} onClick={() => setViewMode('report')}>汇报</button>
          <button type="button" className={`dashboard-chip ${viewMode === 'analysis' ? 'active' : ''}`} onClick={() => setViewMode('analysis')}>分析</button>
        </div>
      </div>

      <div className="dashboard-kpi-grid">
        <StatCard title="本月总消耗" value={stats.consumption} mom={stats.consumption_mom} yoy={stats.consumption_yoy} icon={Activity} color="blue" sparkline={trendWindow.map(item => item.total_consumption)} month={stats.month} />
        <StatCard title="本月服务费" value={stats.fee} mom={stats.fee_mom} yoy={stats.fee_yoy} icon={DollarSign} color="purple" sparkline={trendWindow.map(item => item.total_service_fee)} month={stats.month} />
      </div>

      <div className={viewMode === 'report' ? 'dashboard-report-grid' : 'dashboard-analysis-grid'}>
        <div className="chart-card dashboard-main-trend-card">
          <div className="dashboard-card-header"><h3>{metricMode === 'consumption' ? '消耗金额' : '服务费'}趋势对比</h3></div>
          <div className="chart-container">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart
                data={trendData}
                onClick={(event: { activeLabel?: string | number } | undefined) => {
                  if (event?.activeLabel) setSelectedMonth(String(event.activeLabel))
                }}
              >
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E2E8F0" />
                <XAxis dataKey="month" axisLine={false} tickLine={false} fontSize={12} tickMargin={14} stroke="#64748B" />
                <YAxis axisLine={false} tickLine={false} fontSize={12} tickFormatter={(val) => formatCompact(Number(val))} stroke="#64748B" />
                <Tooltip formatter={(value: unknown, name: string | number | undefined) => [formatCurrency(Number(value || 0)), name === 'current' ? '本期' : '去年同期']} />
                <Line type="monotone" dataKey="current" stroke="#4F46E5" strokeWidth={3} dot={{ r: 3 }} />
                {hasYoY && <Line type="monotone" dataKey="prevYear" stroke="#0EA5E9" strokeWidth={2.5} strokeDasharray="6 4" dot={false} />}
              </LineChart>
            </ResponsiveContainer>
          </div>
          {!hasYoY && <div className="dashboard-hint">暂无去年同期数据，已隐藏同比虚线</div>}
        </div>

        {viewMode === 'report' && (
          <div className="chart-card dashboard-top-share-card">
            <div className="dashboard-card-header"><h3>{stats.month} TOP 客户贡献</h3></div>
            <div className="top-share-list">
              {topShareRows.map((row, idx) => (
                <button type="button" key={row.name} className="top-share-row" onClick={() => setSelectedClient(row.name)}>
                  <div className="top-share-main"><span>{idx + 1}. {row.name}</span><span>{formatCurrency(row.value)}</span></div>
                  <div className="top-share-track"><div className="top-share-fill" style={{ width: `${Math.min(row.share, 100)}%` }} /></div>
                  <span className="top-share-pct">{row.share.toFixed(1)}%</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {viewMode === 'analysis' && (
          <div className="chart-card dashboard-top-compare-card">
            <div className="dashboard-card-header">
              <h3>{stats.month} TOP 客户对比</h3>
              <div className="dashboard-chip-group">
                <button type="button" className={`dashboard-chip ${compareSort === 'delta_pct' ? 'active' : ''}`} onClick={() => setCompareSort('delta_pct')}>按增幅</button>
                <button type="button" className={`dashboard-chip ${compareSort === 'delta' ? 'active' : ''}`} onClick={() => setCompareSort('delta')}>按增量</button>
                <button type="button" className={`dashboard-chip ${compareSort === 'rank' ? 'active' : ''}`} onClick={() => setCompareSort('rank')}>按排名变化</button>
              </div>
            </div>
            <div className="dashboard-compare-table-wrap">
              <table className="dashboard-compare-table">
                <thead><tr><th>排名</th><th>客户</th><th>本月</th><th>上月</th><th>增量</th><th>增幅</th><th>排名变化</th><th>占比</th></tr></thead>
                <tbody>
                  {compareRows.map((row) => (
                    <tr key={row.name} onClick={() => setSelectedClient(row.name)}>
                      <td>{row.rank}</td><td className="client-col">{row.name}</td><td>{formatCurrency(row.current)}</td>
                      <td>{row.prev === null ? '—' : formatCurrency(row.prev)}</td>
                      <td className={row.delta !== null && row.delta >= 0 ? 'positive' : 'negative'}>{row.delta === null ? '—' : formatCurrency(row.delta)}</td>
                      <td className={row.deltaPct !== null && row.deltaPct >= 0 ? 'positive' : 'negative'}>{row.deltaPct === null ? '—' : formatPercent(row.deltaPct)}</td>
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

      {viewMode === 'analysis' && <div className="dashboard-insights"><InsightsPanel /></div>}

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
  sparkline: number[]
  month: string
}

const StatCard = ({ title, value, mom, yoy, icon: Icon, color, sparkline, month }: StatCardProps) => (
  <div className="stat-card dashboard-stat-card">
    <div className="stat-header">
      <span className="stat-title">{title}</span>
      <div className={`stat-icon ${color}`}><Icon size={20} /></div>
    </div>
    <div className="stat-value">{formatCurrency(value)}</div>
    <div className="dashboard-stat-meta">统计月份：{month}</div>
    <div className="stat-footer">
      <div className={`stat-change ${mom >= 0 ? 'up' : 'down'}`}>{mom >= 0 ? <TrendingUp size={14} /> : <TrendingDown size={14} />}<span>环比 {formatPercent(mom)}</span></div>
      <div className={`stat-change ${yoy >= 0 ? 'up' : 'down'}`}><span>同比 {formatPercent(yoy)}</span></div>
    </div>
    <div className="dashboard-sparkline">
      <ResponsiveContainer width="100%" height={48}>
        <AreaChart data={sparkline.map((value, idx) => ({ idx, value }))}>
          <Area type="monotone" dataKey="value" stroke={color === 'blue' ? '#3B82F6' : '#8B5CF6'} fillOpacity={0.15} fill={color === 'blue' ? '#60A5FA' : '#A78BFA'} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  </div>
)
