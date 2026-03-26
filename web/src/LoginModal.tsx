import { useState } from 'react'
import { X, Lock, User } from 'lucide-react'
import './LoginModal.css'
import { apiJson, isApiHttpError } from './apiClient'

interface LoginModalProps {
    onClose: () => void
    onLoginSuccess: (token: string) => void
    closable?: boolean
}

export function LoginModal({ onClose, onLoginSuccess, closable = true }: LoginModalProps) {
    const [username, setUsername] = useState('')
    const [password, setPassword] = useState('')
    const [error, setError] = useState('')
    const [loading, setLoading] = useState(false)

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault()
        setError('')

        const trimmedUsername = username.trim()
        if (!trimmedUsername) {
            setError('请输入账号后再登录')
            return
        }
        if (!password.trim()) {
            setError('请输入密码后再登录')
            return
        }

        setLoading(true)

        const formData = new FormData()
        formData.append('username', trimmedUsername)
        formData.append('password', password)

        try {
            const { data } = await apiJson<{ access_token: string }>(
                '/api/token',
                {
                    method: 'POST',
                    body: formData,
                },
                { auth: false },
            )
            onLoginSuccess(data.access_token)
        } catch (err) {
            if (isApiHttpError(err)) {
                setError(err.message || '登录失败，请检查账号密码')
            } else {
                setError('网络错误，请稍后重试')
            }
        }
        setLoading(false)
    }

    return (
        <div className="modal-overlay">
            <div className="login-modal">
                {closable && (
                    <button className="close-btn" onClick={onClose}>
                        <X size={20} />
                    </button>
                )}

                <div className="login-header">
                    <div className="login-icon">
                        <Lock size={24} />
                    </div>
                    <h2>用户登录</h2>
                    <p>请输入账号和密码以继续使用</p>
                </div>

                <form onSubmit={handleSubmit} noValidate>
                    <div className="form-group">
                        <label>账号</label>
                        <div className="input-with-icon">
                            <User size={18} />
                            <input
                                type="text"
                                value={username}
                                onChange={e => {
                                    setUsername(e.target.value)
                                    if (error) setError('')
                                }}
                                placeholder="请输入用户名"
                            />
                        </div>
                    </div>

                    <div className="form-group">
                        <label>密码</label>
                        <div className="input-with-icon">
                            <Lock size={18} />
                            <input
                                type="password"
                                value={password}
                                onChange={e => {
                                    setPassword(e.target.value)
                                    if (error) setError('')
                                }}
                                placeholder="请输入密码"
                            />
                        </div>
                    </div>

                    {error && <div className="error-message">{error}</div>}

                    <button type="submit" className="login-btn" disabled={loading}>
                        {loading ? '登录中...' : '登录'}
                    </button>
                </form>
            </div>
        </div>
    )
}
