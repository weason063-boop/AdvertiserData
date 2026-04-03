import { useState } from 'react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar } from 'recharts'
import { TrendingUp, TrendingDown, DollarSign, Activity } from 'lucide-react'
import { ClientTrendModal } from './ClientTrendModal'
import { MonthTopClientsModal } from './MonthTopClientsModal'

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

import { Skeleton } from './Skeleton'
import { EmptyState } from './EmptyState'
import { BarChart3 } from 'lucide-react'
import { InsightsPanel } from './InsightsPanel'

interface DashboardProps {
    data: DashboardData
    loading?: boolean
}

export function Dashboard({ data, loading }: DashboardProps) {
    const { stats, trend, top_clients = [] } = data
    const [selectedClient, setSelectedClient] = useState<string | null>(null)
    const [selectedMonth, setSelectedMonth] = useState<string | null>(null)

    if (loading) {
        return (
            <div className="dashboard">
                <div className="dashboard-content">
                    <div className="stats-column">
                        <div className="stat-card">
                            <Skeleton width="40%" height={20} className="mb-4" />
                            <Skeleton width="60%" height={32} className="mb-4" />
                            <div className="stat-footer">
                                <Skeleton width="30%" height={24} />
                                <Skeleton width="30%" height={24} />
                            </div>
                        </div>
                        <div className="stat-card">
                            <Skeleton width="40%" height={20} className="mb-4" />
                            <Skeleton width="60%" height={32} className="mb-4" />
                            <div className="stat-footer">
                                <Skeleton width="30%" height={24} />
                                <Skeleton width="30%" height={24} />
                            </div>
                        </div>
                    </div>
                </div>
                <div className="dashboard-side">
                    <div className="chart-card">
                        <Skeleton width="30%" height={24} className="mb-4" />
                        <Skeleton width="100%" height={200} />
                    </div>
                    <div className="chart-card">
                        <Skeleton width="30%" height={24} className="mb-4" />
                        <Skeleton width="100%" height={200} />
                    </div>
                </div>
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

    return (
        <div className="dashboard">
            {/* Group 1: Stats & Trends (Top) */}
            <div className="dashboard-top">
                {/* Left Side: Stats & Top 20 */}
                <div className="dashboard-content">
                    {/* Stats */}
                    <div className="stats-column">
                        <StatCard
                            title="本月总消耗"
                            value={stats.consumption}
                            mom={stats.consumption_mom}
                            yoy={stats.consumption_yoy}
                            icon={Activity}
                            color="blue"
                        />
                        <StatCard
                            title="本月服务费"
                            value={stats.fee}
                            mom={stats.fee_mom}
                            yoy={stats.fee_yoy}
                            icon={DollarSign}
                            color="purple"
                        />
                    </div>

                    {/* Top 10 Clients */}
                    {top_clients.length > 0 && (
                        <div className="chart-card" style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
                            <h3>本月消耗 TOP 10 客户</h3>
                            <div className="chart-container" style={{ flex: 1 }}>
                                <ResponsiveContainer width="100%" height="100%">
                                    <BarChart data={top_clients} layout="vertical" margin={{ left: 20, right: 20 }} barSize={12}>
                                        <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#f1f5f9" />
                                        <XAxis type="number" hide />
                                        <YAxis
                                            dataKey="client_name"
                                            type="category"
                                            width={120}
                                            tickLine={false}
                                            axisLine={false}
                                            fontSize={13}
                                            interval={0}
                                            stroke="#64748b"
                                            tick={{ textAnchor: 'start', dx: -110 }}
                                        />
                                        <Tooltip
                                            cursor={{ fill: '#f8fafc' }}
                                            contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 10px 15px -3px rgba(0,0,0,0.1)', padding: '12px 16px' }}
                                            formatter={(val: any) => [formatCurrency(val), '消耗金额']}
                                        />
                                        <Bar
                                            dataKey="consumption"
                                            fill="#4F46E5"
                                            radius={[0, 4, 4, 0]}
                                            cursor="pointer"
                                            onClick={(data: any) => setSelectedClient(data.client_name)}
                                        />
                                    </BarChart>
                                </ResponsiveContainer>
                            </div>
                        </div>
                    )}
                </div>

                {/* Right Side: Trends */}
                <div className="dashboard-side">
                    {/* Consumption Trend */}
                    <div className="chart-card">
                        <h3>消耗金额趋势</h3>
                        <div className="chart-container">
                            <ResponsiveContainer width="100%" height="100%">
                                <BarChart data={trend.slice(-12)} barSize={40}>
                                    <defs>
                                        <linearGradient id="colorConsumption" x1="0" y1="0" x2="0" y2="1">
                                            <stop offset="0%" stopColor="#4F46E5" stopOpacity={1} />
                                            <stop offset="100%" stopColor="#6366F1" stopOpacity={0.9} />
                                        </linearGradient>
                                    </defs>
                                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E2E8F0" />
                                    <XAxis dataKey="month" axisLine={false} tickLine={false} fontSize={12} tickMargin={15} stroke="#64748B" />
                                    <YAxis axisLine={false} tickLine={false} fontSize={12} tickFormatter={(val) => `$${val / 1000}k`} stroke="#64748B" />
                                    <Tooltip
                                        cursor={{ fill: '#f8fafc' }}
                                        contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 10px 15px -3px rgba(0,0,0,0.1)', padding: '12px 16px' }}
                                        formatter={(val: any) => [formatCurrency(val), '消耗金额']}
                                    />
                                    <Bar
                                        dataKey="total_consumption"
                                        fill="url(#colorConsumption)"
                                        radius={[8, 8, 0, 0]}
                                        cursor="pointer"
                                        onClick={(data: any) => setSelectedMonth(data.month)}
                                    />
                                </BarChart>
                            </ResponsiveContainer>
                        </div>
                    </div>

                    {/* Fee Trend */}
                    <div className="chart-card">
                        <h3>服务费趋势</h3>
                        <div className="chart-container">
                            <ResponsiveContainer width="100%" height="100%">
                                <LineChart data={trend.slice(-12)}>
                                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E2E8F0" />
                                    <XAxis dataKey="month" axisLine={false} tickLine={false} fontSize={12} tickMargin={15} stroke="#64748B" />
                                    <YAxis axisLine={false} tickLine={false} fontSize={12} tickFormatter={(val) => `$${val}`} stroke="#64748B" />
                                    <Tooltip
                                        contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 10px 15px -3px rgba(0,0,0,0.1)', padding: '12px 16px' }}
                                        formatter={(val: any) => [formatCurrency(val), '服务费']}
                                    />
                                    <Line type="monotone" dataKey="total_service_fee" stroke="#0EA5E9" strokeWidth={4} dot={{ r: 4, fill: '#0EA5E9', strokeWidth: 2, stroke: '#fff' }} activeDot={{ r: 7, fill: '#0EA5E9' }} />
                                </LineChart>
                            </ResponsiveContainer>
                        </div>
                    </div>
                </div>
            </div>

            {/* Group 2: Insights (Bottom) */}
            <div className="dashboard-insights">
                <InsightsPanel />
            </div>

            {/* Client Trend Modal */}
            {selectedClient && (
                <ClientTrendModal
                    clientName={selectedClient}
                    onClose={() => setSelectedClient(null)}
                />
            )}

            {/* Month Top Clients Modal */}
            {selectedMonth && (
                <MonthTopClientsModal
                    month={selectedMonth}
                    onClose={() => setSelectedMonth(null)}
                />
            )}
        </div>
    )
}

const formatCurrency = (val: number) =>
    new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(val)

const formatPercent = (val: number) => {
    const abs = Math.abs(val).toFixed(1)
    return val >= 0 ? `+${abs}%` : `-${abs}%`
}

const StatCard = ({ title, value, mom, yoy, icon: Icon, color }: any) => (
    <div className="stat-card">
        <div className="stat-header">
            <span className="stat-title">{title}</span>
            <div className={`stat-icon ${color}`}>
                <Icon size={20} />
            </div>
        </div>
        <div className="stat-value">{formatCurrency(value)}</div>
        <div className="stat-footer">
            <div className={`stat-change ${mom >= 0 ? 'up' : 'down'}`}>
                {mom >= 0 ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
                <span>环比 {formatPercent(mom)}</span>
            </div>
            <div className={`stat-change ${yoy >= 0 ? 'up' : 'down'}`}>
                <span>同比 {formatPercent(yoy)}</span>
            </div>
        </div>
    </div>
)
