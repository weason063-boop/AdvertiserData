
import { useState, useEffect } from 'react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { X, TrendingUp, BarChart3, Search } from 'lucide-react'
import { Skeleton } from './Skeleton'
import { EmptyState } from './EmptyState'
import { apiJson } from './apiClient'


interface ClientTrendModalProps {
    clientName: string
    onClose: () => void
}

interface TrendData {
    month: string
    consumption: number
    service_fee: number
}

interface TrendResponse {
    client_name: string
    data: TrendData[]
    summary: {
        total_consumption: number
        avg_monthly: number
        peak_month: string | null
        peak_value: number
    }
}

export function ClientTrendModal({ clientName, onClose }: ClientTrendModalProps) {
    const [loading, setLoading] = useState(true)
    const [trendData, setTrendData] = useState<TrendResponse | null>(null)

    // Comparison State
    const [compareClient, setCompareClient] = useState<string | null>(null)
    const [compareData, setCompareData] = useState<TrendResponse | null>(null)
    const [searchTerm, setSearchTerm] = useState('')
    const [searchResults, setSearchResults] = useState<any[]>([])
    const [showSearch, setShowSearch] = useState(false)

    useEffect(() => {
        const fetchTrend = async () => {
            try {
                const { data } = await apiJson<TrendResponse>(
                    `/api/dashboard/client/${encodeURIComponent(clientName)}/trend`,
                )
                setTrendData(data)
            } catch (error) {
                console.error('Failed to fetch client trend:', error)
            } finally {
                setLoading(false)
            }
        }

        fetchTrend()

        // ESC键关闭
        const handleEsc = (e: KeyboardEvent) => {
            if (e.key === 'Escape') onClose()
        }
        window.addEventListener('keydown', handleEsc)
        return () => window.removeEventListener('keydown', handleEsc)
    }, [clientName, onClose])

    // Search Logic
    useEffect(() => {
        if (!searchTerm) {
            setSearchResults([])
            return
        }
        const timer = setTimeout(async () => {
            try {
                const { data } = await apiJson<{ clients: any[] }>(
                    `/api/clients?search=${encodeURIComponent(searchTerm)}`,
                )
                // Filter out current client
                setSearchResults(data.clients.filter((c: any) => c.name !== clientName))
            } catch (e) {
                console.error(e)
            }
        }, 300)
        return () => clearTimeout(timer)
    }, [searchTerm, clientName])

    // Fetch Comparison Data
    useEffect(() => {
        if (!compareClient) {
            setCompareData(null)
            return
        }
        const fetchCompare = async () => {
            try {
                const { data } = await apiJson<TrendResponse>(
                    `/api/dashboard/client/${encodeURIComponent(compareClient)}/trend`,
                )
                setCompareData(data)
            } catch (error) {
                console.error('Failed to fetch comparison data:', error)
            }
        }
        fetchCompare()
    }, [compareClient])

    const formatCurrency = (val: number) =>
        new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(val)

    // Prepare Chart Data
    const chartData = trendData?.data.map(item => {
        const compareItem = compareData?.data.find(d => d.month === item.month)
        return {
            ...item,
            consumption_compare: compareItem ? compareItem.consumption : undefined
        }
    }) || []

    return (
        <div className="modal-overlay" onClick={onClose}>
            <div className="modal-card" onClick={e => e.stopPropagation()}>
                {/* Header */}
                <div className="modal-header">
                    <div className="modal-title">
                        <TrendingUp size={24} className="modal-icon" />
                        <h2>{clientName}</h2>
                        {compareClient && (
                            <span className="compare-pill">
                                vs {compareClient}
                                <button onClick={() => setCompareClient(null)}>
                                    <X size={12} />
                                </button>
                            </span>
                        )}
                    </div>

                    <div className="modal-actions">
                        {!compareClient && (
                            <div className="search-wrapper">
                                {showSearch ? (
                                    <div className="search-input-box">
                                        <Search size={14} className="search-icon-input" />
                                        <input
                                            autoFocus
                                            placeholder="搜索对比客户..."
                                            value={searchTerm}
                                            onChange={e => setSearchTerm(e.target.value)}
                                            onBlur={() => setTimeout(() => setShowSearch(false), 200)}
                                        />
                                        {searchResults.length > 0 && (
                                            <div className="search-dropdown">
                                                {searchResults.map(c => (
                                                    <div
                                                        key={c.id}
                                                        className="search-item"
                                                        onClick={() => {
                                                            setCompareClient(c.name)
                                                            setShowSearch(false)
                                                            setSearchTerm('')
                                                        }}
                                                    >
                                                        {c.name}
                                                    </div>
                                                ))}
                                            </div>
                                        )}
                                    </div>
                                ) : (
                                    <button className="btn-compare" onClick={() => setShowSearch(true)}>
                                        <Search size={14} />
                                        <span>对比</span>
                                    </button>
                                )}
                            </div>
                        )}
                        <button className="modal-close-btn" onClick={onClose}>
                            <X size={20} />
                        </button>
                    </div>
                </div>

                {/* Content */}
                <div className="modal-body">
                    {loading ? (
                        <div className="modal-loading-skeleton">
                            {/* Chart Placeholder */}
                            <Skeleton width="100%" height={300} className="mb-4" />

                            {/* Stats Placeholder - utilizing grid layout from CSS */}
                            <div className="modal-stats">
                                <div className="stat-item">
                                    <Skeleton width={60} height={20} className="mb-2" />
                                    <Skeleton width="100%" height={32} />
                                </div>
                                <div className="stat-item">
                                    <Skeleton width={80} height={20} className="mb-2" />
                                    <Skeleton width="100%" height={32} />
                                </div>
                                <div className="stat-item">
                                    <Skeleton width={60} height={20} className="mb-2" />
                                    <Skeleton width="100%" height={32} />
                                </div>
                            </div>
                        </div>
                    ) : !trendData || trendData.data.length === 0 ? (
                        <div className="modal-empty-section py-8">
                            <EmptyState
                                title="暂无历史数据"
                                description="该客户没有相关的消耗记录"
                                icon={<BarChart3 size={48} strokeWidth={1} />}
                            />
                        </div>
                    ) : (
                        <>
                            {/* Chart */}
                            <div className="modal-chart">
                                <ResponsiveContainer width="100%" height={300}>
                                    <LineChart data={chartData}>
                                        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E2E8F0" />
                                        <XAxis
                                            dataKey="month"
                                            axisLine={false}
                                            tickLine={false}
                                            fontSize={12}
                                            tickMargin={15}
                                            stroke="#64748B"
                                            interval={0}
                                        />
                                        <YAxis
                                            axisLine={false}
                                            tickLine={false}
                                            fontSize={12}
                                            tickFormatter={(val) => `$${(val / 1000).toFixed(0)}k`}
                                            stroke="#64748B"
                                        />
                                        <Tooltip
                                            contentStyle={{
                                                borderRadius: '12px',
                                                border: 'none',
                                                boxShadow: '0 10px 15px -3px rgba(0,0,0,0.1)',
                                                padding: '12px 16px'
                                            }}
                                            formatter={(val: any, name: any) => [
                                                formatCurrency(val),
                                                name === 'consumption' ? clientName : name === 'consumption_compare' ? compareClient : name
                                            ]}
                                            labelStyle={{ color: '#64748B', marginBottom: '4px' }}
                                        />
                                        <Line
                                            type="monotone"
                                            dataKey="consumption"
                                            name="consumption"
                                            stroke="#4F46E5"
                                            strokeWidth={3}
                                            dot={{ r: 4, fill: '#4F46E5', strokeWidth: 2, stroke: '#fff' }}
                                            activeDot={{ r: 6, fill: '#4F46E5' }}
                                            isAnimationActive={false}
                                        />
                                        {compareClient && (
                                            <Line
                                                type="monotone"
                                                dataKey="consumption_compare"
                                                name="consumption_compare"
                                                stroke="#F97316"
                                                strokeWidth={3}
                                                strokeDasharray="5 5"
                                                dot={{ r: 4, fill: '#F97316', strokeWidth: 2, stroke: '#fff' }}
                                                activeDot={{ r: 6, fill: '#F97316' }}
                                                isAnimationActive={false}
                                            />
                                        )}
                                    </LineChart>
                                </ResponsiveContainer>
                            </div>

                            {/* Statistics */}
                            <div className="modal-stats">
                                <div className="stat-item">
                                    <span className="stat-label">总消耗</span>
                                    <span className="stat-value">{formatCurrency(trendData.summary.total_consumption)}</span>
                                </div>
                                <div className="stat-item">
                                    <span className="stat-label">平均月消耗</span>
                                    <span className="stat-value">{formatCurrency(trendData.summary.avg_monthly)}</span>
                                </div>
                                <div className="stat-item">
                                    <span className="stat-label">最高月份</span>
                                    <span className="stat-value">
                                        {trendData.summary.peak_month}
                                        <span className="stat-peak">({formatCurrency(trendData.summary.peak_value)})</span>
                                    </span>
                                </div>
                            </div>
                        </>
                    )}
                </div>
            </div>
        </div>
    )
}
