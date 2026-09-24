import { useEffect, useMemo } from 'react'
import {
  ComposedChart,
  Area,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  Legend,
} from 'recharts'
import { X, TrendingUp, TrendingDown } from 'lucide-react'
import type { ClientHistoryRow } from './billingTypes'

interface ClientMonthTrendModalProps {
  clientName: string
  selectedMonth: string
  rows: ClientHistoryRow[]
  formatNumber: (value: string | number) => string
  onClose: () => void
}

interface ProcessedTrendPoint {
  month: string
  netConsumption: number
  serviceFee: number
  netConsumptionMom: number | null
  netConsumptionYoy: number | null
  serviceFeeMom: number | null
  serviceFeeYoy: number | null
}

const previousMonthKey = (monthStr: string): string => {
  const parts = monthStr.split('-')
  if (parts.length !== 2) return ''
  const year = parseInt(parts[0], 10)
  const month = parseInt(parts[1], 10)
  if (isNaN(year) || isNaN(month)) return ''
  if (month === 1) {
    return `${year - 1}-12`
  }
  return `${year}-${String(month - 1).padStart(2, '0')}`
}

const prevYearMonth = (monthStr: string): string => {
  const parts = monthStr.split('-')
  if (parts.length !== 2) return ''
  const year = parseInt(parts[0], 10)
  const month = parseInt(parts[1], 10)
  if (isNaN(year) || isNaN(month)) return ''
  return `${year - 1}-${String(month).padStart(2, '0')}`
}

const calculateChanges = (current: number, prev: number | null): number | null => {
  if (prev === null) return null
  if (prev === 0) {
    return current > 0 ? 100 : 0
  }
  return ((current - prev) / prev) * 100
}

export function ClientMonthTrendModal({
  clientName,
  selectedMonth,
  rows,
  formatNumber,
  onClose,
}: ClientMonthTrendModalProps) {
  // ESC key listener to close the modal
  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handleEsc)
    return () => window.removeEventListener('keydown', handleEsc)
  }, [onClose])

  // Sort rows chronologically (ascending)
  const sortedRows = useMemo(() => {
    return [...rows].sort((a, b) => a.month.localeCompare(b.month))
  }, [rows])

  // Earliest billing month in database for this client
  const earliestMonth = useMemo(() => {
    return sortedRows.length > 0 ? sortedRows[0].month : ''
  }, [sortedRows])

  // Generate 12 consecutive months ending at selectedMonth
  const last12Months = useMemo(() => {
    const list: string[] = []
    let current = selectedMonth
    for (let i = 0; i < 12; i++) {
      list.unshift(current)
      current = previousMonthKey(current)
    }
    return list
  }, [selectedMonth])

  // Compute all metrics and YoY/MoM changes for each point in the window
  const processedTrendData = useMemo<ProcessedTrendPoint[]>(() => {
    const isBeforeEarliest = (m: string, earliest: string) => {
      return earliest ? m.localeCompare(earliest) < 0 : false
    }

    return last12Months.map((m) => {
      const prevM = previousMonthKey(m)
      const yoyM = prevYearMonth(m)

      const currentRow = sortedRows.find((r) => r.month === m)
      const prevRow = sortedRows.find((r) => r.month === prevM)
      const yoyRow = sortedRows.find((r) => r.month === yoyM)

      const netConsumption = currentRow?.net_consumption ?? 0
      const serviceFee = currentRow ? currentRow.service_fee + currentRow.fixed_service_fee : 0

      // Only calculate if the month is within the client's billing lifecycle
      const prevNetConsumption = isBeforeEarliest(prevM, earliestMonth)
        ? null
        : prevRow?.net_consumption ?? 0
      const yoyNetConsumption = isBeforeEarliest(yoyM, earliestMonth)
        ? null
        : yoyRow?.net_consumption ?? 0

      const prevServiceFee = isBeforeEarliest(prevM, earliestMonth)
        ? null
        : prevRow ? prevRow.service_fee + prevRow.fixed_service_fee : 0
      const yoyServiceFee = isBeforeEarliest(yoyM, earliestMonth)
        ? null
        : yoyRow ? yoyRow.service_fee + yoyRow.fixed_service_fee : 0

      const netConsumptionMom = calculateChanges(netConsumption, prevNetConsumption)
      const netConsumptionYoy = calculateChanges(netConsumption, yoyNetConsumption)

      const serviceFeeMom = calculateChanges(serviceFee, prevServiceFee)
      const serviceFeeYoy = calculateChanges(serviceFee, yoyServiceFee)

      return {
        month: m,
        netConsumption,
        serviceFee,
        netConsumptionMom,
        netConsumptionYoy,
        serviceFeeMom,
        serviceFeeYoy,
      }
    })
  }, [last12Months, sortedRows, earliestMonth])

  // Locate the data point for the clicked month
  const selectedPoint = useMemo<ProcessedTrendPoint | null>(() => {
    return processedTrendData.find((d) => d.month === selectedMonth) ?? null
  }, [processedTrendData, selectedMonth])

  // Helpers to render percentage badges
  const formatDeltaPct = (val: number | null): string => {
    if (val === null) return '无历史值'
    const sign = val >= 0 ? '+' : ''
    return `${sign}${val.toFixed(1)}%`
  }

  const getDeltaClass = (val: number | null): string => {
    if (val === null) return 'neutral'
    if (val > 0.01) return 'up'
    if (val < -0.01) return 'down'
    return 'neutral'
  }

  const renderDeltaBadge = (val: number | null, label: string) => {
    const cls = getDeltaClass(val)
    const formatted = formatDeltaPct(val)
    return (
      <div className={`kpi-change-item ${cls}`}>
        <span className="kpi-change-label">{label}</span>
        {val !== null && val > 0.01 && <TrendingUp size={12} />}
        {val !== null && val < -0.01 && <TrendingDown size={12} />}
        <span>{formatted}</span>
      </div>
    )
  }

  // Custom tooltips inside recharts
  const CustomTooltip = ({ active, payload }: any) => {
    if (active && payload && payload.length) {
      const data = payload[0].payload as ProcessedTrendPoint
      return (
        <div className="custom-chart-tooltip">
          <p className="tooltip-title">{data.month}</p>
          <div className="tooltip-content">
            <div className="tooltip-section consumption-sec">
              <div className="tooltip-metric-row">
                <span className="tooltip-dot consumption-dot"></span>
                <span className="tooltip-label">纯消耗:</span>
                <span className="tooltip-val">{formatNumber(data.netConsumption)}</span>
              </div>
              <div className="tooltip-badge-row">
                <span>环比: <strong className={getDeltaClass(data.netConsumptionMom)}>{formatDeltaPct(data.netConsumptionMom)}</strong></span>
                <span className="divider">|</span>
                <span>同比: <strong className={getDeltaClass(data.netConsumptionYoy)}>{formatDeltaPct(data.netConsumptionYoy)}</strong></span>
              </div>
            </div>

            <div className="tooltip-section fee-sec">
              <div className="tooltip-metric-row">
                <span className="tooltip-dot fee-dot"></span>
                <span className="tooltip-label">服务费:</span>
                <span className="tooltip-val">{formatNumber(data.serviceFee)}</span>
              </div>
              <div className="tooltip-badge-row">
                <span>环比: <strong className={getDeltaClass(data.serviceFeeMom)}>{formatDeltaPct(data.serviceFeeMom)}</strong></span>
                <span className="divider">|</span>
                <span>同比: <strong className={getDeltaClass(data.serviceFeeYoy)}>{formatDeltaPct(data.serviceFeeYoy)}</strong></span>
              </div>
            </div>
          </div>
        </div>
      )
    }
    return null
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-card month-trend-modal-card" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="modal-header">
          <div className="modal-title">
            <TrendingUp size={24} className="modal-icon" />
            <div>
              <h2>{clientName}</h2>
              <span className="modal-subtitle">{selectedMonth} 账单趋势分析</span>
            </div>
          </div>
          <button className="modal-close-btn" onClick={onClose} title="关闭 (Esc)">
            <X size={20} />
          </button>
        </div>

        {/* Body */}
        <div className="modal-body">
          {selectedPoint ? (
            <>
              {/* KPI Cards */}
              <div className="month-trend-kpis">
                <div className="month-kpi-card">
                  <span className="month-kpi-label">纯消耗 (不含服务费)</span>
                  <span className="month-kpi-value">{formatNumber(selectedPoint.netConsumption)}</span>
                  <div className="month-kpi-changes">
                    {renderDeltaBadge(selectedPoint.netConsumptionMom, '环比')}
                    {renderDeltaBadge(selectedPoint.netConsumptionYoy, '同比')}
                  </div>
                </div>

                <div className="month-kpi-card">
                  <span className="month-kpi-label">总服务费 (变动 + 固定)</span>
                  <span className="month-kpi-value">{formatNumber(selectedPoint.serviceFee)}</span>
                  <div className="month-kpi-changes">
                    {renderDeltaBadge(selectedPoint.serviceFeeMom, '环比')}
                    {renderDeltaBadge(selectedPoint.serviceFeeYoy, '同比')}
                  </div>
                </div>
              </div>

              {/* Chart */}
              <div className="modal-chart month-trend-chart-container">
                <ResponsiveContainer width="100%" height="100%">
                  <ComposedChart data={processedTrendData}>
                    <defs>
                      <linearGradient id="colorConsumption" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#4f46e5" stopOpacity={0.2} />
                        <stop offset="95%" stopColor="#4f46e5" stopOpacity={0.0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#F1F5F9" />
                    <XAxis
                      dataKey="month"
                      axisLine={false}
                      tickLine={false}
                      fontSize={11}
                      tickMargin={10}
                      stroke="#64748B"
                    />
                    <YAxis
                      yAxisId="left"
                      axisLine={false}
                      tickLine={false}
                      fontSize={11}
                      stroke="#4f46e5"
                      tickFormatter={(val) => `${(val / 1000).toFixed(0)}k`}
                    />
                    <YAxis
                      yAxisId="right"
                      orientation="right"
                      axisLine={false}
                      tickLine={false}
                      fontSize={11}
                      stroke="#10b981"
                      className="y-axis-right"
                      tickFormatter={(val) => `${(val / 1000).toFixed(1)}k`}
                    />
                    <Tooltip content={<CustomTooltip />} />
                    <Legend
                      verticalAlign="top"
                      height={36}
                      iconType="circle"
                      iconSize={8}
                      wrapperStyle={{ fontSize: 12, paddingBottom: 10 }}
                    />
                    <Area
                      yAxisId="left"
                      type="monotone"
                      dataKey="netConsumption"
                      name="纯消耗 (左轴)"
                      stroke="#4f46e5"
                      strokeWidth={2}
                      fillOpacity={1}
                      fill="url(#colorConsumption)"
                      isAnimationActive={false}
                    />
                    <Line
                      yAxisId="right"
                      type="monotone"
                      dataKey="serviceFee"
                      name="服务费 (右轴)"
                      stroke="#10b981"
                      strokeWidth={2}
                      dot={{ r: 3, fill: '#10b981', strokeWidth: 1, stroke: '#fff' }}
                      activeDot={{ r: 5, fill: '#10b981' }}
                      isAnimationActive={false}
                    />
                    {/* Add ReferenceLine for clicked month */}
                    <ReferenceLine
                      yAxisId="left"
                      x={selectedMonth}
                      stroke="#94A3B8"
                      strokeDasharray="4 4"
                      label={{
                        value: '选中月',
                        position: 'top',
                        fill: '#64748B',
                        fontSize: 10,
                        fontWeight: 600,
                      }}
                    />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
            </>
          ) : (
            <div style={{ textAlign: 'center', padding: '2rem 0', color: 'var(--text-muted)' }}>
              未找到该月份的数据。
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
