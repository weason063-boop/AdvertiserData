import { startTransition, useDeferredValue, useEffect, useMemo, useRef, useState } from 'react'
import './App.css'
import {
  extractPermissionsFromToken,
  extractRoleFromToken,
  extractUsernameFromToken,
} from './authTokenUtils'
import type { CalculationResult, Client, SyncResult } from './billingTypes'
import { LoginModal } from './LoginModal'
import { MainContentShell } from './MainContentShell'
import { SidebarNav } from './SidebarNav'
import { SidebarSettingsMenu } from './SidebarSettingsMenu'
import { Toast } from './Toast'
import { UserManagerModal } from './UserManagerModal'
import { apiBlob, apiJson, isApiHttpError } from './apiClient'
import { useTaskHistory } from './useTaskHistory'
import {
  ALL_PERMISSIONS,
  type ManagedUser,
  normalizePermissions,
  PERMISSION_META,
  ROLE_LABELS,
  USER_MANAGER_PAGE_SIZE,
  type UserPermission,
} from './userManagement'

type Tab = 'dashboard' | 'clients' | 'results' | 'rates' | 'taskHistory'

const ACTIVE_TAB_STORAGE_KEY = 'billing_active_tab'

const isTab = (value: string | null): value is Tab =>
  value === 'dashboard' ||
  value === 'clients' ||
  value === 'results' ||
  value === 'rates' ||
  value === 'taskHistory'

const isAdminRole = (role: ManagedUser['role']): boolean => role === 'admin' || role === 'super_admin'

const getStoredActiveTab = (): Tab => {
  const stored = window.localStorage.getItem(ACTIVE_TAB_STORAGE_KEY)
  return isTab(stored) ? stored : 'dashboard'
}

function App() {
  const [activeTab, setActiveTab] = useState<Tab>(() => getStoredActiveTab())
  const [clients, setClients] = useState<Client[]>([])
  const [search, setSearch] = useState('')
  const [editingClient, setEditingClient] = useState<Client | null>(null)
  const [editClause, setEditClause] = useState('')
  const [isAddingClient, setIsAddingClient] = useState(false)
  const [newClientData, setNewClientData] = useState({ name: '', business_type: '', fee_clause: '' })
  const [loading, setLoading] = useState(false)

  const [results, setResults] = useState<CalculationResult | null>(null)
  const [resultFile, setResultFile] = useState('')
  const [, setResultDataUrl] = useState('')
  const [resultDownloadUrl, setResultDownloadUrl] = useState('')
  const [resultsPage, setResultsPage] = useState(1)
  const [resultsPageSize, setResultsPageSize] = useState(100)

  const [dashboardData, setDashboardData] = useState<{ stats: any; trend: any[]; top_clients?: any[] }>({
    stats: null,
    trend: [],
  })
  const [isDashboardStale, setIsDashboardStale] = useState(false)

  // Toast state
  const [toastMessage, setToastMessage] = useState('')
  const [toastType, setToastType] = useState<'info' | 'success' | 'error'>('info')

  const [syncResult, setSyncResult] = useState<SyncResult | null>(null)

  // Auth State
  const [isAuthenticated, setIsAuthenticated] = useState(() => !!localStorage.getItem('token'))
  const [showLoginModal, setShowLoginModal] = useState(() => !localStorage.getItem('token'))
  const [pendingTab, setPendingTab] = useState<Tab | null>(null)
  const [showSettingsMenu, setShowSettingsMenu] = useState(false)
  const [currentUser, setCurrentUser] = useState(() => {
    const token = localStorage.getItem('token')
    if (!token) return ''
    return localStorage.getItem('username') || extractUsernameFromToken(token)
  })
  const [currentRole, setCurrentRole] = useState<ManagedUser['role']>(() => {
    const token = localStorage.getItem('token')
    if (!token) return 'user'
    const storedRole = (localStorage.getItem('role') || '').toLowerCase()
    if (storedRole === 'super_admin' || storedRole === 'admin' || storedRole === 'user') {
      return storedRole
    }
    return extractRoleFromToken(token)
  })
  const [currentPermissions, setCurrentPermissions] = useState<UserPermission[]>(() => {
    const token = localStorage.getItem('token')
    if (!token) return []
    const stored = localStorage.getItem('permissions')
    if (stored) {
      try {
        return normalizePermissions(JSON.parse(stored))
      } catch {
        return extractPermissionsFromToken(token)
      }
    }
    return extractPermissionsFromToken(token)
  })
  const [showUserManager, setShowUserManager] = useState(false)
  const [managedUsers, setManagedUsers] = useState<ManagedUser[]>([])
  const [userOpLoading, setUserOpLoading] = useState(false)
  const [newAccount, setNewAccount] = useState({
    username: '',
    password: '',
    role: 'user' as ManagedUser['role'],
    permissions: [] as UserPermission[],
  })
  const [userSearchKeyword, setUserSearchKeyword] = useState('')
  const [userListPage, setUserListPage] = useState(1)
  const settingsMenuRef = useRef<HTMLDivElement | null>(null)
  const deferredResultsData = useDeferredValue(results?.data ?? [])
  const resultsTotalRows = deferredResultsData.length
  const resultsTotalPages = Math.max(1, Math.ceil(resultsTotalRows / resultsPageSize))
  const pagedResultsData = useMemo(() => {
    const start = (resultsPage - 1) * resultsPageSize
    return deferredResultsData.slice(start, start + resultsPageSize)
  }, [deferredResultsData, resultsPage, resultsPageSize])
  const filteredManagedUsers = useMemo(() => {
    const keyword = userSearchKeyword.trim().toLowerCase()
    if (!keyword) return managedUsers
    return managedUsers.filter((u) => {
      const roleLabel = ROLE_LABELS[u.role].toLowerCase()
      return u.username.toLowerCase().includes(keyword) || roleLabel.includes(keyword)
    })
  }, [managedUsers, userSearchKeyword])
  const userListTotalPages = Math.max(1, Math.ceil(filteredManagedUsers.length / USER_MANAGER_PAGE_SIZE))
  const pagedManagedUsers = useMemo(() => {
    const start = (userListPage - 1) * USER_MANAGER_PAGE_SIZE
    return filteredManagedUsers.slice(start, start + USER_MANAGER_PAGE_SIZE)
  }, [filteredManagedUsers, userListPage])

  const switchTab = (tab: Tab) => {
    if (!isAuthenticated) {
      setPendingTab(tab)
      setShowLoginModal(true)
    } else if (tab === 'taskHistory' && !isAdminRole(currentRole)) {
      setToastMessage('任务历史仅管理员可查看')
      setToastType('error')
    } else {
      setActiveTab(tab)
    }
  }

  const handleLoginSuccess = (token: string) => {
    const username = extractUsernameFromToken(token)
    const role = extractRoleFromToken(token)
    const permissions = extractPermissionsFromToken(token)
    localStorage.setItem('token', token)
    localStorage.setItem('username', username)
    localStorage.setItem('role', role)
    localStorage.setItem('permissions', JSON.stringify(permissions))
    setIsAuthenticated(true)
    setCurrentUser(username)
    setCurrentRole(role)
    setCurrentPermissions(permissions)
    setShowLoginModal(false)
    setShowSettingsMenu(false)
    setToastMessage('登录成功')
    setToastType('success')
    if (pendingTab) {
      if (pendingTab === 'taskHistory' && !isAdminRole(role)) {
        setActiveTab('dashboard')
        setToastMessage('任务历史仅管理员可查看')
        setToastType('error')
      } else {
        setActiveTab(pendingTab)
      }
      setPendingTab(null)
    }
  }

  const handleLogout = () => {
    localStorage.removeItem('token')
    localStorage.removeItem('username')
    localStorage.removeItem('role')
    localStorage.removeItem('permissions')
    setIsAuthenticated(false)
    setCurrentUser('')
    setCurrentRole('user')
    setCurrentPermissions([])
    setShowSettingsMenu(false)
    setShowUserManager(false)
    setManagedUsers([])
    setPendingTab(null)
    setShowLoginModal(true)
    setClients([])
    setResults(null)
    setResultFile('')
    setResultDataUrl('')
    setResultDownloadUrl('')
    taskHistory.reset()
    setDashboardData({ stats: null, trend: [] })
    setIsAddingClient(false)
    setEditingClient(null)
    setSearch('')
    setActiveTab('dashboard')
    window.localStorage.removeItem(ACTIVE_TAB_STORAGE_KEY)
    setToastMessage('已退出登录')
    setToastType('info')
  }

  const handleAction = (action: () => void) => {
    if (isAuthenticated) {
      action()
    } else {
      setShowLoginModal(true)
    }
  }

  const handleUnauthorized = () => {
    handleLogout()
    setShowLoginModal(true)
    setToastMessage('登录已过期，请重新登录')
    setToastType('error')
  }

  const getApiErrorMessage = (error: unknown, fallback: string): string => {
    if (isApiHttpError(error)) {
      return error.message || fallback
    }
    if (error instanceof Error && error.message) {
      return error.message
    }
    return fallback
  }

  const taskHistory = useTaskHistory({
    enabled: isAuthenticated && activeTab === 'taskHistory' && isAdminRole(currentRole),
    onUnauthorized: handleUnauthorized,
    onForbidden: () => {
      setActiveTab('dashboard')
      setToastMessage('任务历史仅管理员可查看')
      setToastType('error')
    },
    onNotify: (message, type) => {
      setToastMessage(message)
      setToastType(type)
    },
  })

  const loadClients = async () => {
    setLoading(true)
    try {
      const path = search
        ? `/api/clients?search=${encodeURIComponent(search)}`
        : '/api/clients'
      const { data } = await apiJson<{ clients?: Client[] }>(path)
      setClients(data.clients || [])
    } catch (error: unknown) {
      if (isApiHttpError(error) && error.status === 401) {
        handleUnauthorized()
        return
      }
      console.error('Failed to load clients:', error)
    } finally {
      setLoading(false)
    }
  }
  const loadDashboard = async () => {
    try {
      const { data } = await apiJson<{ stats: any; trend: any[] }>('/api/dashboard')
      setDashboardData(data)
    } catch (error: unknown) {
      if (isApiHttpError(error) && error.status === 401) {
        handleUnauthorized()
        return
      }
      console.error('Failed to load dashboard', error)
    }
  }
  const loadLatestResult = async () => {
    try {
      const { data } = await apiJson<{
        has_result?: boolean
        filename?: string
        output_file?: string
        data_url?: string
        download_url?: string
      }>('/api/latest-result')
      if (data.has_result) {
        const latestFilename = String(data.filename || data.output_file || '')
        const latestDataUrl = String(data.data_url || '')
        const latestDownloadUrl = String(data.download_url || '')
        setResultFile(latestFilename)
        setResultDataUrl(latestDataUrl)
        setResultDownloadUrl(latestDownloadUrl)
        if (!latestDataUrl) {
          throw new Error('结果地址缺失')
        }
        const { data: resultData } = await apiJson<CalculationResult>(latestDataUrl)
        setResults(resultData)
      } else {
        setResults(null)
        setResultFile('')
        setResultDataUrl('')
        setResultDownloadUrl('')
      }
    } catch (error: unknown) {
      if (isApiHttpError(error) && error.status === 401) {
        handleUnauthorized()
        return
      }
      if (isApiHttpError(error) && error.status === 403) {
        setResults(null)
        setResultFile('')
        setResultDataUrl('')
        setResultDownloadUrl('')
        return
      }
      console.error('Failed to load latest result', error)
    }
  }

  useEffect(() => {
    if (!isAuthenticated) {
      setShowLoginModal(true)
      return
    }
    setShowLoginModal(false)
    loadClients()
    loadDashboard()
    loadLatestResult()
  }, [isAuthenticated])

  useEffect(() => {
    window.localStorage.setItem(ACTIVE_TAB_STORAGE_KEY, activeTab)
  }, [activeTab])

  useEffect(() => {
    if (!isAuthenticated) return
    if (activeTab !== 'taskHistory') return
    if (isAdminRole(currentRole)) return
    setActiveTab(Boolean(results) ? 'results' : 'dashboard')
    setToastMessage('任务历史仅管理员可查看')
    setToastType('error')
  }, [activeTab, currentRole, isAuthenticated, results])

  // Delayed Dashboard refresh: only when switching to dashboard tab
  useEffect(() => {
    if (isAuthenticated && activeTab === 'dashboard' && isDashboardStale) {
      loadDashboard()
      setIsDashboardStale(false)
    }
  }, [activeTab, isDashboardStale, isAuthenticated])

  // Auto-hide sync result after 5 seconds
  useEffect(() => {
    if (syncResult) {
      const timer = setTimeout(() => {
        setSyncResult(null)
      }, 5000)
      return () => clearTimeout(timer)
    }
  }, [syncResult])

  useEffect(() => {
    const onMouseDown = (event: MouseEvent) => {
      if (!settingsMenuRef.current) return
      if (!settingsMenuRef.current.contains(event.target as Node)) {
        setShowSettingsMenu(false)
      }
    }

    document.addEventListener('mousedown', onMouseDown)
    return () => document.removeEventListener('mousedown', onMouseDown)
  }, [])

  useEffect(() => {
    if (!showUserManager) return

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setShowUserManager(false)
      }
    }

    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [showUserManager])

  useEffect(() => {
    if (resultsPage > resultsTotalPages) {
      setResultsPage(resultsTotalPages)
    }
  }, [resultsPage, resultsTotalPages])

  useEffect(() => {
    if (userListPage > userListTotalPages) {
      setUserListPage(userListTotalPages)
    }
  }, [userListPage, userListTotalPages])

  const openEdit = (client: Client) => {
    setEditingClient(client)
    setEditClause(client.fee_clause || '')
  }

  const closeEdit = () => {
    setEditingClient(null)
    setEditClause('')
  }

  const saveClause = async () => {
    if (!(currentRole === 'admin' || currentRole === 'super_admin' || currentPermissions.includes('client_write'))) {
      setToastMessage('当前账号没有 client_write 权限')
      setToastType('error')
      return
    }
    if (!editingClient) return
    setLoading(true)
    try {
      await apiJson(`/api/clients/${editingClient.id}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ fee_clause: editClause }),
      })
      loadClients()
      closeEdit()
      setToastMessage('条款更新成功')
      setToastType('success')
    } catch (error: unknown) {
      if (isApiHttpError(error) && error.status === 401) {
        handleUnauthorized()
        return
      }
      setToastMessage(`更新失败: ${getApiErrorMessage(error, '未知错误')}`)
      setToastType('error')
    }
    setLoading(false)
  }
  const saveNewClient = async () => {
    if (!(currentRole === 'admin' || currentRole === 'super_admin' || currentPermissions.includes('client_write'))) {
      setToastMessage('当前账号没有 client_write 权限')
      setToastType('error')
      return
    }
    if (!newClientData.name) {
      setToastMessage('客户名称不能为空')
      setToastType('info')
      return
    }
    setLoading(true)
    try {
      await apiJson('/api/clients', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(newClientData),
      })
      loadClients()
      setIsAddingClient(false)
      setNewClientData({ name: '', business_type: '', fee_clause: '' })
      setToastMessage('客户添加成功')
      setToastType('success')
    } catch (error: unknown) {
      if (isApiHttpError(error) && error.status === 401) {
        handleUnauthorized()
        return
      }
      setToastMessage(`添加失败: ${getApiErrorMessage(error, '未知错误')}`)
      setToastType('error')
    }
    setLoading(false)
  }



  const handleCalculate = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!(currentRole === 'admin' || currentRole === 'super_admin' || currentPermissions.includes('billing_run'))) {
      setToastMessage('当前账号没有 billing_run 权限')
      setToastType('error')
      e.target.value = ''
      return
    }
    const file = e.target.files?.[0]
    if (!file) return

    setLoading(true)
    const formData = new FormData()
    formData.append('file', file)

    try {
      setToastMessage('正在上传并计算...')
      setToastType('info')

      const { data: result } = await apiJson<{
        output_file?: string
        filename?: string
        data_url?: string
        download_url?: string
      }>('/api/calculate', {
        method: 'POST',
        body: formData,
      })

      if (result.data_url) {
        const nextFile = String(result.output_file || result.filename || '')
        const nextDataUrl = String(result.data_url || '')
        const nextDownloadUrl = String(result.download_url || '')
        setResultFile(nextFile)
        setResultDataUrl(nextDataUrl)
        setResultDownloadUrl(nextDownloadUrl)
        setResultsPage(1)

        const { data: resultData } = await apiJson<CalculationResult>(nextDataUrl)
        setResults(resultData)
        startTransition(() => {
          setActiveTab('results')
        })

        setIsDashboardStale(true)
        setToastMessage('计算完成')
        setToastType('success')
      } else {
        setToastMessage('计算失败: 后端未返回结果地址')
        setToastType('error')
      }
    } catch (error: unknown) {
      if (isApiHttpError(error) && error.status === 401) {
        handleUnauthorized()
        return
      }
      setToastMessage(`计算失败: ${getApiErrorMessage(error, '未知错误')}`)
      setToastType('error')
    } finally {
      setLoading(false)
      e.target.value = ''
    }
  }

  const handleSyncFeishu = async () => {
    if (!(currentRole === 'admin' || currentRole === 'super_admin' || currentPermissions.includes('feishu_sync'))) {
      setToastMessage('当前账号没有 feishu_sync 权限')
      setToastType('error')
      return
    }
    setLoading(true)
    try {
      setToastMessage('正在同步飞书数据...')
      setToastType('info')

      const { data: result } = await apiJson<{ status?: string; count?: number; message?: string; detail?: string }>(
        '/api/clients/sync-feishu',
        {
        method: 'POST',
        },
      )

      if (result.status === 'ok') {
        setToastMessage(`✅ ${result.message || '同步成功'}`)
        setToastType('success')
        setSyncResult({
          count: Number(result.count || 0),
          message: String(result.message || '同步成功'),
          time: new Date().toLocaleTimeString()
        })
        loadClients()
      } else {
        setToastMessage(`同步失败: ${result.detail || result.message || '未知错误'}`)
        setToastType('error')
      }
    } catch (error: unknown) {
      if (isApiHttpError(error) && error.status === 401) {
        handleUnauthorized()
        return
      }
      setToastMessage(`同步失败: ${getApiErrorMessage(error, '未知错误')}`)
      setToastType('error')
    } finally {
      setLoading(false)
    }
  }

  const handleUploadContract = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!(currentRole === 'admin' || currentRole === 'super_admin' || currentPermissions.includes('client_write'))) {
      setToastMessage('当前账号没有 client_write 权限')
      setToastType('error')
      e.target.value = ''
      return
    }
    const file = e.target.files?.[0]
    if (!file) return

    setLoading(true)

    const formData = new FormData()
    formData.append('file', file)

    try {
      await apiJson('/api/upload-contract', {
        method: 'POST',
        body: formData,
      })
      loadClients()
      setToastMessage('合同上传成功')
      setToastType('success')
    } catch (error: unknown) {
      if (isApiHttpError(error) && error.status === 401) {
        handleUnauthorized()
        return
      }
      setToastMessage(`合同上传失败: ${getApiErrorMessage(error, '未知错误')}`)
      setToastType('error')
    }
    setLoading(false)
    e.target.value = ''
  }

  const loadManagedUsers = async (): Promise<boolean> => {
    try {
      const { data } = await apiJson<{ users?: ManagedUser[] }>('/api/users')
      const users = data.users || []
      setManagedUsers(users)
      const me = users.find((u: ManagedUser) => u.username === currentUser)
      if (me?.role) {
        setCurrentRole(me.role)
        localStorage.setItem('role', me.role)
        const mePermissions = normalizePermissions(me.permissions || [])
        setCurrentPermissions(mePermissions)
        localStorage.setItem('permissions', JSON.stringify(mePermissions))
      }
      return true
    } catch (error: unknown) {
      if (isApiHttpError(error) && error.status === 401) {
        handleUnauthorized()
        return false
      }
      setToastMessage(`加载账号失败: ${getApiErrorMessage(error, '未知错误')}`)
      setToastType('error')
      return false
    }
  }

  const handleRecalculate = async () => {
    if (!(currentRole === 'admin' || currentRole === 'super_admin' || currentPermissions.includes('billing_run'))) {
      setToastMessage('当前账号没有 billing_run 权限')
      setToastType('error')
      return
    }
    setLoading(true)
    try {
      setToastMessage('正在基于最近上传文件重新计算...')
      setToastType('info')

      const { data: result } = await apiJson<{
        output_file?: string
        filename?: string
        data_url?: string
        download_url?: string
      }>('/api/recalculate', {
        method: 'POST',
      })
      if (result.data_url) {
        const nextFile = String(result.output_file || result.filename || '')
        const nextDataUrl = String(result.data_url || '')
        const nextDownloadUrl = String(result.download_url || '')
        setResultFile(nextFile)
        setResultDataUrl(nextDataUrl)
        setResultDownloadUrl(nextDownloadUrl)
        setResultsPage(1)

        const { data: resultData } = await apiJson<CalculationResult>(nextDataUrl)
        setResults(resultData)
        startTransition(() => {
          setActiveTab('results')
        })

        setIsDashboardStale(true)
        setToastMessage('已重新计算完成')
        setToastType('success')
      } else {
        setToastMessage('重新计算失败: 后端未返回结果地址')
        setToastType('error')
      }
    } catch (error: unknown) {
      if (isApiHttpError(error) && error.status === 401) {
        handleUnauthorized()
        return
      }
      setToastMessage(`重新计算失败: ${getApiErrorMessage(error, '未知错误')}`)
      setToastType('error')
    } finally {
      setLoading(false)
    }
  }
  const openUserManager = async () => {
    setShowSettingsMenu(false)
    setUserSearchKeyword('')
    setUserListPage(1)
    setShowUserManager(true)
    const ok = await loadManagedUsers()
    if (!ok) {
      setShowUserManager(false)
    }
  }

  const handleCreateAccount = async () => {
    if (!newAccount.username.trim() || !newAccount.password.trim()) {
      setToastMessage('请填写账号和密码')
      setToastType('info')
      return
    }
    setUserOpLoading(true)
    try {
      await apiJson('/api/users', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          username: newAccount.username.trim(),
          password: newAccount.password,
          role: newAccount.role,
          permissions: newAccount.permissions,
        }),
      })
      setToastMessage('账号创建成功')
      setToastType('success')
      setNewAccount({ username: '', password: '', role: 'user', permissions: [] })
      await loadManagedUsers()
    } catch (error: unknown) {
      if (isApiHttpError(error) && error.status === 401) {
        handleUnauthorized()
        return
      }
      setToastMessage(`创建失败: ${getApiErrorMessage(error, '未知错误')}`)
      setToastType('error')
    } finally {
      setUserOpLoading(false)
    }
  }

  const handleDeleteAccount = async (user: ManagedUser) => {
    if (!window.confirm(`确认删除账号 ${user.username} 吗？`)) return
    setUserOpLoading(true)
    try {
      await apiJson(`/api/users/${user.id}`, {
        method: 'DELETE',
      })
      setToastMessage('账号删除成功')
      setToastType('success')
      await loadManagedUsers()
    } catch (error: unknown) {
      if (isApiHttpError(error) && error.status === 401) {
        handleUnauthorized()
        return
      }
      setToastMessage(`删除失败: ${getApiErrorMessage(error, '未知错误')}`)
      setToastType('error')
    } finally {
      setUserOpLoading(false)
    }
  }

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') loadClients()
  }

  const formatNumber = (val: string | number) => {
    if (val === '' || val === null || val === undefined) return '—'
    const num = Number(val)
    if (isNaN(num)) return String(val)
    return num.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  }

  const downloadResult = async () => {
    if (!resultDownloadUrl && !resultFile) return
    try {
      const downloadPath = resultDownloadUrl || `/api/download/${encodeURIComponent(resultFile)}`
      const { blob } = await apiBlob(downloadPath)
      const url = window.URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = resultFile || 'billing_result.xlsx'
      document.body.appendChild(anchor)
      anchor.click()
      anchor.remove()
      window.URL.revokeObjectURL(url)
    } catch (error: unknown) {
      if (isApiHttpError(error) && error.status === 401) {
        handleUnauthorized()
        return
      }
      setToastMessage(`下载失败: ${getApiErrorMessage(error, '未知错误')}`)
      setToastType('error')
    }
  }

  const hasPermission = (permission: UserPermission): boolean => {
    if (currentRole === 'admin' || currentRole === 'super_admin') return true
    return currentPermissions.includes(permission)
  }
  const canClientWrite = hasPermission('client_write')
  const canFeishuSync = hasPermission('feishu_sync')
  const canBillingRun = hasPermission('billing_run')
  const canViewTaskHistory = isAdminRole(currentRole)
  const canManageAccounts = currentRole === 'super_admin'
  const userDisplay = currentUser || 'admin'
  const workspaceDisplay = '账单工作空间'

  return (
    <div className="app">
      {/* Left Sidebar */}
      <aside className="sidebar">
        <div className="sidebar-header">
          <h1>广告客户数据</h1>
        </div>

        <SidebarNav
          activeTab={activeTab}
          onSwitchTab={switchTab}
          canViewTaskHistory={canViewTaskHistory}
        />
        <SidebarSettingsMenu
          containerRef={settingsMenuRef}
          showSettingsMenu={showSettingsMenu}
          onToggle={() => setShowSettingsMenu(v => !v)}
          userDisplay={userDisplay}
          workspaceDisplay={workspaceDisplay}
          canManageAccounts={canManageAccounts}
          currentRoleLabel={ROLE_LABELS[currentRole]}
          isAuthenticated={isAuthenticated}
          onOpenUserManager={openUserManager}
          onLogout={handleLogout}
        />
      </aside>

      <MainContentShell
        activeTab={activeTab}
        isAuthenticated={isAuthenticated}
        search={search}
        onSearchChange={setSearch}
        onSearchKeyPress={handleKeyPress}
        canClientWrite={canClientWrite}
        canFeishuSync={canFeishuSync}
        canBillingRun={canBillingRun}
        loading={loading}
        isAddingClient={isAddingClient}
        hasResults={Boolean(results)}
        onOpenLogin={() => setShowLoginModal(true)}
        onAddClient={() => handleAction(() => setIsAddingClient(true))}
        onSyncFeishu={() => handleAction(handleSyncFeishu)}
        onUploadContract={(e) => handleAction(() => handleUploadContract(e))}
        onUploadConsumption={(e) => handleAction(() => handleCalculate(e))}
        onRecalculate={() => handleAction(handleRecalculate)}
        onDownloadResult={downloadResult}
        dashboardData={dashboardData}
        onNotify={(message, type) => {
          setToastMessage(message)
          setToastType(type)
        }}
        onRequireAuth={() => {
          handleLogout()
          setShowLoginModal(true)
        }}
        syncResult={syncResult}
        clients={clients}
        editingClient={editingClient}
        editClause={editClause}
        newClientData={newClientData}
        onNewClientDataChange={(patch) => setNewClientData((v) => ({ ...v, ...patch }))}
        onSaveNewClient={saveNewClient}
        onCancelAddClient={() => setIsAddingClient(false)}
        onEditClauseChange={setEditClause}
        onSaveClause={() => handleAction(saveClause)}
        onCloseEdit={closeEdit}
        onOpenEdit={(client) => handleAction(() => openEdit(client))}
        results={results}
        pagedResultsData={pagedResultsData}
        resultsTotalRows={resultsTotalRows}
        resultsPage={resultsPage}
        resultsTotalPages={resultsTotalPages}
        resultsPageSize={resultsPageSize}
        onResultsPageSizeChange={(size) => {
          setResultsPageSize(size)
          setResultsPage(1)
        }}
        onPrevResultsPage={() => setResultsPage((p) => Math.max(1, p - 1))}
        onNextResultsPage={() => setResultsPage((p) => Math.min(resultsTotalPages, p + 1))}
        formatNumber={formatNumber}
        taskHistoryItems={taskHistory.items}
        taskHistoryLoading={taskHistory.loading}
        taskHistoryLimit={taskHistory.limit}
        taskHistoryActorFilter={taskHistory.actorFilter}
        taskHistoryActionFilter={taskHistory.actionFilter}
        taskHistoryStatusFilter={taskHistory.statusFilter}
        taskHistoryDaysFilter={taskHistory.daysFilter}
        onTaskHistoryLimitChange={taskHistory.setLimit}
        onTaskHistoryActorFilterChange={taskHistory.setActorFilter}
        onTaskHistoryActionFilterChange={taskHistory.setActionFilter}
        onTaskHistoryStatusFilterChange={taskHistory.setStatusFilter}
        onTaskHistoryDaysFilterChange={taskHistory.setDaysFilter}
        onToggleTaskHistoryFailedOnly={taskHistory.toggleFailedOnly}
        onRefreshTaskHistory={() => taskHistory.loadTaskHistory()}
        onExportTaskHistory={taskHistory.exportTaskHistory}
      />

      <UserManagerModal
        visible={showUserManager}
        canManageAccounts={canManageAccounts}
        currentRole={currentRole}
        roleLabels={ROLE_LABELS}
        allPermissions={ALL_PERMISSIONS}
        permissionMeta={PERMISSION_META}
        newAccount={newAccount}
        setNewAccount={setNewAccount}
        userOpLoading={userOpLoading}
        onClose={() => setShowUserManager(false)}
        onCreateAccount={handleCreateAccount}
        managedUsers={managedUsers}
        filteredManagedUsers={filteredManagedUsers}
        pagedManagedUsers={pagedManagedUsers}
        userSearchKeyword={userSearchKeyword}
        setUserSearchKeyword={setUserSearchKeyword}
        userListPage={userListPage}
        setUserListPage={setUserListPage}
        userListTotalPages={userListTotalPages}
        onDeleteAccount={handleDeleteAccount}
        normalizePermissions={normalizePermissions}
      />

      {/* Global Toast notification */}
      {toastMessage && (
        <Toast
          message={toastMessage}
          type={toastType}
          onClose={() => setToastMessage('')}
        />
      )}

      {showLoginModal && (
        <LoginModal
          onClose={() => {
            if (isAuthenticated) setShowLoginModal(false)
          }}
          onLoginSuccess={handleLoginSuccess}
          closable={isAuthenticated}
        />
      )}
    </div>
  )
}

export default App





