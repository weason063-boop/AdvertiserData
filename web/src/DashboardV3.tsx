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
interface DashboardProps { data: DashboardData; loading?: boolean }
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

const fmtMoney = (v: number) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(v)
const fmtPct = (v: number) => `${v >= 0 ? '+' : '-'}${Math.abs(v).toFixed(1)}%`
const fmtCompact = (v: number) => Math.abs(v) >= 1000 ? `$${(v / 1000).toFixed(1)}k` : `$${v.toFixed(0)}`
const prevYearMonth = (m: string) => { const [y, mm] = m.split('-').map(Number); return `${y - 1}-${String(mm).padStart(2, '0')}` }
const quarterKey = (m: string) => {
  const [ys, ms] = m.split('-'); const y = Number(ys); const mm = Number(ms)
  if (mm >= 3 && mm <= 5) return `${y}-Q1`
  if (mm >= 6 && mm <= 8) return `${y}-Q2`
  if (mm >= 9 && mm <= 11) return `${y}-Q3`
  if (mm === 12) return `${y}-Q4`
  return `${y - 1}-Q4`
}
const prevYearQuarter = (q: string) => { const [ys, qs] = q.split('-Q'); return `${Number(ys) - 1}-Q${Number(qs)}` }
const windowOpts = (g: Granularity) => g === 'month' ? [6, 12] : [1, 2, 3, 4]

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

  const monthSeries = useMemo<SeriesPoint[]>(() => trend.map(t => ({
    key: t.month, label: t.month, total_consumption: t.total_consumption, total_service_fee: t.total_service_fee,
  })), [trend])

  const quarterSeries = useMemo<SeriesPoint[]>(() => {
    const map = new Map<string, SeriesPoint>()
    monthSeries.forEach(p => {
      const k = quarterKey(p.key); const cur = map.get(k)
      if (cur) { cur.total_consumption += p.total_consumption; cur.total_service_fee += p.total_service_fee }
      else map.set(k, { key: k, label: k, total_consumption: p.total_consumption, total_service_fee: p.total_service_fee })
    })
    return [...map.values()].sort((a, b) => a.key.localeCompare(b.key))
  }, [monthSeries])

  const series = granularity === 'month' ? monthSeries : quarterSeries
  const currentPeriod = series.length ? series[series.length - 1] : null

  useEffect(() => {
    const opts = windowOpts(granularity)
    if (!opts.includes(windowSize)) setWindowSize(opts[opts.length - 1])
  }, [granularity, windowSize])

  useEffect(() => {
    if (!currentPeriod) return
    const controller = new AbortController()
    const path = granularity === 'month'
      ? `/api/dashboard/month/${encodeURIComponent(currentPeriod.key)}/top-clients?limit=10&compare_prev=true`
      : `/api/dashboard/quarter/${encodeURIComponent(currentPeriod.key)}/top-clients?limit=10&compare_prev=true`
    apiJson<CompareResp>(path, { signal: controller.signal }, { throwOnHttpError: false })
      .then(({ data: p, res }) => {
        if (!res.ok) return
        if (p?.clients) setCompare(p)
      })
      .catch(() => undefined)
    return () => controller.abort()
  }, [currentPeriod?.key, granularity])

  const lookup = useMemo(() => new Map(series.map(s => [s.key, s])), [series])
  const windowed = useMemo(() => series.slice(-Math.min(windowSize, series.length)), [series, windowSize])
  const trendData = useMemo(() => windowed.map(s => {
    const prevKey = granularity === 'month' ? prevYearMonth(s.key) : prevYearQuarter(s.key)
    const prev = lookup.get(prevKey)
    return { periodKey: s.key, label: s.label, curr: metric === 'consumption' ? s.total_consumption : s.total_service_fee, prev: prev ? (metric === 'consumption' ? prev.total_consumption : prev.total_service_fee) : null as number | null }
  }), [windowed, granularity, lookup, metric])
  const hasYoY = trendData.some(t => t.prev !== null)

  if (loading) {
    return <div className="dashboard"><div className="chart-card"><Skeleton width="100%" height={54} /></div><div className="dashboard-kpi-grid"><div className="stat-card"><Skeleton width="100%" height={160} /></div><div className="stat-card"><Skeleton width="100%" height={160} /></div></div><div className="chart-card"><Skeleton width="100%" height={320} /></div></div>
  }
  if (!stats) return <div style={{ height: 'calc(100vh - 180px)' }}><EmptyState title="暂无账单数据" description="请上传消耗数据开始分析" icon={<BarChart3 size={48} strokeWidth={1} />} /></div>

  const clients: NormalizedClient[] = compare?.clients?.length
    ? compare.clients.map((c, i) => ({ ...c, rank: c.rank ?? i + 1 }))
    : top_clients.map((c, i) => ({
      ...c,
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

  const compareRows = [...clients].map((c, i) => {
    const curr = metric === 'consumption' ? c.consumption : c.service_fee
    const prev = metric === 'consumption' ? (c.prev_consumption ?? null) : (c.prev_service_fee ?? null)
    const delta = metric === 'consumption' ? (c.consumption_delta ?? null) : (c.fee_delta ?? null)
    return { name: c.client_name, rank: c.rank ?? i + 1, curr, prev, delta, deltaPct: prev && prev !== 0 && delta !== null ? (delta / prev) * 100 : null as number | null, rankChange: c.rank_change ?? null as number | null, share: total > 0 ? curr / total * 100 : 0 }
  })
  const sval = (v: number | null) => typeof v === 'number' ? v : Number.NEGATIVE_INFINITY
  if (sort === 'delta') compareRows.sort((a, b) => sval(b.delta) - sval(a.delta))
  if (sort === 'delta_pct') compareRows.sort((a, b) => sval(b.deltaPct) - sval(a.deltaPct))
  if (sort === 'rank') compareRows.sort((a, b) => sval(b.rankChange) - sval(a.rankChange))

  return (
    <div className="dashboard">
      <div className="chart-card dashboard-control-bar">
        <div className="dashboard-control-grid">
          <div className="dashboard-control-item"><span className="dashboard-control-title">指标</span><div className="dashboard-chip-group"><button type="button" className={`dashboard-chip ${metric === 'consumption' ? 'active' : ''}`} onClick={() => setMetric('consumption')}>消耗金额</button><button type="button" className={`dashboard-chip ${metric === 'fee' ? 'active' : ''}`} onClick={() => setMetric('fee')}>服务费</button></div></div>
          <div className="dashboard-control-item"><span className="dashboard-control-title">时间维度</span><div className="dashboard-chip-group"><button type="button" className={`dashboard-chip ${granularity === 'month' ? 'active' : ''}`} onClick={() => setGranularity('month')}>月度</button><button type="button" className={`dashboard-chip ${granularity === 'quarter' ? 'active' : ''}`} onClick={() => setGranularity('quarter')}>季度</button></div></div>
          <div className="dashboard-control-item"><span className="dashboard-control-title">{granularity === 'month' ? '月度窗口' : '季度窗口'}</span><div className="dashboard-chip-group">{windowOpts(granularity).map(w => <button key={w} type="button" className={`dashboard-chip ${windowSize === w ? 'active' : ''}`} onClick={() => setWindowSize(w)}>{granularity === 'month' ? `${w}个月` : `${w}季度`}</button>)}</div></div>
          <div className="dashboard-control-item dashboard-control-item-right"><span className="dashboard-control-title">视图</span><div className="dashboard-chip-group"><button type="button" className={`dashboard-chip ${view === 'report' ? 'active' : ''}`} onClick={() => setView('report')}>汇报</button><button type="button" className={`dashboard-chip ${view === 'analysis' ? 'active' : ''}`} onClick={() => setView('analysis')}>分析</button></div></div>
        </div>
      </div>

      <div className="dashboard-kpi-grid">
        <StatCard title="本期总消耗" value={stats.consumption} mom={stats.consumption_mom} yoy={stats.consumption_yoy} icon={Activity} color="blue" period={currentLabel} />
        <StatCard title="本期服务费" value={stats.fee} mom={stats.fee_mom} yoy={stats.fee_yoy} icon={DollarSign} color="purple" period={currentLabel} />
      </div>

      <div className={view === 'report' ? 'dashboard-report-grid' : 'dashboard-analysis-grid'}>
        <div className="chart-card dashboard-main-trend-card">
          <div className="dashboard-card-header"><h3>{metric === 'consumption' ? '消耗金额' : '服务费'}趋势对比</h3></div>
          <div className="chart-container">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={trendData} onClick={(event: unknown) => {
                if (granularity !== 'month') return
                const payload = (event as { activePayload?: Array<{ payload?: { periodKey?: string } }> } | undefined)?.activePayload
                const key = payload?.[0]?.payload?.periodKey
                if (key) setSelectedMonth(key)
              }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E2E8F0" />
                <XAxis dataKey="label" axisLine={false} tickLine={false} fontSize={12} tickMargin={14} stroke="#64748B" />
                <YAxis axisLine={false} tickLine={false} fontSize={12} tickFormatter={(v) => fmtCompact(Number(v))} stroke="#64748B" />
                <Tooltip formatter={(v: unknown, n: string | number | undefined) => [fmtMoney(Number(v || 0)), n === 'curr' ? '本期' : '去年同期']} />
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
              {compareRows.slice(0, 6).map((r, i) => (
                <button type="button" key={r.name} className="top-share-row" onClick={() => setSelectedClient(r.name)}>
                  <div className="top-share-main"><span>{i + 1}. {r.name}</span><span>{fmtMoney(r.curr)}</span></div>
                  <div className="top-share-track"><div className="top-share-fill" style={{ width: `${Math.min(r.share, 100)}%` }} /></div>
                  <span className="top-share-pct">{r.share.toFixed(1)}%</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {view === 'analysis' && (
          <div className="chart-card dashboard-top-compare-card">
            <div className="dashboard-card-header"><h3>{currentLabel} TOP 客户对比</h3><div className="dashboard-chip-group"><button type="button" className={`dashboard-chip ${sort === 'delta_pct' ? 'active' : ''}`} onClick={() => setSort('delta_pct')}>按增幅</button><button type="button" className={`dashboard-chip ${sort === 'delta' ? 'active' : ''}`} onClick={() => setSort('delta')}>按增量</button><button type="button" className={`dashboard-chip ${sort === 'rank' ? 'active' : ''}`} onClick={() => setSort('rank')}>按排名变化</button></div></div>
            <div className="dashboard-hint" style={{ marginBottom: '0.55rem' }}>对比基准：{prevLabel || (granularity === 'month' ? '上月无可用数据' : '上季度无可用数据')}</div>
            <div className="dashboard-compare-table-wrap">
              <table className="dashboard-compare-table">
                <thead><tr><th>排名</th><th>客户</th><th>本期</th><th>{granularity === 'month' ? '上月' : '上季度'}</th><th>增量</th><th>增幅</th><th>排名变化</th><th>占比</th></tr></thead>
                <tbody>
                  {compareRows.map(r => (
                    <tr key={r.name} onClick={() => setSelectedClient(r.name)}>
                      <td>{r.rank}</td><td className="client-col">{r.name}</td><td>{fmtMoney(r.curr)}</td><td>{r.prev === null ? '—' : fmtMoney(r.prev)}</td>
                      <td className={r.delta !== null && r.delta >= 0 ? 'positive' : 'negative'}>{r.delta === null ? '—' : fmtMoney(r.delta)}</td>
                      <td className={r.deltaPct !== null && r.deltaPct >= 0 ? 'positive' : 'negative'}>{r.deltaPct === null ? '—' : fmtPct(r.deltaPct)}</td>
                      <td className={r.rankChange !== null && r.rankChange >= 0 ? 'positive' : 'negative'}>{r.rankChange === null ? '—' : r.rankChange > 0 ? `+${r.rankChange}` : `${r.rankChange}`}</td>
                      <td>{r.share.toFixed(1)}%</td>
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
  period: string
}

const StatCard = ({ title, value, mom, yoy, icon: Icon, color, period }: StatCardProps) => (
  <div className="stat-card dashboard-stat-card">
    <div className="stat-header"><span className="stat-title">{title}</span><div className={`stat-icon ${color}`}><Icon size={20} /></div></div>
    <div className="stat-value">{fmtMoney(value)}</div>
    <div className="dashboard-stat-meta">统计周期：{period}</div>
    <div className="stat-footer">
      <div className={`stat-change ${mom >= 0 ? 'up' : 'down'}`}>{mom >= 0 ? <TrendingUp size={14} /> : <TrendingDown size={14} />}<span>环比 {fmtPct(mom)}</span></div>
      <div className={`stat-change ${yoy >= 0 ? 'up' : 'down'}`}><span>同比 {fmtPct(yoy)}</span></div>
    </div>
  </div>
)
