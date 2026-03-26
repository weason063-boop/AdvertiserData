
import { useEffect, useState } from 'react';
import { AreaChart, Area, XAxis, ResponsiveContainer, Tooltip } from 'recharts';
import { Skeleton } from './Skeleton';
import { AlertCircle, TriangleAlert, Sparkles, PieChart } from 'lucide-react';
import { apiJson } from './apiClient';
import './InsightsPanel.css';

interface InsightMetric {
    client: string;
    value?: number;
    change_pct?: number; // for anomaly
    type?: string;
    trend?: string; // for churn
    consecutive_months?: number;
    growth_amount?: number; // for growth
    recent_values?: number[]; // for churn sparkline
}

interface SegmentationData {
    count: number;
    value: number;
    pct: number;
    top_clients?: { client: string, value: number }[];
}

interface InsightsData {
    metrics: {
        anomalies: InsightMetric[];
        churn_risk: InsightMetric[];
        growth_stars: InsightMetric[];
    };
    segmentation: {
        whales: SegmentationData;
        core: SegmentationData;
        long_tail: SegmentationData;
    };
}

// Helper to format currency
const formatCurrency = (val: number | undefined) => {
    if (val === undefined) return '$0';
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(val);
}

export function InsightsPanel() {
    const [data, setData] = useState<InsightsData | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        apiJson<InsightsData>('/api/dashboard/insights')
            .then(({ data }) => data)
            .then(data => {
                setData(data);
                setLoading(false);
            })
            .catch(err => {
                console.error("Failed to fetch insights", err);
                setLoading(false);
            });
    }, []);

    if (loading) {
        return (
            <div className="insights-grid">
                {Array.from({ length: 4 }).map((_, i) => (
                    <div key={i} className="insight-card">
                        <Skeleton variant="text" width="60%" height={24} style={{ marginBottom: 16 }} />
                        <Skeleton variant="rect" width="100%" height={60} />
                    </div>
                ))}
            </div>
        );
    }

    if (!data || !data.metrics) return null;

    const { anomalies, churn_risk, growth_stars } = data.metrics;
    const { segmentation } = data;

    return (
        <div className="insights-grid">
            {/* 1. Anomaly Detection */}
            <div className="insight-card anomaly">
                <div className="insight-header">
                    <div className="insight-icon">
                        <AlertCircle size={18} />
                    </div>
                    <h3 className="insight-title">异动预警</h3>
                </div>
                <div className="insight-list">
                    {anomalies.length > 0 ? anomalies.map((item, idx) => (
                        <div key={idx} className="insight-item">
                            <div className="insight-item-main">
                                <span className="insight-client-name">{item.client}</span>
                                <span className="insight-detail">
                                    {item.type === 'surge' ? '暴涨' : '暴跌'} {Math.abs(item.change_pct || 0)}%
                                </span>
                            </div>
                            <span className={`insight-value ${item.type === 'surge' ? 'positive' : 'negative'}`}>
                                {formatCurrency(item.value)}
                            </span>
                        </div>
                    )) : <div className="empty-insight">暂无异常波动</div>}
                </div>
            </div>

            {/* 2. Churn Risk */}
            <div className="insight-card churn">
                <div className="insight-header">
                    <div className="insight-icon">
                        <TriangleAlert size={18} />
                    </div>
                    <h3 className="insight-title">流失风险</h3>
                </div>
                <div className="insight-list">
                    {churn_risk.length > 0 ? churn_risk.map((item, idx) => (
                        <div key={idx} className="insight-item">
                            <div className="insight-item-main" style={{ flex: 1 }}>
                                <span className="insight-client-name">{item.client}</span>
                                <span className="insight-detail">
                                    {item.trend === 'trend_to_zero' ? '本月无消耗' : `连续 ${item.consecutive_months} 月下滑`}
                                </span>
                            </div>
                            {/* Sparkline for Churn Trend */}
                            {item.recent_values && item.recent_values.length > 0 && (
                                <div style={{ width: 80, height: 32 }}>
                                    <ResponsiveContainer width="100%" height="100%">
                                        <AreaChart data={item.recent_values.map((v: any) => ({ month: v.month, val: v.consumption }))}>
                                            <XAxis dataKey="month" hide />
                                            <Tooltip
                                                contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)', padding: '4px 8px', fontSize: '12px' }}
                                                itemStyle={{ color: '#EF4444', padding: 0 }}
                                                labelStyle={{ color: '#94A3B8', marginBottom: '2px', fontSize: '10px' }}
                                                formatter={(value: any) => [formatCurrency(value), '']}
                                            />
                                            <Area type="monotone" dataKey="val" stroke="var(--danger)" fill="#FEF2F2" strokeWidth={2} />
                                        </AreaChart>
                                    </ResponsiveContainer>
                                </div>
                            )}
                        </div>
                    )) : <div className="empty-insight">客户状态稳定</div>}
                </div>
            </div>

            {/* 3. Growth Stars */}
            <div className="insight-card growth">
                <div className="insight-header">
                    <div className="insight-icon">
                        <Sparkles size={18} />
                    </div>
                    <h3 className="insight-title">增长之星</h3>
                </div>
                <div className="insight-list">
                    {growth_stars.length > 0 ? growth_stars.map((item, idx) => (
                        <div key={idx} className="insight-item">
                            <div className="insight-item-main">
                                <span className="insight-client-name">{item.client}</span>
                                <span className="insight-detail">增长潜力股</span>
                            </div>
                            <span className="insight-value positive">
                                +{formatCurrency(item.growth_amount)}
                            </span>
                        </div>
                    )) : <div className="empty-insight">暂无显著增长</div>}
                </div>
            </div>

            {/* 4. Client Segmentation */}
            <div className="insight-card segmentation">
                <div className="insight-header">
                    <div className="insight-icon">
                        <PieChart size={18} />
                    </div>
                    <h3 className="insight-title">客户分层</h3>
                </div>

                {/* Top Clients List (Whales) */}
                <div className="insight-list">
                    {segmentation.whales.top_clients && segmentation.whales.top_clients.length > 0 ? (
                        segmentation.whales.top_clients.map((client, idx) => (
                            <div key={idx} className="insight-item">
                                <div className="insight-item-main">
                                    <span className="insight-client-name">{client.client}</span>
                                    <span className="insight-detail">头部客户</span>
                                </div>
                                <span className="insight-value" style={{ color: 'var(--segment-whale)' }}>
                                    {formatCurrency(client.value)}
                                </span>
                            </div>
                        ))
                    ) : (
                        <div className="insight-item" style={{ justifyContent: 'center' }}>
                            <span className="insight-detail">暂无头部客户数据</span>
                        </div>
                    )}
                </div>

                <div className="seg-bar-container">
                    <div className="seg-bar">
                        <div className="seg-segment" style={{ width: `${segmentation.whales.pct}%`, background: 'var(--segment-whale)' }}></div>
                        <div className="seg-segment" style={{ width: `${segmentation.core.pct}%`, background: 'var(--segment-core)' }}></div>
                        <div className="seg-segment" style={{ width: `${segmentation.long_tail.pct}%`, background: 'var(--segment-longtail)' }}></div>
                    </div>
                    <div className="seg-legend">
                        <div className="legend-item">
                            <div className="legend-dot" style={{ background: 'var(--segment-whale)' }}></div>
                            <span>头部 ({segmentation.whales.count})</span>
                        </div>
                        <div className="legend-item">
                            <div className="legend-dot" style={{ background: 'var(--segment-core)' }}></div>
                            <span>腰部 ({segmentation.core.count})</span>
                        </div>
                        <div className="legend-item">
                            <div className="legend-dot" style={{ background: 'var(--segment-longtail)' }}></div>
                            <span>长尾 ({segmentation.long_tail.count})</span>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}
