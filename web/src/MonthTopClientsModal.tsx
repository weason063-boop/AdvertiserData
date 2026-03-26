import { useState, useEffect } from 'react'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { X, TrendingUp } from 'lucide-react'
import { Skeleton } from './Skeleton'
import { EmptyState } from './EmptyState'
import { ClientTrendModal } from './ClientTrendModal'
import { apiJson } from './apiClient'
import './ClientTrendModal.css' // Reuse existing modal styles

interface MonthTopClientsModalProps {
    month: string
    onClose: () => void
}

interface ClientData {
    client_name: string
    consumption: number
    service_fee: number
}

interface MonthTopClientsResponse {
    month: string
    clients: ClientData[]
}

export function MonthTopClientsModal({ month, onClose }: MonthTopClientsModalProps) {
    const [loading, setLoading] = useState(true)
    const [data, setData] = useState<MonthTopClientsResponse | null>(null)
    const [selectedClient, setSelectedClient] = useState<string | null>(null)

    useEffect(() => {
        const fetchData = async () => {
            try {
                const { data: result } = await apiJson<MonthTopClientsResponse>(`/api/dashboard/month/${month}/top-clients`)
                setData(result)
            } catch (error) {
                console.error('Failed to load month top clients:', error)
            } finally {
                setLoading(false)
            }
        }

        fetchData()
    }, [month])

    const formatCurrency = (val: number) =>
        new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(val)

    if (selectedClient) {
        return <ClientTrendModal clientName={selectedClient} onClose={() => setSelectedClient(null)} />
    }

    return (
        <div className="modal-overlay" onClick={onClose}>
            <div className="modal-card" onClick={(e) => e.stopPropagation()}>
                <div className="modal-header">
                    <div>
                        <h2 className="modal-title">{month} TOP 10 客户</h2>
                        <p className="modal-subtitle">点击客户查看历史趋势</p>
                    </div>
                    <button className="modal-close-btn" onClick={onClose}>
                        <X size={20} />
                    </button>
                </div>

                <div className="modal-body">
                    {loading ? (
                        <div className="modal-chart">
                            <Skeleton width="100%" height={400} />
                        </div>
                    ) : !data || data.clients.length === 0 ? (
                        <EmptyState
                            title="暂无数据"
                            description="该月份没有客户数据"
                            icon={<TrendingUp size={48} strokeWidth={1} />}
                        />
                    ) : (
                        <div className="modal-chart">
                            <ResponsiveContainer width="100%" height={300}>
                                <BarChart
                                    data={data.clients}
                                    layout="vertical"
                                    margin={{ left: 20, right: 20 }}
                                    barSize={12}
                                >
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
                                        contentStyle={{
                                            borderRadius: '12px',
                                            border: 'none',
                                            boxShadow: '0 10px 15px -3px rgba(0,0,0,0.1)',
                                            padding: '12px 16px'
                                        }}
                                        formatter={(val: any) => [formatCurrency(val), '消耗金额']}
                                    />
                                    <Bar
                                        dataKey="consumption"
                                        fill="#4F46E5"
                                        radius={[0, 4, 4, 0]}
                                        cursor="pointer"
                                        onClick={(data: any) => setSelectedClient(data.client_name)}
                                        isAnimationActive={false}
                                    />
                                </BarChart>
                            </ResponsiveContainer>
                        </div>
                    )}
                </div>
            </div>
        </div>
    )
}
