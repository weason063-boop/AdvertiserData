import { useEffect, useMemo, useRef, useState, type ComponentType } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { Activity, BarChart3, DollarSign, TrendingDown, TrendingUp } from 'lucide-react'
import { ClientTrendModal } from './ClientTrendModal'
import { Skeleton } from './Skeleton'
import { EmptyState } from './EmptyState'
import { apiJson } from './apiClient'
import type { DashboardData } from './billingTypes'

type MetricMode = 'consumption' | 'fee'
type Granularity = 'month' | 'quarter'
type MonthCompareMode = 'mom' | 'yoy' | 'dual'
type MonthWorkbenchView = 'dual' | 'share' | 'mom' | 'yoy'
type QuarterCompareMode = 'qoq' | 'yoy' | 'dual'
type QuarterWorkbenchView = 'dual' | 'share' | 'qoq' | 'yoy'

interface DashboardProps {
  data: DashboardData
  preferredMonth?: string | null
  loading?: boolean
  onNotify?: (message: string, type: 'info' | 'success' | 'error') => void
  onRequireAuth?: () => void
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
  prev_month_consumption?: number | null
  prev_month_service_fee?: number | null
  prev_month_rank?: number | null
  mom_delta?: number | null
  mom_fee_delta?: number | null
  mom_rank_change?: number | null
  prev_quarter_consumption?: number | null
  prev_quarter_service_fee?: number | null
  prev_quarter_rank?: number | null
  yoy_consumption?: number | null
  yoy_service_fee?: number | null
  yoy_rank?: number | null
  qoq_delta?: number | null
  qoq_fee_delta?: number | null
  qoq_rank_change?: number | null
  yoy_delta?: number | null
  yoy_fee_delta?: number | null
  yoy_rank_change?: number | null
}

interface CompareResp {
  month?: string
  quarter?: string
  prev_month?: string | null
  yoy_month?: string | null
  prev_quarter?: string | null
  yoy_quarter?: string | null
  compare_mode?: 'none' | MonthCompareMode | QuarterCompareMode
  clients: CompareClient[]
}

interface SeriesPoint {
  key: string
  label: string
  total_consumption: number
  total_service_fee: number
}

interface TrendPoint {
  periodKey: string
  label: string
  curr: number
  prevMonthKey: string | null
  prevMonthLabel: string
  prevMonthValue: number | null
  yoyKey: string | null
  yoyLabel: string
  yoyValue: number | null
  isActive: boolean
}

interface QuarterChartPoint {
  slot: string
  currentMonthLabel: string
  qoqMonthLabel: string
  yoyMonthLabel: string
  curr: number
  qoq: number
  yoy: number
  missingCurrent: boolean
  missingQoq: boolean
  missingYoy: boolean
}

interface NormalizedClient extends CompareClient {
  rank: number
}

interface MonthWorkbenchRow {
  name: string
  rank: number
  curr: number
  prevMonth: number | null
  yoy: number | null
  momDelta: number | null
  momDeltaPct: number | null
  momRankChange: number | null
  yoyDelta: number | null
  yoyDeltaPct: number | null
  yoyRankChange: number | null
  share: number
}

interface QuarterRow {
  name: string
  rank: number
  curr: number
  prevQuarter: number | null
  yoy: number | null
  qoqDelta: number | null
  qoqDeltaPct: number | null
  qoqRankChange: number | null
  yoyDelta: number | null
  yoyDeltaPct: number | null
  yoyRankChange: number | null
  share: number
}

interface QuarterSummaryCard {
  label: string
  value: string
  meta: string
  tone: 'neutral' | 'positive' | 'negative'
}

interface QuarterOverviewMetric {
  value: number
  qoqChange: number
  yoyChange: number
}

const MONTH_WINDOW_OPTIONS = [6, 12]
const EMPTY_TOP_CLIENTS: NonNullable<DashboardData['top_clients']> = []
const QUARTER_SLOT_LABELS = ['季初', '季中', '季末']
const MONTH_VIEW_OPTIONS: Array<{ key: MonthWorkbenchView; label: string }> = [
  { key: 'dual', label: '双基准' },
  { key: 'share', label: '贡献排行' },
  { key: 'mom', label: '环比变化' },
  { key: 'yoy', label: '同比变化' },
]
const QUARTER_VIEW_OPTIONS: Array<{ key: QuarterWorkbenchView; label: string }> = [
  { key: 'dual', label: '双基准' },
  { key: 'share', label: '贡献排行' },
  { key: 'qoq', label: '环比变化' },
  { key: 'yoy', label: '同比变化' },
]

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
  const [year, m] = month.split('-').map(Number)
  return `${year - 1}-${String(m).padStart(2, '0')}`
}

const previousMonthKey = (month: string) => {
  const [year, m] = month.split('-').map(Number)
  if (!year || !m) return null
  const date = new Date(year, m - 1, 1)
  date.setMonth(date.getMonth() - 1)
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`
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

const parseQuarterKey = (quarter: string): { year: number; quarter: number } | null => {
  const match = /^(\d{4})-Q([1-4])$/.exec(quarter)
  if (!match) return null
  return { year: Number(match[1]), quarter: Number(match[2]) }
}

const prevYearQuarter = (quarter: string) => {
  const [yearText, qText] = quarter.split('-Q')
  return `${Number(yearText) - 1}-Q${Number(qText)}`
}

const previousQuarter = (quarter: string) => {
  const parsed = parseQuarterKey(quarter)
  if (!parsed) return null
  if (parsed.quarter > 1) return `${parsed.year}-Q${parsed.quarter - 1}`
  return `${parsed.year - 1}-Q4`
}

const quarterMonths = (quarter: string): string[] => {
  const parsed = parseQuarterKey(quarter)
  if (!parsed) return []
  if (parsed.quarter === 1) return [`${parsed.year}-03`, `${parsed.year}-04`, `${parsed.year}-05`]
  if (parsed.quarter === 2) return [`${parsed.year}-06`, `${parsed.year}-07`, `${parsed.year}-08`]
  if (parsed.quarter === 3) return [`${parsed.year}-09`, `${parsed.year}-10`, `${parsed.year}-11`]
  return [`${parsed.year}-12`, `${parsed.year + 1}-01`, `${parsed.year + 1}-02`]
}

const calcPctChange = (current: number, baseline: number | null) => {
  if (baseline === null || baseline === 0) return 0
  return ((current - baseline) / baseline) * 100
}

const calcNullablePct = (delta: number | null, baseline: number | null) => {
  if (delta === null || baseline === null || baseline === 0) return null
  return (delta / baseline) * 100
}

const sortable = (value: number | null) => (typeof value === 'number' ? value : Number.NEGATIVE_INFINITY)

const formatQuarterLabel = (quarter: string | null | undefined) => {
  if (!quarter) return '—'
  return quarter.replace('-Q', ' Q')
}

const formatRankChange = (value: number | null) => {
  if (value === null) return '—'
  if (value > 0) return `+${value}`
  return `${value}`
}

const toneForDelta = (value: number | null): 'neutral' | 'positive' | 'negative' => {
  if (value === null || value === 0) return 'neutral'
  return value > 0 ? 'positive' : 'negative'
}

const getPreviousAvailableQuarter = (quarter: string, keys: string[]) => {
  const exactPrev = previousQuarter(quarter)
  if (exactPrev && keys.includes(exactPrev)) return exactPrev
  const earlier = keys.filter((key) => key < quarter)
  return earlier.length ? earlier[earlier.length - 1] : null
}

const getPreviousAvailableMonth = (month: string, keys: string[]) => {
  const exactPrev = previousMonthKey(month)
  if (exactPrev && keys.includes(exactPrev)) return exactPrev
  const earlier = keys.filter((key) => key < month)
  return earlier.length ? earlier[earlier.length - 1] : null
}

const getYoYQuarter = (quarter: string, lookup: Map<string, SeriesPoint>) => {
  const candidate = prevYearQuarter(quarter)
  return lookup.has(candidate) ? candidate : null
}

const buildQuarterSummaryMeta = (label: string | null | undefined, pct: number | null, fallback: string) => {
  if (!label || label === '—') return fallback
  if (pct === null) return `对比 ${label} · 基准为 0`
  return `对比 ${label} · ${fmtPct(pct)}`
}

export function Dashboard({ data, preferredMonth, loading, onRequireAuth }: DashboardProps) {
  const { stats, trend, top_clients = EMPTY_TOP_CLIENTS } = data
  const [metric, setMetric] = useState<MetricMode>('consumption')
  const [granularity, setGranularity] = useState<Granularity>('month')
  const [monthWindowSize, setMonthWindowSize] = useState<number>(12)
  const [activeMonthKey, setActiveMonthKey] = useState<string | null>(null)
  const [monthWorkbenchView, setMonthWorkbenchView] = useState<MonthWorkbenchView>('dual')
  const [selectedClient, setSelectedClient] = useState<string | null>(null)
  const [compare, setCompare] = useState<CompareResp | null>(null)
  const [quarterYear, setQuarterYear] = useState<number>(new Date().getFullYear())
  const [quarterNumber, setQuarterNumber] = useState<number>(1)
  const [quarterWorkbenchView, setQuarterWorkbenchView] = useState<QuarterWorkbenchView>('dual')
  const monthSelectionModeRef = useRef<'auto' | 'manual'>('auto')

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

  const monthLookup = useMemo(() => new Map(monthSeries.map((item) => [item.key, item])), [monthSeries])
  const monthKeys = useMemo(() => monthSeries.map((item) => item.key), [monthSeries])
  const quarterLookup = useMemo(() => new Map(quarterSeries.map((item) => [item.key, item])), [quarterSeries])
  const quarterKeys = useMemo(() => quarterSeries.map((item) => item.key), [quarterSeries])
  const latestQuarterMeta = useMemo(() => {
    if (!quarterSeries.length) return null
    return parseQuarterKey(quarterSeries[quarterSeries.length - 1].key)
  }, [quarterSeries])

  const availableQuarterYears = useMemo(() => {
    const years = new Set<number>()
    quarterSeries.forEach((item) => {
      const parsed = parseQuarterKey(item.key)
      if (parsed) years.add(parsed.year)
    })
    return [...years].sort((a, b) => a - b)
  }, [quarterSeries])

  const availableQuarterNumbers = useMemo(() => {
    const numbers = quarterSeries
      .map((item) => parseQuarterKey(item.key))
      .filter((item): item is { year: number; quarter: number } => Boolean(item))
      .filter((item) => item.year === quarterYear)
      .map((item) => item.quarter)
    return [...new Set(numbers)].sort((a, b) => a - b)
  }, [quarterSeries, quarterYear])

  useEffect(() => {
    if (!latestQuarterMeta) return
    setQuarterYear((current) => (availableQuarterYears.includes(current) ? current : latestQuarterMeta.year))
  }, [availableQuarterYears, latestQuarterMeta])

  useEffect(() => {
    if (!latestQuarterMeta) return
    if (!availableQuarterNumbers.length) {
      setQuarterNumber(latestQuarterMeta.quarter)
      return
    }
    setQuarterNumber((current) => (availableQuarterNumbers.includes(current)
      ? current
      : availableQuarterNumbers[availableQuarterNumbers.length - 1]))
  }, [availableQuarterNumbers, latestQuarterMeta])

  const quarterTarget = useMemo(() => {
    if (!quarterSeries.length) return null
    const exact = quarterLookup.get(`${quarterYear}-Q${quarterNumber}`)
    return exact ?? quarterSeries[quarterSeries.length - 1]
  }, [quarterLookup, quarterNumber, quarterSeries, quarterYear])

  const quarterCompareMode: QuarterCompareMode = useMemo(() => {
    if (quarterWorkbenchView === 'qoq') return 'qoq'
    if (quarterWorkbenchView === 'yoy') return 'yoy'
    return 'dual'
  }, [quarterWorkbenchView])

  const monthWindowed = useMemo(
    () => monthSeries.slice(-Math.min(monthWindowSize, monthSeries.length)),
    [monthSeries, monthWindowSize],
  )

  const preferredMonthKey = useMemo(() => {
    if (!monthWindowed.length) return null
    if (preferredMonth && monthWindowed.some((item) => item.key === preferredMonth)) return preferredMonth
    if (stats?.month && monthWindowed.some((item) => item.key === stats.month)) return stats.month
    return null
  }, [monthWindowed, preferredMonth, stats])

  useEffect(() => {
    if (!monthWindowed.length) {
      monthSelectionModeRef.current = 'auto'
      setActiveMonthKey(null)
      return
    }
    const fallbackKey = preferredMonthKey ?? monthWindowed[monthWindowed.length - 1].key
    setActiveMonthKey((current) => (
      monthSelectionModeRef.current === 'manual' && current && monthWindowed.some((item) => item.key === current)
        ? current
        : fallbackKey
    ))
  }, [monthWindowed, preferredMonthKey])

  const activeMonthPoint = useMemo(() => {
    if (!monthWindowed.length) return null
    return monthWindowed.find((item) => item.key === activeMonthKey) ?? monthWindowed[monthWindowed.length - 1]
  }, [activeMonthKey, monthWindowed])

  const monthCompareMode: MonthCompareMode = useMemo(() => {
    if (monthWorkbenchView === 'mom') return 'mom'
    if (monthWorkbenchView === 'yoy') return 'yoy'
    return 'dual'
  }, [monthWorkbenchView])

  const currentPeriod = granularity === 'month'
    ? activeMonthPoint
    : quarterTarget

  useEffect(() => {
    if (!currentPeriod) return
    const controller = new AbortController()
    setCompare(null)

    const path = granularity === 'month'
      ? `/api/dashboard/month/${encodeURIComponent(currentPeriod.key)}/top-clients?limit=10&compare_mode=${monthCompareMode}`
      : `/api/dashboard/quarter/${encodeURIComponent(currentPeriod.key)}/top-clients?limit=10&compare_mode=${quarterCompareMode}`

    apiJson<CompareResp>(path, {
      signal: controller.signal,
    }, {
      throwOnHttpError: false,
    })
      .then(({ data: payload, res }) => {
        if (res.status === 401) {
          onRequireAuth?.()
          return
        }
        if (res.ok && payload?.clients) {
          setCompare(payload)
        }
      })
      .catch(() => undefined)

    return () => controller.abort()
  }, [currentPeriod, granularity, monthCompareMode, onRequireAuth, quarterCompareMode])

  const monthTrendData = useMemo<TrendPoint[]>(() => monthWindowed.map((item) => {
    const prevMonth = getPreviousAvailableMonth(item.key, monthKeys)
    const prevMonthPoint = prevMonth ? monthLookup.get(prevMonth) : null
    const yoyKey = monthLookup.has(prevYearMonth(item.key)) ? prevYearMonth(item.key) : null
    const yoyPoint = yoyKey ? monthLookup.get(yoyKey) : null
    return {
      periodKey: item.key,
      label: item.label,
      curr: metric === 'consumption' ? item.total_consumption : item.total_service_fee,
      prevMonthKey: prevMonth,
      prevMonthLabel: prevMonth ?? '—',
      prevMonthValue: prevMonthPoint
        ? (metric === 'consumption' ? prevMonthPoint.total_consumption : prevMonthPoint.total_service_fee)
        : null,
      yoyKey,
      yoyLabel: yoyKey ?? '—',
      yoyValue: yoyPoint
        ? (metric === 'consumption' ? yoyPoint.total_consumption : yoyPoint.total_service_fee)
        : null,
      isActive: item.key === activeMonthKey,
    }
  }), [activeMonthKey, metric, monthKeys, monthLookup, monthWindowed])

  const currentQuarterKey = quarterTarget?.key ?? ''
  const activeMonthCompare = granularity === 'month' && compare?.month === activeMonthPoint?.key ? compare : null
  const monthCompareModeMismatch = granularity === 'month'
    && Boolean(activeMonthCompare)
    && activeMonthCompare?.compare_mode !== monthCompareMode
  const showMonthCompareSyncWarning = monthWorkbenchView !== 'share' && monthCompareModeMismatch
  const activeQuarterCompare = granularity === 'quarter' && compare?.quarter === currentQuarterKey ? compare : null
  const prevMonthKey = activeMonthPoint
    ? (activeMonthCompare?.prev_month ?? getPreviousAvailableMonth(activeMonthPoint.key, monthKeys))
    : null
  const yoyMonthKey = activeMonthPoint
    ? (activeMonthCompare?.yoy_month ?? (monthLookup.has(prevYearMonth(activeMonthPoint.key)) ? prevYearMonth(activeMonthPoint.key) : null))
    : null
  const prevMonthPoint = prevMonthKey ? monthLookup.get(prevMonthKey) ?? null : null
  const yoyMonthPoint = yoyMonthKey ? monthLookup.get(yoyMonthKey) ?? null : null
  const qoqQuarterKey = currentQuarterKey
    ? (activeQuarterCompare?.prev_quarter ?? getPreviousAvailableQuarter(currentQuarterKey, quarterKeys))
    : null
  const yoyQuarterKey = currentQuarterKey
    ? (activeQuarterCompare?.yoy_quarter ?? getYoYQuarter(currentQuarterKey, quarterLookup))
    : null

  const qoqQuarterPoint = qoqQuarterKey ? quarterLookup.get(qoqQuarterKey) ?? null : null
  const yoyQuarterPoint = yoyQuarterKey ? quarterLookup.get(yoyQuarterKey) ?? null : null

  const monthOverview = useMemo(() => {
    if (!activeMonthPoint) return null
    const prevConsumptionBase = prevMonthPoint?.total_consumption ?? null
    const prevFeeBase = prevMonthPoint?.total_service_fee ?? null
    const yoyConsumptionBase = yoyMonthPoint?.total_consumption ?? null
    const yoyFeeBase = yoyMonthPoint?.total_service_fee ?? null
    return {
      consumption: {
        value: activeMonthPoint.total_consumption,
        momChange: calcPctChange(activeMonthPoint.total_consumption, prevConsumptionBase),
        yoyChange: calcPctChange(activeMonthPoint.total_consumption, yoyConsumptionBase),
      },
      fee: {
        value: activeMonthPoint.total_service_fee,
        momChange: calcPctChange(activeMonthPoint.total_service_fee, prevFeeBase),
        yoyChange: calcPctChange(activeMonthPoint.total_service_fee, yoyFeeBase),
      },
    }
  }, [activeMonthPoint, prevMonthPoint, yoyMonthPoint])

  const quarterOverview = useMemo(() => {
    if (!quarterTarget) return null
    const qoqConsumptionBase = qoqQuarterPoint?.total_consumption ?? null
    const yoyConsumptionBase = yoyQuarterPoint?.total_consumption ?? null
    const qoqFeeBase = qoqQuarterPoint?.total_service_fee ?? null
    const yoyFeeBase = yoyQuarterPoint?.total_service_fee ?? null

    const consumption: QuarterOverviewMetric = {
      value: quarterTarget.total_consumption,
      qoqChange: calcPctChange(quarterTarget.total_consumption, qoqConsumptionBase),
      yoyChange: calcPctChange(quarterTarget.total_consumption, yoyConsumptionBase),
    }
    const fee: QuarterOverviewMetric = {
      value: quarterTarget.total_service_fee,
      qoqChange: calcPctChange(quarterTarget.total_service_fee, qoqFeeBase),
      yoyChange: calcPctChange(quarterTarget.total_service_fee, yoyFeeBase),
    }

    return { consumption, fee }
  }, [qoqQuarterPoint, quarterTarget, yoyQuarterPoint])

  const quarterChartData = useMemo<QuarterChartPoint[]>(() => {
    if (!quarterTarget) return []

    const currentMonths = quarterMonths(quarterTarget.key)
    const qoqMonths = qoqQuarterKey ? quarterMonths(qoqQuarterKey) : []
    const yoyMonths = yoyQuarterKey ? quarterMonths(yoyQuarterKey) : []

    return currentMonths.map((month, index) => {
      const currentPoint = monthLookup.get(month)
      const qoqMonth = qoqMonths[index] ?? ''
      const yoyMonth = yoyMonths[index] ?? ''
      const qoqPoint = qoqMonth ? monthLookup.get(qoqMonth) : undefined
      const yoyPoint = yoyMonth ? monthLookup.get(yoyMonth) : undefined

      return {
        slot: QUARTER_SLOT_LABELS[index] ?? `月份 ${index + 1}`,
        currentMonthLabel: month,
        qoqMonthLabel: qoqMonth || '—',
        yoyMonthLabel: yoyMonth || '—',
        curr: metric === 'consumption'
          ? Number(currentPoint?.total_consumption || 0)
          : Number(currentPoint?.total_service_fee || 0),
        qoq: qoqQuarterKey
          ? (metric === 'consumption'
            ? Number(qoqPoint?.total_consumption || 0)
            : Number(qoqPoint?.total_service_fee || 0))
          : 0,
        yoy: yoyQuarterKey
          ? (metric === 'consumption'
            ? Number(yoyPoint?.total_consumption || 0)
            : Number(yoyPoint?.total_service_fee || 0))
          : 0,
        missingCurrent: !currentPoint,
        missingQoq: qoqQuarterKey ? !qoqPoint : true,
        missingYoy: yoyQuarterKey ? !yoyPoint : true,
      }
    })
  }, [metric, monthLookup, qoqQuarterKey, quarterTarget, yoyQuarterKey])

  const monthClients = useMemo<NormalizedClient[]>(() => {
    if (activeMonthCompare?.clients?.length) {
      return activeMonthCompare.clients.map((item, index) => ({ ...item, rank: item.rank ?? index + 1 }))
    }
    if (activeMonthPoint?.key !== stats?.month) return []
    return top_clients.map((item, index) => ({
      ...item,
      rank: index + 1,
      prev_consumption: null,
      prev_service_fee: null,
      consumption_delta: null,
      fee_delta: null,
      rank_change: null,
      prev_month_consumption: null,
      prev_month_service_fee: null,
      prev_month_rank: null,
      yoy_consumption: null,
      yoy_service_fee: null,
      yoy_rank: null,
      mom_delta: null,
      mom_fee_delta: null,
      mom_rank_change: null,
      yoy_delta: null,
      yoy_fee_delta: null,
      yoy_rank_change: null,
    }))
  }, [activeMonthCompare, activeMonthPoint?.key, stats?.month, top_clients])

  const monthTotal = activeMonthPoint
    ? (metric === 'consumption' ? activeMonthPoint.total_consumption : activeMonthPoint.total_service_fee)
    : 0
  const monthRows = useMemo<MonthWorkbenchRow[]>(() => [...monthClients].map((item, index) => {
    const curr = metric === 'consumption' ? item.consumption : item.service_fee
    const prevMonth = metric === 'consumption'
      ? (item.prev_month_consumption ?? item.prev_consumption ?? null)
      : (item.prev_month_service_fee ?? item.prev_service_fee ?? null)
    const yoy = metric === 'consumption'
      ? (item.yoy_consumption ?? null)
      : (item.yoy_service_fee ?? null)
    const momDelta = metric === 'consumption'
      ? (item.mom_delta ?? item.consumption_delta ?? null)
      : (item.mom_fee_delta ?? item.fee_delta ?? null)
    const yoyDelta = metric === 'consumption'
      ? (item.yoy_delta ?? null)
      : (item.yoy_fee_delta ?? null)
    return {
      name: item.client_name,
      rank: item.rank ?? index + 1,
      curr,
      prevMonth,
      yoy,
      momDelta,
      momDeltaPct: calcNullablePct(momDelta, prevMonth),
      momRankChange: item.mom_rank_change ?? item.rank_change ?? null,
      yoyDelta,
      yoyDeltaPct: calcNullablePct(yoyDelta, yoy),
      yoyRankChange: item.yoy_rank_change ?? null,
      share: monthTotal > 0 ? (curr / monthTotal) * 100 : 0,
    }
  }).sort((a, b) => b.curr - a.curr), [metric, monthClients, monthTotal])

  const monthShareRows = [...monthRows].sort((a, b) => b.curr - a.curr).slice(0, 100)
  const monthDualRows = [...monthRows].sort((a, b) => b.curr - a.curr)
  const monthMomRows = [...monthRows].sort((a, b) => sortable(b.momDelta) - sortable(a.momDelta))
  const monthYoyRows = [...monthRows].sort((a, b) => sortable(b.yoyDelta) - sortable(a.yoyDelta))

  const quarterTotal = quarterTarget
    ? (metric === 'consumption' ? quarterTarget.total_consumption : quarterTarget.total_service_fee)
    : 0
  const quarterClients = useMemo<CompareClient[]>(
    () => activeQuarterCompare?.clients ?? [],
    [activeQuarterCompare],
  )
  const quarterRows = useMemo<QuarterRow[]>(() => quarterClients.map((item, index) => {
    const curr = metric === 'consumption' ? item.consumption : item.service_fee
    const prevQuarter = metric === 'consumption'
      ? (item.prev_quarter_consumption ?? item.prev_consumption ?? null)
      : (item.prev_quarter_service_fee ?? item.prev_service_fee ?? null)
    const yoy = metric === 'consumption'
      ? (item.yoy_consumption ?? null)
      : (item.yoy_service_fee ?? null)
    const qoqDelta = metric === 'consumption'
      ? (item.qoq_delta ?? item.consumption_delta ?? null)
      : (item.qoq_fee_delta ?? item.fee_delta ?? null)
    const yoyDelta = metric === 'consumption'
      ? (item.yoy_delta ?? null)
      : (item.yoy_fee_delta ?? null)
    return {
      name: item.client_name,
      rank: item.rank ?? index + 1,
      curr,
      prevQuarter,
      yoy,
      qoqDelta,
      qoqDeltaPct: calcNullablePct(qoqDelta, prevQuarter),
      qoqRankChange: item.qoq_rank_change ?? item.rank_change ?? null,
      yoyDelta,
      yoyDeltaPct: calcNullablePct(yoyDelta, yoy),
      yoyRankChange: item.yoy_rank_change ?? null,
      share: quarterTotal > 0 ? (curr / quarterTotal) * 100 : 0,
    }
  }), [metric, quarterClients, quarterTotal])

  const quarterShareRows = [...quarterRows].sort((a, b) => b.curr - a.curr).slice(0, 100)
  const quarterDualRows = [...quarterRows].sort((a, b) => b.curr - a.curr)
  const quarterQoqRows = [...quarterRows].sort((a, b) => sortable(b.qoqDelta) - sortable(a.qoqDelta))
  const quarterYoyRows = [...quarterRows].sort((a, b) => sortable(b.yoyDelta) - sortable(a.yoyDelta))

  const monthSummaryCards = useMemo<QuarterSummaryCard[]>(() => {
    if (!activeMonthPoint) return []
    const currentValue = metric === 'consumption' ? activeMonthPoint.total_consumption : activeMonthPoint.total_service_fee
    const momValue = prevMonthPoint
      ? (metric === 'consumption' ? prevMonthPoint.total_consumption : prevMonthPoint.total_service_fee)
      : null
    const yoyValue = yoyMonthPoint
      ? (metric === 'consumption' ? yoyMonthPoint.total_consumption : yoyMonthPoint.total_service_fee)
      : null
    const momDelta = momValue === null ? null : currentValue - momValue
    const yoyDelta = yoyValue === null ? null : currentValue - yoyValue
    const momPct = calcNullablePct(momDelta, momValue)
    const yoyPct = calcNullablePct(yoyDelta, yoyValue)
    return [
      {
        label: '本月总额',
        value: fmtMoney(currentValue),
        meta: `当前月份 ${activeMonthPoint.label}`,
        tone: 'neutral',
      },
      {
        label: '环比变化',
        value: momDelta === null ? '—' : fmtMoney(momDelta),
        meta: buildQuarterSummaryMeta(prevMonthKey, momPct, '暂无可用上月'),
        tone: toneForDelta(momDelta),
      },
      {
        label: '同比变化',
        value: yoyDelta === null ? '—' : fmtMoney(yoyDelta),
        meta: buildQuarterSummaryMeta(yoyMonthKey, yoyPct, '暂无去年同月'),
        tone: toneForDelta(yoyDelta),
      },
    ]
  }, [activeMonthPoint, metric, prevMonthKey, prevMonthPoint, yoyMonthKey, yoyMonthPoint])

  const quarterSummaryCards = useMemo<QuarterSummaryCard[]>(() => {
    if (!quarterTarget) return []
    const currentValue = metric === 'consumption' ? quarterTarget.total_consumption : quarterTarget.total_service_fee
    const qoqValue = qoqQuarterPoint
      ? (metric === 'consumption' ? qoqQuarterPoint.total_consumption : qoqQuarterPoint.total_service_fee)
      : null
    const yoyValue = yoyQuarterPoint
      ? (metric === 'consumption' ? yoyQuarterPoint.total_consumption : yoyQuarterPoint.total_service_fee)
      : null
    const qoqDelta = qoqValue === null ? null : currentValue - qoqValue
    const yoyDelta = yoyValue === null ? null : currentValue - yoyValue
    const qoqPct = calcNullablePct(qoqDelta, qoqValue)
    const yoyPct = calcNullablePct(yoyDelta, yoyValue)
    return [
      {
        label: '本季总额',
        value: fmtMoney(currentValue),
        meta: `当前季度 ${formatQuarterLabel(quarterTarget.key)}`,
        tone: 'neutral',
      },
      {
        label: '环比变化',
        value: qoqDelta === null ? '—' : fmtMoney(qoqDelta),
        meta: buildQuarterSummaryMeta(formatQuarterLabel(qoqQuarterKey), qoqPct, '暂无可用上季度'),
        tone: toneForDelta(qoqDelta),
      },
      {
        label: '同比变化',
        value: yoyDelta === null ? '—' : fmtMoney(yoyDelta),
        meta: buildQuarterSummaryMeta(formatQuarterLabel(yoyQuarterKey), yoyPct, '暂无去年同季'),
        tone: toneForDelta(yoyDelta),
      },
    ]
  }, [metric, qoqQuarterKey, qoqQuarterPoint, quarterTarget, yoyQuarterKey, yoyQuarterPoint])

  const currentMonthLabel = activeMonthPoint?.label || stats?.month || ''
  const currentQuarterLabel = formatQuarterLabel(quarterTarget?.key)

  const monthTooltip = (props: { active?: boolean; payload?: ReadonlyArray<{ payload?: TrendPoint }> }) => {
    const { active, payload } = props
    const point = payload?.[0]?.payload
    if (!active || !point) return null

    const momDelta = point.prevMonthValue === null ? null : point.curr - point.prevMonthValue
    const yoyDelta = point.yoyValue === null ? null : point.curr - point.yoyValue

    return (
      <div className="dashboard-tooltip">
        <div className="dashboard-tooltip-title">{point.label}</div>
        <div className="dashboard-tooltip-row">
          <span>本月</span>
          <strong>{fmtMoney(point.curr)}</strong>
        </div>
        <div className="dashboard-tooltip-row">
          <span>{point.prevMonthLabel === '—' ? '上月' : point.prevMonthLabel}</span>
          <strong>{point.prevMonthValue === null ? '—' : fmtMoney(point.prevMonthValue)}</strong>
        </div>
        <div className="dashboard-tooltip-row">
          <span>{point.yoyLabel === '—' ? '去年同月' : point.yoyLabel}</span>
          <strong>{point.yoyValue === null ? '—' : fmtMoney(point.yoyValue)}</strong>
        </div>
        <div className="dashboard-tooltip-row">
          <span>环比差值</span>
          <strong>{momDelta === null ? '—' : fmtMoney(momDelta)}</strong>
        </div>
        <div className="dashboard-tooltip-row">
          <span>同比差值</span>
          <strong>{yoyDelta === null ? '—' : fmtMoney(yoyDelta)}</strong>
        </div>
      </div>
    )
  }

  const quarterTooltip = (props: { active?: boolean; payload?: ReadonlyArray<{ payload?: QuarterChartPoint }> }) => {
    const { active, payload } = props
    const point = payload?.[0]?.payload
    if (!active || !point) return null

    const qoqDelta = qoqQuarterKey ? point.curr - point.qoq : null
    const yoyDelta = yoyQuarterKey ? point.curr - point.yoy : null

    return (
      <div className="dashboard-tooltip quarter-tooltip">
        <div className="dashboard-tooltip-title">{currentQuarterLabel} · {point.slot}</div>
        <div className="dashboard-tooltip-row">
          <span>{point.currentMonthLabel}</span>
          <strong>{fmtMoney(point.curr)}</strong>
        </div>
        {(quarterCompareMode === 'qoq' || quarterCompareMode === 'dual') && (
          <>
            <div className="dashboard-tooltip-row">
              <span>{point.qoqMonthLabel}</span>
              <strong>{qoqQuarterKey ? fmtMoney(point.qoq) : '—'}</strong>
            </div>
            <div className="dashboard-tooltip-row">
              <span>环比差值</span>
              <strong>{qoqDelta === null ? '—' : fmtMoney(qoqDelta)}</strong>
            </div>
          </>
        )}
        {(quarterCompareMode === 'yoy' || quarterCompareMode === 'dual') && (
          <>
            <div className="dashboard-tooltip-row">
              <span>{point.yoyMonthLabel}</span>
              <strong>{yoyQuarterKey ? fmtMoney(point.yoy) : '—'}</strong>
            </div>
            <div className="dashboard-tooltip-row">
              <span>同比差值</span>
              <strong>{yoyDelta === null ? '—' : fmtMoney(yoyDelta)}</strong>
            </div>
          </>
        )}
        {(point.missingCurrent || point.missingQoq || point.missingYoy) && (
          <div className="dashboard-tooltip-note">浅色柱表示该月缺失数据，已按 0 展示。</div>
        )}
      </div>
    )
  }

  if (loading) {
    return (
      <div className="dashboard">
        <div className="chart-card"><Skeleton width="100%" height={54} /></div>
        <div className="dashboard-kpi-grid">
          <div className="stat-card"><Skeleton width="100%" height={84} /></div>
          <div className="stat-card"><Skeleton width="100%" height={84} /></div>
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
          description="请上传消耗数据后开始分析"
          icon={<BarChart3 size={48} strokeWidth={1} />}
        />
      </div>
    )
  }

  const consumptionCard = granularity === 'month'
    ? {
      title: `${currentMonthLabel || '当前月'} 总消耗`,
      value: monthOverview?.consumption.value ?? 0,
      qoq: monthOverview?.consumption.momChange ?? 0,
      yoy: monthOverview?.consumption.yoyChange ?? 0,
    }
    : {
      title: `${currentQuarterLabel} 总消耗`,
      value: quarterOverview?.consumption.value ?? 0,
      qoq: quarterOverview?.consumption.qoqChange ?? 0,
      yoy: quarterOverview?.consumption.yoyChange ?? 0,
    }
  const feeCard = granularity === 'month'
    ? {
      title: `${currentMonthLabel || '当前月'} 服务费`,
      value: monthOverview?.fee.value ?? 0,
      qoq: monthOverview?.fee.momChange ?? 0,
      yoy: monthOverview?.fee.yoyChange ?? 0,
    }
    : {
      title: `${currentQuarterLabel} 服务费`,
      value: quarterOverview?.fee.value ?? 0,
      qoq: quarterOverview?.fee.qoqChange ?? 0,
      yoy: quarterOverview?.fee.yoyChange ?? 0,
    }

  const renderMonthTableRows = () => {
    const rows = monthWorkbenchView === 'mom'
      ? monthMomRows
      : monthWorkbenchView === 'yoy'
        ? monthYoyRows
        : monthDualRows

    if (!rows.length) {
      return <div className="dashboard-hint">当前月份暂无可分析的客户数据。</div>
    }

    if (monthWorkbenchView === 'dual') {
      return (
        <div className="quarter-workbench-table-wrap">
          <table className="quarter-workbench-table">
            <thead>
              <tr>
                <th>排名</th>
                <th>客户</th>
                <th>本期</th>
                <th>上月</th>
                <th>去年同月</th>
                <th>环比增量</th>
                <th>同比增量</th>
                <th>环比名次</th>
                <th>同比名次</th>
                <th>占比</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.name} onClick={() => setSelectedClient(row.name)}>
                  <td>{row.rank}</td>
                  <td className="client-col">{row.name}</td>
                  <td>{fmtMoney(row.curr)}</td>
                  <td>{row.prevMonth === null ? '—' : fmtMoney(row.prevMonth)}</td>
                  <td>{row.yoy === null ? '—' : fmtMoney(row.yoy)}</td>
                  <td className={row.momDelta !== null && row.momDelta >= 0 ? 'positive' : 'negative'}>{row.momDelta === null ? '—' : fmtMoney(row.momDelta)}</td>
                  <td className={row.yoyDelta !== null && row.yoyDelta >= 0 ? 'positive' : 'negative'}>{row.yoyDelta === null ? '—' : fmtMoney(row.yoyDelta)}</td>
                  <td className={row.momRankChange !== null && row.momRankChange >= 0 ? 'positive' : 'negative'}>{formatRankChange(row.momRankChange)}</td>
                  <td className={row.yoyRankChange !== null && row.yoyRankChange >= 0 ? 'positive' : 'negative'}>{formatRankChange(row.yoyRankChange)}</td>
                  <td>{row.share.toFixed(1)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )
    }

    if (monthWorkbenchView === 'mom') {
      return (
        <div className="quarter-workbench-table-wrap">
          <table className="quarter-workbench-table">
            <thead>
              <tr>
                <th>排名</th>
                <th>客户</th>
                <th>本期</th>
                <th>上月</th>
                <th>环比增量</th>
                <th>环比增幅</th>
                <th>名次变化</th>
                <th>占比</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.name} onClick={() => setSelectedClient(row.name)}>
                  <td>{row.rank}</td>
                  <td className="client-col">{row.name}</td>
                  <td>{fmtMoney(row.curr)}</td>
                  <td>{row.prevMonth === null ? '—' : fmtMoney(row.prevMonth)}</td>
                  <td className={row.momDelta !== null && row.momDelta >= 0 ? 'positive' : 'negative'}>{row.momDelta === null ? '—' : fmtMoney(row.momDelta)}</td>
                  <td className={row.momDeltaPct !== null && row.momDeltaPct >= 0 ? 'positive' : 'negative'}>{row.momDeltaPct === null ? '—' : fmtPct(row.momDeltaPct)}</td>
                  <td className={row.momRankChange !== null && row.momRankChange >= 0 ? 'positive' : 'negative'}>{formatRankChange(row.momRankChange)}</td>
                  <td>{row.share.toFixed(1)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )
    }

    return (
      <div className="quarter-workbench-table-wrap">
        <table className="quarter-workbench-table">
          <thead>
            <tr>
              <th>排名</th>
              <th>客户</th>
              <th>本期</th>
              <th>去年同月</th>
              <th>同比增量</th>
              <th>同比增幅</th>
              <th>名次变化</th>
              <th>占比</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.name} onClick={() => setSelectedClient(row.name)}>
                <td>{row.rank}</td>
                <td className="client-col">{row.name}</td>
                <td>{fmtMoney(row.curr)}</td>
                <td>{row.yoy === null ? '—' : fmtMoney(row.yoy)}</td>
                <td className={row.yoyDelta !== null && row.yoyDelta >= 0 ? 'positive' : 'negative'}>{row.yoyDelta === null ? '—' : fmtMoney(row.yoyDelta)}</td>
                <td className={row.yoyDeltaPct !== null && row.yoyDeltaPct >= 0 ? 'positive' : 'negative'}>{row.yoyDeltaPct === null ? '—' : fmtPct(row.yoyDeltaPct)}</td>
                <td className={row.yoyRankChange !== null && row.yoyRankChange >= 0 ? 'positive' : 'negative'}>{formatRankChange(row.yoyRankChange)}</td>
                <td>{row.share.toFixed(1)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  }

  const renderMonthView = () => (
    <div className="dashboard-month-grid">
      <div className="chart-card dashboard-main-trend-card">
        <div className="dashboard-card-header">
          <div>
            <h3>{metric === 'consumption' ? '月度消耗趋势工作台' : '月度服务费趋势工作台'}</h3>
          </div>
        </div>

        <div className="quarter-summary-grid month-summary-grid">
          {monthSummaryCards.map((card) => (
            <div key={card.label} className={`quarter-summary-card ${card.tone}`}>
              <span className="quarter-summary-label">{card.label}</span>
              <strong className="quarter-summary-value">{card.value}</strong>
              <span className="quarter-summary-meta">{card.meta}</span>
            </div>
          ))}
        </div>

        <div className="chart-container month-chart-container">
          <ResponsiveContainer width="100%" height={320}>
            <LineChart
              data={monthTrendData}
              onClick={(event: unknown) => {
                const payload = (event as { activePayload?: Array<{ payload?: { periodKey?: string } }> } | undefined)?.activePayload
                const key = payload?.[0]?.payload?.periodKey
                if (key) {
                  monthSelectionModeRef.current = 'manual'
                  setActiveMonthKey(key)
                }
              }}
            >
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E2E8F0" />
              <XAxis
                dataKey="label"
                axisLine={false}
                tickLine={false}
                fontSize={12}
                tickMargin={14}
                stroke="#64748B"
                interval={0}
                minTickGap={0}
              />
              <YAxis axisLine={false} tickLine={false} fontSize={12} tickFormatter={(value) => fmtCompact(Number(value))} stroke="#64748B" />
              <Tooltip content={monthTooltip} />
              {currentMonthLabel && <ReferenceLine x={currentMonthLabel} stroke="#C7D2FE" strokeDasharray="4 4" />}
              <Line
                type="monotone"
                dataKey="curr"
                stroke="#4F46E5"
                strokeWidth={3}
                dot={(props: { cx?: number; cy?: number; payload?: TrendPoint }) => (
                  <circle
                    cx={props.cx}
                    cy={props.cy}
                    r={props.payload?.isActive ? 6 : 3}
                    fill={props.payload?.isActive ? '#4338CA' : '#4F46E5'}
                    stroke="#fff"
                    strokeWidth={props.payload?.isActive ? 2 : 1}
                  />
                )}
                activeDot={{ r: 7 }}
              />
              {monthTrendData.some((item) => item.yoyValue !== null) && (
                <Line type="monotone" dataKey="yoyValue" stroke="#0EA5E9" strokeWidth={2.5} strokeDasharray="6 4" dot={false} />
              )}
            </LineChart>
          </ResponsiveContainer>
        </div>

        <div className="month-chart-note">
          <span>点击任意月份节点，右侧工作台和上方摘要会同步切到该月份。</span>
          <span>当前 {currentMonthLabel || '—'} · 环比 {prevMonthKey || '—'} · 同比 {yoyMonthKey || '—'}</span>
        </div>
      </div>

      <div className="chart-card dashboard-workbench-card">
        <div className="dashboard-card-header">
          <div>
            <h3>{currentMonthLabel || '当前月'} 月度客户工作台</h3>
          </div>
        </div>

        <div className="dashboard-workbench-tabs">
          {MONTH_VIEW_OPTIONS.map((option) => (
            <button
              key={option.key}
              type="button"
              className={`dashboard-workbench-tab ${monthWorkbenchView === option.key ? 'active' : ''}`}
              onClick={() => setMonthWorkbenchView(option.key)}
            >
              {option.label}
            </button>
          ))}
        </div>

        <div className="dashboard-hint" style={{ marginBottom: '0.7rem' }}>
          当前口径：本期 {currentMonthLabel || '—'} / 环比 {prevMonthKey || '—'} / 同比 {yoyMonthKey || '—'}
        </div>
        {showMonthCompareSyncWarning && (
          <div className="dashboard-hint warning" style={{ marginBottom: '0.7rem' }}>
            检测到后端仍返回旧版月度对比结构，当前环比/同比列可能为空。请以管理员权限重启 `billing-backend` 服务后再刷新页面。
          </div>
        )}

        {monthWorkbenchView === 'share' ? (
          <div className="top-share-list">
            {monthShareRows.map((row, index) => (
              <button type="button" key={row.name} className="top-share-row" onClick={() => setSelectedClient(row.name)}>
                <div className="top-share-main">
                  <span>{index + 1}. {row.name}</span>
                  <span>{fmtMoney(row.curr)}</span>
                </div>
                <div className="top-share-track">
                  <div className="top-share-fill" style={{ width: `${Math.min(row.share, 100)}%` }} />
                </div>
                <span className="top-share-pct">{row.share.toFixed(1)}%</span>
              </button>
            ))}
            {!monthShareRows.length && <div className="dashboard-hint">当前月份暂无客户数据。</div>}
          </div>
        ) : renderMonthTableRows()}
      </div>
    </div>
  )

  const renderQuarterTableRows = () => {
    const rows = quarterWorkbenchView === 'qoq'
      ? quarterQoqRows
      : quarterWorkbenchView === 'yoy'
        ? quarterYoyRows
        : quarterDualRows

    if (!rows.length) {
      return <div className="dashboard-hint">当前季度暂无可分析的客户数据。</div>
    }

    if (quarterWorkbenchView === 'dual') {
      return (
        <div className="quarter-workbench-table-wrap">
          <table className="quarter-workbench-table">
            <thead>
              <tr>
                <th>排名</th>
                <th>客户</th>
                <th>本期</th>
                <th>上季度</th>
                <th>去年同季</th>
                <th>环比增量</th>
                <th>同比增量</th>
                <th>环比名次</th>
                <th>同比名次</th>
                <th>占比</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.name} onClick={() => setSelectedClient(row.name)}>
                  <td>{row.rank}</td>
                  <td className="client-col">{row.name}</td>
                  <td>{fmtMoney(row.curr)}</td>
                  <td>{row.prevQuarter === null ? '—' : fmtMoney(row.prevQuarter)}</td>
                  <td>{row.yoy === null ? '—' : fmtMoney(row.yoy)}</td>
                  <td className={row.qoqDelta !== null && row.qoqDelta >= 0 ? 'positive' : 'negative'}>{row.qoqDelta === null ? '—' : fmtMoney(row.qoqDelta)}</td>
                  <td className={row.yoyDelta !== null && row.yoyDelta >= 0 ? 'positive' : 'negative'}>{row.yoyDelta === null ? '—' : fmtMoney(row.yoyDelta)}</td>
                  <td className={row.qoqRankChange !== null && row.qoqRankChange >= 0 ? 'positive' : 'negative'}>{formatRankChange(row.qoqRankChange)}</td>
                  <td className={row.yoyRankChange !== null && row.yoyRankChange >= 0 ? 'positive' : 'negative'}>{formatRankChange(row.yoyRankChange)}</td>
                  <td>{row.share.toFixed(1)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )
    }

    if (quarterWorkbenchView === 'qoq') {
      return (
        <div className="quarter-workbench-table-wrap">
          <table className="quarter-workbench-table">
            <thead>
              <tr>
                <th>排名</th>
                <th>客户</th>
                <th>本期</th>
                <th>上季度</th>
                <th>环比增量</th>
                <th>环比增幅</th>
                <th>名次变化</th>
                <th>占比</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.name} onClick={() => setSelectedClient(row.name)}>
                  <td>{row.rank}</td>
                  <td className="client-col">{row.name}</td>
                  <td>{fmtMoney(row.curr)}</td>
                  <td>{row.prevQuarter === null ? '—' : fmtMoney(row.prevQuarter)}</td>
                  <td className={row.qoqDelta !== null && row.qoqDelta >= 0 ? 'positive' : 'negative'}>{row.qoqDelta === null ? '—' : fmtMoney(row.qoqDelta)}</td>
                  <td className={row.qoqDeltaPct !== null && row.qoqDeltaPct >= 0 ? 'positive' : 'negative'}>{row.qoqDeltaPct === null ? '—' : fmtPct(row.qoqDeltaPct)}</td>
                  <td className={row.qoqRankChange !== null && row.qoqRankChange >= 0 ? 'positive' : 'negative'}>{formatRankChange(row.qoqRankChange)}</td>
                  <td>{row.share.toFixed(1)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )
    }

    return (
      <div className="quarter-workbench-table-wrap">
        <table className="quarter-workbench-table">
          <thead>
            <tr>
              <th>排名</th>
              <th>客户</th>
              <th>本期</th>
              <th>去年同季</th>
              <th>同比增量</th>
              <th>同比增幅</th>
              <th>名次变化</th>
              <th>占比</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.name} onClick={() => setSelectedClient(row.name)}>
                <td>{row.rank}</td>
                <td className="client-col">{row.name}</td>
                <td>{fmtMoney(row.curr)}</td>
                <td>{row.yoy === null ? '—' : fmtMoney(row.yoy)}</td>
                <td className={row.yoyDelta !== null && row.yoyDelta >= 0 ? 'positive' : 'negative'}>{row.yoyDelta === null ? '—' : fmtMoney(row.yoyDelta)}</td>
                <td className={row.yoyDeltaPct !== null && row.yoyDeltaPct >= 0 ? 'positive' : 'negative'}>{row.yoyDeltaPct === null ? '—' : fmtPct(row.yoyDeltaPct)}</td>
                <td className={row.yoyRankChange !== null && row.yoyRankChange >= 0 ? 'positive' : 'negative'}>{formatRankChange(row.yoyRankChange)}</td>
                <td>{row.share.toFixed(1)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  }

  const renderQuarterView = () => (
    <div className="dashboard-quarter-grid">
      <div className="chart-card dashboard-main-trend-card dashboard-quarter-main-card">
        <div className="dashboard-card-header">
          <div>
            <h3>{currentQuarterLabel} 季度构成图</h3>
            <p>把当前季度、上季度、去年同季放在同一张图里，直接对比季度内三个月的结构变化。</p>
          </div>
        </div>

        <div className="quarter-summary-grid">
          {quarterSummaryCards.map((card) => (
            <div key={card.label} className={`quarter-summary-card ${card.tone}`}>
              <span className="quarter-summary-label">{card.label}</span>
              <strong className="quarter-summary-value">{card.value}</strong>
              <span className="quarter-summary-meta">{card.meta}</span>
            </div>
          ))}
        </div>

        <div className="chart-container quarter-chart-container">
          <ResponsiveContainer width="100%" height={320}>
            <BarChart data={quarterChartData} barGap={8}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E2E8F0" />
              <XAxis dataKey="slot" axisLine={false} tickLine={false} fontSize={12} tickMargin={14} stroke="#64748B" />
              <YAxis axisLine={false} tickLine={false} fontSize={12} tickFormatter={(value) => fmtCompact(Number(value))} stroke="#64748B" />
              <Tooltip content={quarterTooltip} />
              <Legend verticalAlign="top" align="right" iconType="circle" />
              <Bar dataKey="curr" name={currentQuarterLabel} radius={[8, 8, 0, 0]} fill="#4F46E5">
                {quarterChartData.map((point) => (
                  <Cell key={`curr-${point.slot}`} fill="#4F46E5" fillOpacity={point.missingCurrent ? 0.18 : 1} />
                ))}
              </Bar>
              {(quarterCompareMode === 'qoq' || quarterCompareMode === 'dual') && (
                <Bar dataKey="qoq" name={formatQuarterLabel(qoqQuarterKey)} radius={[8, 8, 0, 0]} fill="#0EA5E9">
                  {quarterChartData.map((point) => (
                    <Cell key={`qoq-${point.slot}`} fill="#0EA5E9" fillOpacity={point.missingQoq ? 0.18 : 0.92} />
                  ))}
                </Bar>
              )}
              {(quarterCompareMode === 'yoy' || quarterCompareMode === 'dual') && (
                <Bar dataKey="yoy" name={formatQuarterLabel(yoyQuarterKey)} radius={[8, 8, 0, 0]} fill="#10B981">
                  {quarterChartData.map((point) => (
                    <Cell key={`yoy-${point.slot}`} fill="#10B981" fillOpacity={point.missingYoy ? 0.18 : 0.92} />
                  ))}
                </Bar>
              )}
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="quarter-chart-note">
          <span>浅色柱表示该月缺失数据，已按 0 展示。</span>
          <span>当前 {currentQuarterLabel} · 环比 {formatQuarterLabel(qoqQuarterKey)} · 同比 {formatQuarterLabel(yoyQuarterKey)}</span>
        </div>
      </div>

      <div className="chart-card dashboard-workbench-card">
        <div className="dashboard-card-header">
          <div>
            <h3>{currentQuarterLabel} 季度客户工作台</h3>
          </div>
        </div>

        <div className="dashboard-workbench-tabs">
          {QUARTER_VIEW_OPTIONS.map((option) => (
            <button
              key={option.key}
              type="button"
              className={`dashboard-workbench-tab ${quarterWorkbenchView === option.key ? 'active' : ''}`}
              onClick={() => setQuarterWorkbenchView(option.key)}
            >
              {option.label}
            </button>
          ))}
        </div>

        <div className="dashboard-hint" style={{ marginBottom: '0.7rem' }}>
          当前口径：本期 {currentQuarterLabel} / 环比 {formatQuarterLabel(qoqQuarterKey)} / 同比 {formatQuarterLabel(yoyQuarterKey)}
        </div>

        {quarterWorkbenchView === 'share' ? (
          <div className="top-share-list">
            {quarterShareRows.map((row, index) => (
              <button type="button" key={row.name} className="top-share-row" onClick={() => setSelectedClient(row.name)}>
                <div className="top-share-main">
                  <span>{index + 1}. {row.name}</span>
                  <span>{fmtMoney(row.curr)}</span>
                </div>
                <div className="top-share-track">
                  <div className="top-share-fill" style={{ width: `${Math.min(row.share, 100)}%` }} />
                </div>
                <span className="top-share-pct">{row.share.toFixed(1)}%</span>
              </button>
            ))}
            {!quarterShareRows.length && <div className="dashboard-hint">当前季度暂无客户数据。</div>}
          </div>
        ) : renderQuarterTableRows()}
      </div>
    </div>
  )

  return (
    <div className="dashboard">
      <div className="dashboard-control-wrap">
        <div className="dashboard-toolbar-group">
          <span className="dashboard-toolbar-title">指标</span>
          <div className="dashboard-chip-group">
            <button type="button" className={`dashboard-chip ${metric === 'consumption' ? 'active' : ''}`} onClick={() => setMetric('consumption')}>消耗金额</button>
            <button type="button" className={`dashboard-chip ${metric === 'fee' ? 'active' : ''}`} onClick={() => setMetric('fee')}>服务费</button>
          </div>
        </div>

        <div className="dashboard-toolbar-group">
          <span className="dashboard-toolbar-title">时间维度</span>
          <div className="dashboard-chip-group">
            <button type="button" className={`dashboard-chip ${granularity === 'month' ? 'active' : ''}`} onClick={() => setGranularity('month')}>月度</button>
            <button type="button" className={`dashboard-chip ${granularity === 'quarter' ? 'active' : ''}`} onClick={() => setGranularity('quarter')}>季度</button>
          </div>
        </div>

        {granularity === 'month' ? (
          <div className="dashboard-toolbar-group">
            <span className="dashboard-toolbar-title">月度窗口</span>
            <div className="dashboard-chip-group">
              {MONTH_WINDOW_OPTIONS.map((window) => (
                <button key={window} type="button" className={`dashboard-chip ${monthWindowSize === window ? 'active' : ''}`} onClick={() => setMonthWindowSize(window)}>
                  {window} 个月
                </button>
              ))}
            </div>
          </div>
        ) : (
          <>
            <div className="dashboard-toolbar-group">
              <span className="dashboard-toolbar-title">分析年份</span>
              <div className="dashboard-select">
                <select value={quarterYear} onChange={(event) => setQuarterYear(Number(event.target.value))}>
                  {availableQuarterYears.map((year) => (
                    <option key={year} value={year}>{year} 年</option>
                  ))}
                </select>
              </div>
            </div>
            <div className="dashboard-toolbar-group">
              <span className="dashboard-toolbar-title">分析季度</span>
              <div className="dashboard-chip-group">
                {[1, 2, 3, 4].map((quarter) => (
                  <button
                    key={quarter}
                    type="button"
                    disabled={!availableQuarterNumbers.includes(quarter)}
                    className={`dashboard-chip ${quarterNumber === quarter ? 'active' : ''}`}
                    onClick={() => setQuarterNumber(quarter)}
                  >
                    Q{quarter}
                  </button>
                ))}
              </div>
            </div>
          </>
        )}
      </div>

      <div className="dashboard-kpi-grid">
        <StatCard title={consumptionCard.title} value={consumptionCard.value} mom={consumptionCard.qoq} yoy={consumptionCard.yoy} icon={Activity} color="blue" />
        <StatCard title={feeCard.title} value={feeCard.value} mom={feeCard.qoq} yoy={feeCard.yoy} icon={DollarSign} color="purple" />
      </div>

      {granularity === 'month' ? renderMonthView() : renderQuarterView()}

      {selectedClient && <ClientTrendModal clientName={selectedClient} onClose={() => setSelectedClient(null)} />}
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
  <div className="dashboard-kpi-card">
    <div className="dashboard-kpi-header">
      <span className="dashboard-kpi-label">{title}</span>
      <div className={`dashboard-kpi-icon ${color}`}>
        <Icon size={17} />
      </div>
    </div>
    <div className="dashboard-kpi-body">
      <span className="dashboard-kpi-value">{fmtMoney(value)}</span>
      <div className="dashboard-kpi-deltas">
        <div className={`dashboard-kpi-change ${mom >= 0 ? 'up' : 'down'}`}>
          {mom >= 0 ? <TrendingUp size={13} /> : <TrendingDown size={13} />}
          <span>环比 {fmtPct(mom)}</span>
        </div>
        <div className={`dashboard-kpi-change ${yoy >= 0 ? 'up' : 'down'}`}>
          {yoy >= 0 ? <TrendingUp size={13} /> : <TrendingDown size={13} />}
          <span>同比 {fmtPct(yoy)}</span>
        </div>
      </div>
    </div>
  </div>
)
