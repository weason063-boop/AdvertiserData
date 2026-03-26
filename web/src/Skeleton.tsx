import './Skeleton.css'

interface SkeletonProps {
    variant?: 'text' | 'rect' | 'circle'
    width?: string | number
    height?: string | number
    className?: string
    style?: React.CSSProperties
}

export function Skeleton({ variant = 'text', width, height, className = '', style = {} }: SkeletonProps) {
    const styles = {
        width,
        height,
        ...style
    }
    return <div className={`skeleton ${variant} ${className}`} style={styles} />
}
