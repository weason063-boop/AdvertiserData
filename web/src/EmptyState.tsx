import type { ReactNode } from 'react'
import { Inbox } from 'lucide-react'

interface EmptyStateProps {
    title?: string
    description?: string
    icon?: ReactNode
    children?: ReactNode
}

export function EmptyState({
    title = '暂无数据',
    description = 'No data available',
    icon = <Inbox size={48} strokeWidth={1.5} />,
    children
}: EmptyStateProps) {
    return (
        <div className="empty-state-container" style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '4rem 2rem',
            textAlign: 'center',
            color: 'var(--text-secondary)',
            background: 'var(--bg-surface)',
            borderRadius: '16px',
            border: '2px dashed var(--border-subtle)',
            height: '100%',
            minHeight: '300px'
        }}>
            <div className="empty-state-icon" style={{
                marginBottom: '1rem',
                color: 'var(--text-muted)',
                background: 'var(--bg-page)',
                padding: '1.5rem',
                borderRadius: '50%'
            }}>
                {icon}
            </div>
            <h3 style={{
                marginBottom: '0.5rem',
                fontWeight: 600,
                color: 'var(--text-main)',
                fontFamily: 'var(--font-display)'
            }}>
                {title}
            </h3>
            <p style={{
                fontSize: '0.9rem',
                maxWidth: '300px',
                margin: '0 auto',
                lineHeight: 1.5,
                color: 'var(--text-secondary)'
            }}>
                {description}
            </p>
            {children && <div style={{ marginTop: '1.5rem' }}>{children}</div>}
        </div>
    )
}
