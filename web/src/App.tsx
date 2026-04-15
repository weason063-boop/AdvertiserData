import { startTransition, useDeferredValue, useEffect, useMemo, useRef, useState } from 'react'
import './App.css'
import {
  extractPermissionsFromToken,
  extractRoleFromToken,
  extractUsernameFromToken,
} from './authTokenUtils'
import type { CalculationResult, Client, ContractChangeReview, SyncResult } from './billingTypes'
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

type Tab =
  | 'dashboard'
  | 'clientLedger'
  | 'clientDetail'
  | 'clients'
  | 'results'
  | 'estimateResults'
  | 'rates'
  | 'taskHistory'

const ACTIVE_TAB_STORAGE_KEY = 'billing_active_tab'

const isTab = (value: string | null): value is Tab =>
  value === 'dashboard' ||
  value === 'clientLedger' ||
  value === 'clientDetail' ||
  value === 'clients' ||
  value === 'results' ||
  value === 'estimateResults' ||
  value === 'rates' ||
  value === 'taskHistory'

const isAdminRole = (role: ManagedUser['role']): boolean => role === 'admin' || role === 'super_admin'

const getStoredActiveTab = (): Tab => {
  const stored = window.localStorage.getItem(ACTIVE_TAB_STORAGE_KEY)
  return isTab(stored) ? stored : 'dashboard'
}

const normalizeSearchText = (value: unknown): string =>
  String(value ?? '')
    .toLowerCase()
    .replace(/\s+/g, '')

const matchesClientSearch = (client: Client, keyword: string): boolean => {
  const token = normalizeSearchText(keyword)
  if (!token) return true
  return [
    client.name,
    client.fee_clause,
    client.entity,
    client.business_type,
  ].some((field) => normalizeSearchText(field).includes(token))
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
  const [estimateResults, setEstimateResults] = useState<CalculationResult | null>(null)
  const [estimateResultFile, setEstimateResultFile] = useState('')
  const [, setEstimateResultDataUrl] = useState('')
  const [estimateResultDownloadUrl, setEstimateResultDownloadUrl] = useState('')
  const [estimateResultsPage, setEstimateResultsPage] = useState(1)
  const [estimateResultsPageSize, setEstimateResultsPageSize] = useState(100)

  const [dashboardData, setDashboardData] = useState<{ stats: any; trend: any[]; top_clients?: any[] }>({
    stats: null,
    trend: [],
  })
  const [isDashboardStale, setIsDashboardStale] = useState(false)
  const [selectedClientName, setSelectedClientName] = useState<string | null>(null)

  // Toast state
  const [toastMessage, setToastMessage] = useState('')
  const [toastType, setToastType] = useState<'info' | 'success' | 'error'>('info')

  const [syncResult, setSyncResult] = useState<SyncResult | null>(null)
  const [contractChangeReviews, setContractChangeReviews] = useState<ContractChangeReview[]>([])

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
  const deferredEstimateResultsData = useDeferredValue(estimateResults?.data ?? [])
  const estimateResultsTotalRows = deferredEstimateResultsData.length
  const estimateResultsTotalPages = Math.max(1, Math.ceil(estimateResultsTotalRows / estimateResultsPageSize))
  const pagedEstimateResultsData = useMemo(() => {
    const start = (estimateResultsPage - 1) * estimateResultsPageSize
    return deferredEstimateResultsData.slice(start, start + estimateResultsPageSize)
  }, [deferredEstimateResultsData, estimateResultsPage, estimateResultsPageSize])
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
    setContractChangeReviews([])
    setSyncResult(null)
    setResults(null)
    setResultFile('')
    setResultDataUrl('')
    setResultDownloadUrl('')
    setEstimateResults(null)
    setEstimateResultFile('')
    setEstimateResultDataUrl('')
    setEstimateResultDownloadUrl('')
    taskHistory.reset()
    setDashboardData({ stats: null, trend: [] })
    setIsDashboardStale(false)
    setIsAddingClient(false)
    setEditingClient(null)
    setSelectedClientName(null)
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

  const loadClients = async (keyword: string = search) => {
    setLoading(true)
    try {
      const normalizedKeyword = keyword.trim()
      if (!normalizedKeyword) {
        const { data } = await apiJson<{ clients?: Client[] }>('/api/clients')
        setClients(data.clients || [])
        return
      }

      const { data } = await apiJson<{ clients?: Client[] }>(
        `/api/clients?search=${encodeURIComponent(normalizedKeyword)}`,
      )
      let nextClients = data.clients || []

      // Backward-compatible fallback: if backend search is stale, filter locally.
      if (nextClients.length === 0) {
        const { data: allData } = await apiJson<{ clients?: Client[] }>('/api/clients')
        nextClients = (allData.clients || []).filter((item) => matchesClientSearch(item, normalizedKeyword))
      }

      setClients(nextClients)
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

  const loadContractChangeReviews = async (keyword: string = search) => {
    try {
      const normalizedKeyword = keyword.trim()
      const query = normalizedKeyword ? `?search=${encodeURIComponent(normalizedKeyword)}` : ''
      const { data } = await apiJson<{ reviews?: ContractChangeReview[] }>(
        `/api/clients/contract-change-reviews${query}`,
      )
      setContractChangeReviews(data.reviews || [])
    } catch (error: unknown) {
      if (isApiHttpError(error) && error.status === 401) {
        handleUnauthorized()
        return
      }
      console.error('Failed to load contract change reviews:', error)
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
  const loadLatestEstimateResult = async () => {
    try {
      const { data } = await apiJson<{
        has_result?: boolean
        filename?: string
        output_file?: string
        data_url?: string
        download_url?: string
      }>('/api/estimate/latest-result')
      if (data.has_result) {
        const latestFilename = String(data.filename || data.output_file || '')
        const latestDataUrl = String(data.data_url || '')
        const latestDownloadUrl = String(data.download_url || '')
        setEstimateResultFile(latestFilename)
        setEstimateResultDataUrl(latestDataUrl)
        setEstimateResultDownloadUrl(latestDownloadUrl)
        if (!latestDataUrl) {
          throw new Error('预估结果地址缺失')
        }
        const { data: resultData } = await apiJson<CalculationResult>(latestDataUrl)
        setEstimateResults(resultData)
        setEstimateResultsPage(1)
      } else {
        setEstimateResults(null)
        setEstimateResultFile('')
        setEstimateResultDataUrl('')
        setEstimateResultDownloadUrl('')
      }
    } catch (error: unknown) {
      if (isApiHttpError(error) && error.status === 401) {
        handleUnauthorized()
        return
      }
      if (isApiHttpError(error) && error.status === 403) {
        setEstimateResults(null)
        setEstimateResultFile('')
        setEstimateResultDataUrl('')
        setEstimateResultDownloadUrl('')
        return
      }
      console.error('Failed to load latest estimate result', error)
    }
  }

  useEffect(() => {
    if (!isAuthenticated) {
      setShowLoginModal(true)
      return
    }
    setShowLoginModal(false)
    loadClients()
    loadContractChangeReviews()
    loadDashboard()
    loadLatestResult()
    loadLatestEstimateResult()
  }, [isAuthenticated])

  useEffect(() => {
    if (!isAuthenticated || activeTab !== 'clients') return
    const timer = window.setTimeout(() => {
      void loadClients(search)
      void loadContractChangeReviews(search)
    }, 250)
    return () => window.clearTimeout(timer)
  }, [search, activeTab, isAuthenticated])

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

  useEffect(() => {
    if (isAuthenticated && activeTab === 'dashboard' && isDashboardStale) {
      loadDashboard()
      setIsDashboardStale(false)
    }
  }, [activeTab, isDashboardStale, isAuthenticated])

  useEffect(() => {
    if (activeTab === 'clientDetail' && !selectedClientName) {
      setActiveTab('clientLedger')
    }
  }, [activeTab, selectedClientName])

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
    if (estimateResultsPage > estimateResultsTotalPages) {
      setEstimateResultsPage(estimateResultsTotalPages)
    }
  }, [estimateResultsPage, estimateResultsTotalPages])

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

  const handleEstimateCalculate = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!(currentRole === 'admin' || currentRole === 'super_admin' || currentPermissions.includes('billing_run'))) {
      setToastMessage('\u5f53\u524d\u8d26\u53f7\u6ca1\u6709 billing_run \u6743\u9650')
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
      setToastMessage('\u6b63\u5728\u4e0a\u4f20\u5e76\u8ba1\u7b97\u9884\u4f30...')
      setToastType('info')

      const { data: result } = await apiJson<{
        output_file?: string
        filename?: string
        data_url?: string
        download_url?: string
      }>('/api/estimate/calculate', {
        method: 'POST',
        body: formData,
      })

      if (result.data_url) {
        const nextFile = String(result.output_file || result.filename || '')
        const nextDataUrl = String(result.data_url || '')
        const nextDownloadUrl = String(result.download_url || '')
        setEstimateResultFile(nextFile)
        setEstimateResultDataUrl(nextDataUrl)
        setEstimateResultDownloadUrl(nextDownloadUrl)
        setEstimateResultsPage(1)

        const { data: resultData } = await apiJson<CalculationResult>(nextDataUrl)
        setEstimateResults(resultData)
        startTransition(() => {
          setActiveTab('estimateResults')
        })

        setToastMessage('\u9884\u4f30\u8ba1\u7b97\u5b8c\u6210')
        setToastType('success')
      } else {
        setToastMessage('\u9884\u4f30\u8ba1\u7b97\u5931\u8d25: \u540e\u7aef\u672a\u8fd4\u56de\u7ed3\u679c\u5730\u5740')
        setToastType('error')
      }
    } catch (error: unknown) {
      if (isApiHttpError(error) && error.status === 401) {
        handleUnauthorized()
        return
      }
      setToastMessage(`\u9884\u4f30\u8ba1\u7b97\u5931\u8d25: ${getApiErrorMessage(error, '\u672a\u77e5\u9519\u8bef')}`)
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

      const { data: result } = await apiJson<{
        status?: string
        count?: number
        message?: string
        detail?: string
        line_count?: number
        client_count?: number
        new_client_count?: number
        unchanged_count?: number
        pending_count?: number
        new_clients?: string[]
      }>(
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
          time: new Date().toLocaleTimeString(),
          line_count: Number(result.line_count || 0),
          client_count: Number(result.client_count || result.count || 0),
          new_client_count: Number(result.new_client_count || 0),
          unchanged_count: Number(result.unchanged_count || 0),
          pending_count: Number(result.pending_count || 0),
          new_clients: Array.isArray(result.new_clients) ? result.new_clients.map(String) : [],
        })
        await loadClients()
        await loadContractChangeReviews()
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

  const handleApproveContractChangeReview = async (reviewId: number, overrideNewFeeClause?: string) => {
    if (!(currentRole === 'admin' || currentRole === 'super_admin' || currentPermissions.includes('client_write'))) {
      setToastMessage('当前账号没有 client_write 权限')
      setToastType('error')
      return
    }

    setLoading(true)
    try {
      const payload =
        overrideNewFeeClause !== undefined
          ? JSON.stringify({ override_new_fee_clause: overrideNewFeeClause })
          : undefined
      await apiJson(`/api/clients/contract-change-reviews/${reviewId}/approve`, {
        method: 'POST',
        headers: payload
          ? {
              'Content-Type': 'application/json',
            }
          : undefined,
        body: payload,
      })
      await loadClients(search)
      await loadContractChangeReviews(search)
      setToastMessage('已确认并应用条款变更')
      setToastType('success')
    } catch (error: unknown) {
      if (isApiHttpError(error) && error.status === 401) {
        handleUnauthorized()
        return
      }
      setToastMessage(`确认失败: ${getApiErrorMessage(error, '未知错误')}`)
      setToastType('error')
    } finally {
      setLoading(false)
    }
  }

  const handleIgnoreContractChangeReview = async (reviewId: number) => {
    if (!(currentRole === 'admin' || currentRole === 'super_admin' || currentPermissions.includes('client_write'))) {
      setToastMessage('当前账号没有 client_write 权限')
      setToastType('error')
      return
    }

    setLoading(true)
    try {
      await apiJson(`/api/clients/contract-change-reviews/${reviewId}/ignore`, {
        method: 'POST',
      })
      await loadContractChangeReviews(search)
      setToastMessage('已忽略本次条款变更')
      setToastType('success')
    } catch (error: unknown) {
      if (isApiHttpError(error) && error.status === 401) {
        handleUnauthorized()
        return
      }
      setToastMessage(`忽略失败: ${getApiErrorMessage(error, '未知错误')}`)
      setToastType('error')
    } finally {
      setLoading(false)
    }
  }

  const handleBatchApproveContractChangeReviews = async (
    reviewIds: number[],
    overrideNewFeeClauseByReviewId?: Record<number, string>,
  ) => {
    if (!(currentRole === 'admin' || currentRole === 'super_admin' || currentPermissions.includes('client_write'))) {
      setToastMessage('当前账号没有 client_write 权限')
      setToastType('error')
      return
    }
    if (reviewIds.length === 0) {
      setToastMessage('请先选择待确认记录')
      setToastType('info')
      return
    }

    setLoading(true)
    try {
      const { data } = await apiJson<{ approved_count?: number }>(
        '/api/clients/contract-change-reviews/batch-approve',
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            review_ids: reviewIds,
            override_new_fee_clause_by_review_id: overrideNewFeeClauseByReviewId,
          }),
        },
      )
      await loadClients(search)
      await loadContractChangeReviews(search)
      setToastMessage(`已批量确认 ${Number(data.approved_count || 0)} 条变更`)
      setToastType('success')
    } catch (error: unknown) {
      if (isApiHttpError(error) && error.status === 401) {
        handleUnauthorized()
        return
      }
      setToastMessage(`批量确认失败: ${getApiErrorMessage(error, '未知错误')}`)
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

  const handleEstimateRecalculate = async () => {
    if (!(currentRole === 'admin' || currentRole === 'super_admin' || currentPermissions.includes('billing_run'))) {
      setToastMessage('\u5f53\u524d\u8d26\u53f7\u6ca1\u6709 billing_run \u6743\u9650')
      setToastType('error')
      return
    }
    setLoading(true)
    try {
      setToastMessage('\u6b63\u5728\u57fa\u4e8e\u6700\u8fd1\u4e0a\u4f20\u6a21\u677f\u91cd\u65b0\u8ba1\u7b97\u9884\u4f30...')
      setToastType('info')

      const { data: result } = await apiJson<{
        output_file?: string
        filename?: string
        data_url?: string
        download_url?: string
      }>('/api/estimate/recalculate', {
        method: 'POST',
      })
      if (result.data_url) {
        const nextFile = String(result.output_file || result.filename || '')
        const nextDataUrl = String(result.data_url || '')
        const nextDownloadUrl = String(result.download_url || '')
        setEstimateResultFile(nextFile)
        setEstimateResultDataUrl(nextDataUrl)
        setEstimateResultDownloadUrl(nextDownloadUrl)
        setEstimateResultsPage(1)

        const { data: resultData } = await apiJson<CalculationResult>(nextDataUrl)
        setEstimateResults(resultData)
        startTransition(() => {
          setActiveTab('estimateResults')
        })

        setToastMessage('\u9884\u4f30\u5df2\u91cd\u65b0\u8ba1\u7b97\u5b8c\u6210')
        setToastType('success')
      } else {
        setToastMessage('\u9884\u4f30\u91cd\u65b0\u8ba1\u7b97\u5931\u8d25: \u540e\u7aef\u672a\u8fd4\u56de\u7ed3\u679c\u5730\u5740')
        setToastType('error')
      }
    } catch (error: unknown) {
      if (isApiHttpError(error) && error.status === 401) {
        handleUnauthorized()
        return
      }
      setToastMessage(`\u9884\u4f30\u91cd\u65b0\u8ba1\u7b97\u5931\u8d25: ${getApiErrorMessage(error, '\u672a\u77e5\u9519\u8bef')}`)
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

  const handleKeyPress = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key !== 'Enter') return
    if ((e.nativeEvent as KeyboardEvent).isComposing) return
    const value = e.currentTarget.value
    setSearch(value)
    void loadClients(value)
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

  const downloadEstimateResult = async () => {
    if (!estimateResultDownloadUrl && !estimateResultFile) return
    try {
      const downloadPath = estimateResultDownloadUrl || `/api/download/${encodeURIComponent(estimateResultFile)}`
      const { blob } = await apiBlob(downloadPath)
      const url = window.URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = estimateResultFile || 'estimate_result.xlsx'
      document.body.appendChild(anchor)
      anchor.click()
      anchor.remove()
      window.URL.revokeObjectURL(url)
    } catch (error: unknown) {
      if (isApiHttpError(error) && error.status === 401) {
        handleUnauthorized()
        return
      }
      setToastMessage(`\u4e0b\u8f7d\u9884\u4f30\u7ed3\u679c\u5931\u8d25: ${getApiErrorMessage(error, '\u672a\u77e5\u9519\u8bef')}`)
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
  const openClientDetail = (clientName: string) => {
    setSelectedClientName(clientName)
    setActiveTab('clientDetail')
  }
  const closeClientDetail = () => {
    setActiveTab('clientLedger')
  }
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
        hasEstimateResults={Boolean(estimateResults)}
        onOpenLogin={() => setShowLoginModal(true)}
        onAddClient={() => handleAction(() => setIsAddingClient(true))}
        onSyncFeishu={() => handleAction(handleSyncFeishu)}
        onUploadContract={(e) => handleAction(() => handleUploadContract(e))}
        onUploadConsumption={(e) => handleAction(() => handleCalculate(e))}
        onUploadEstimateConsumption={(e) => handleAction(() => handleEstimateCalculate(e))}
        onRecalculate={() => handleAction(handleRecalculate)}
        onRecalculateEstimate={() => handleAction(handleEstimateRecalculate)}
        onDownloadResult={downloadResult}
        onDownloadEstimateResult={downloadEstimateResult}
        dashboardData={dashboardData}
        onNotify={(message, type) => {
          setToastMessage(message)
          setToastType(type)
        }}
        onRequireAuth={() => {
          handleLogout()
          setShowLoginModal(true)
        }}
        selectedClientName={selectedClientName}
        onOpenClientDetail={openClientDetail}
        onCloseClientDetail={closeClientDetail}
        syncResult={syncResult}
        contractChangeReviews={contractChangeReviews}
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
        onApproveContractChangeReview={(reviewId, overrideNewFeeClause) =>
          handleAction(() => handleApproveContractChangeReview(reviewId, overrideNewFeeClause))
        }
        onIgnoreContractChangeReview={(reviewId) => handleAction(() => handleIgnoreContractChangeReview(reviewId))}
        onBatchApproveContractChangeReviews={(reviewIds, overrideNewFeeClauseByReviewId) =>
          handleAction(() =>
            handleBatchApproveContractChangeReviews(reviewIds, overrideNewFeeClauseByReviewId),
          )
        }
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
        estimateResults={estimateResults}
        pagedEstimateResultsData={pagedEstimateResultsData}
        estimateResultsTotalRows={estimateResultsTotalRows}
        estimateResultsPage={estimateResultsPage}
        estimateResultsTotalPages={estimateResultsTotalPages}
        estimateResultsPageSize={estimateResultsPageSize}
        onEstimateResultsPageSizeChange={(size) => {
          setEstimateResultsPageSize(size)
          setEstimateResultsPage(1)
        }}
        onPrevEstimateResultsPage={() => setEstimateResultsPage((p) => Math.max(1, p - 1))}
        onNextEstimateResultsPage={() => setEstimateResultsPage((p) => Math.min(estimateResultsTotalPages, p + 1))}
        formatNumber={formatNumber}
        taskHistoryItems={taskHistory.items}
        taskHistoryLoading={taskHistory.loading}
        taskHistoryLimit={taskHistory.limit}
        taskHistoryCurrentPage={taskHistory.currentPage}
        taskHistoryTotalCount={taskHistory.totalCount}
        taskHistoryActorFilter={taskHistory.actorFilter}
        taskHistoryActionFilter={taskHistory.actionFilter}
        taskHistoryStatusFilter={taskHistory.statusFilter}
        taskHistoryDaysFilter={taskHistory.daysFilter}
        onTaskHistoryLimitChange={taskHistory.setLimit}
        onTaskHistoryCurrentPageChange={taskHistory.setCurrentPage}
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





