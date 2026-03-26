import { useEffect } from 'react'
import './Toast.css'

export interface ToastProps {
    message: string
    type: 'info' | 'success' | 'error'
    onClose: () => void
    duration?: number
}

export function Toast({ message, type, onClose, duration = 3000 }: ToastProps) {
    useEffect(() => {
        const timer = setTimeout(() => {
            onClose()
        }, duration)

        return () => clearTimeout(timer)
    }, [duration, onClose])

    return (
        <div className={`toast toast-${type}`}>
            <div className="toast-content">
                <span className="toast-icon">
                    {type === 'success' && '✓'}
                    {type === 'error' && '✕'}
                    {type === 'info' && 'ℹ'}
                </span>
                <span className="toast-message">{message}</span>
            </div>
        </div>
    )
}
