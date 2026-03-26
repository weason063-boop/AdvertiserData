import { useCallback, useEffect, useRef, useState } from 'react'
import type { OperationAuditLog } from './billingTypes'
import { apiBlob, apiJson, isApiHttpError, parseDownloadFilename } from './apiClient'

type ToastType = 'info' | 'success' | 'error'

interface UseTaskHistoryOptions {
  enabled: boolean
  onUnauthorized: () => void
  onForbidden?: () => void
  onNotify: (message: string, type: ToastType) => void
}

const DEFAULT_LIMIT = 100
const DEFAULT_DAYS_FILTER = '30'

const getApiErrorMessage = (error: unknown, fallback: string): string => {
  if (isApiHttpError(error)) {
    return error.message || fallback
  }
  if (error instanceof Error && error.message) {
    return error.message
  }
  return fallback
}

export function useTaskHistory({ enabled, onUnauthorized, onForbidden, onNotify }: UseTaskHistoryOptions) {
  const enabledRef = useRef(enabled)
  const onUnauthorizedRef = useRef(onUnauthorized)
  const onForbiddenRef = useRef(onForbidden)
  const onNotifyRef = useRef(onNotify)

  useEffect(() => {
    enabledRef.current = enabled
  }, [enabled])

  useEffect(() => {
    onUnauthorizedRef.current = onUnauthorized
  }, [onUnauthorized])

  useEffect(() => {
    onForbiddenRef.current = onForbidden
  }, [onForbidden])

  useEffect(() => {
    onNotifyRef.current = onNotify
  }, [onNotify])

  const [items, setItems] = useState<OperationAuditLog[]>([])
  const [loading, setLoading] = useState(false)
  const [limit, setLimit] = useState(DEFAULT_LIMIT)
  const [actorFilter, setActorFilter] = useState('')
  const [actionFilter, setActionFilter] = useState('all')
  const [statusFilter, setStatusFilter] = useState('all')
  const [daysFilter, setDaysFilter] = useState(DEFAULT_DAYS_FILTER)

  const buildParams = useCallback(() => {
    const params = new URLSearchParams()
    params.set('limit', String(limit))
    if (actorFilter.trim()) {
      params.set('actor', actorFilter.trim())
    }
    if (actionFilter !== 'all') {
      params.set('action', actionFilter)
    }
    if (statusFilter !== 'all') {
      params.set('status', statusFilter)
    }
    if (daysFilter !== 'all') {
      params.set('days', daysFilter)
    }
    return params.toString()
  }, [limit, actorFilter, actionFilter, statusFilter, daysFilter])

  const loadTaskHistory = useCallback(async (silent = false) => {
    if (!silent) {
      setLoading(true)
    }
    try {
      const query = buildParams()
      const { data } = await apiJson<{ items?: OperationAuditLog[] }>(
        `/api/task-history${query ? `?${query}` : ''}`,
      )
      setItems(data.items || [])
    } catch (error: unknown) {
      if (isApiHttpError(error) && error.status === 401) {
        onUnauthorizedRef.current()
        return
      }
      if (isApiHttpError(error) && error.status === 403) {
        setItems([])
        onForbiddenRef.current?.()
        return
      }
      console.error('Failed to load task history', error)
    } finally {
      if (!silent) {
        setLoading(false)
      }
    }
  }, [buildParams])

  const refreshSilently = useCallback(async () => {
    if (!enabledRef.current) return
    await loadTaskHistory(true)
  }, [loadTaskHistory])

  const exportTaskHistory = useCallback(async () => {
    try {
      const query = buildParams()
      const { blob, res } = await apiBlob(`/api/task-history/export${query ? `?${query}` : ''}`)
      const filename = parseDownloadFilename(
        res.headers.get('content-disposition'),
        `task_history_${new Date().toISOString().slice(0, 10)}.csv`,
      )
      const url = window.URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = filename
      document.body.appendChild(anchor)
      anchor.click()
      anchor.remove()
      window.URL.revokeObjectURL(url)
      onNotifyRef.current('任务历史导出成功', 'success')
    } catch (error: unknown) {
      if (isApiHttpError(error) && error.status === 401) {
        onUnauthorizedRef.current()
        return
      }
      if (isApiHttpError(error) && error.status === 403) {
        onForbiddenRef.current?.()
        return
      }
      onNotifyRef.current(`导出失败: ${getApiErrorMessage(error, '未知错误')}`, 'error')
    }
  }, [buildParams])

  const toggleFailedOnly = useCallback(() => {
    setStatusFilter((prev) => (prev === 'failed' ? 'all' : 'failed'))
  }, [])

  const reset = useCallback(() => {
    setItems([])
    setActorFilter('')
    setActionFilter('all')
    setStatusFilter('all')
    setDaysFilter(DEFAULT_DAYS_FILTER)
    setLimit(DEFAULT_LIMIT)
    setLoading(false)
  }, [])

  useEffect(() => {
    if (!enabled) return
    loadTaskHistory()
  }, [enabled, loadTaskHistory])

  return {
    items,
    loading,
    limit,
    actorFilter,
    actionFilter,
    statusFilter,
    daysFilter,
    setLimit,
    setActorFilter,
    setActionFilter,
    setStatusFilter,
    setDaysFilter,
    loadTaskHistory,
    refreshSilently,
    exportTaskHistory,
    toggleFailedOnly,
    reset,
  }
}
