import { useEffect, useMemo, useRef, useState } from 'react'
import { apiJson, isApiHttpError } from './apiClient'
import type { LatestMonthClientRow, LatestMonthClientsResponse } from './billingTypes'
import { EmptyState } from './EmptyState'
import { Skeleton } from './Skeleton'

interface LatestMonthClientsPanelProps {
  active: boolean
  isAuthenticated: boolean
  selectedClientName: string | null
  formatNumber: (value: string | number) => string
  onOpenClientDetail: (clientName: string) => void
  onNotify?: (message: string, type: 'info' | 'success' | 'error') => void
  onRequireAuth?: () => void
}

type LedgerColumnKey = 'month' | 'entity' | 'bill_type' | 'bill_amount' | 'note'

interface LedgerFilterOption {
  value: string
  label: string
}

interface LedgerColumn {
  key: LedgerColumnKey
  label: string
  numeric?: boolean
}

const FILTER_ALL_VALUE = '__ALL__'

const LEDGER_TABLE_COLUMNS: LedgerColumn[] = [
  { key: 'month', label: '归属月份' },
  { key: 'entity', label: '公司主体' },
  { key: 'bill_amount', label: '账单金额', numeric: true },
  { key: 'note', label: '备注' },
]

const renderTextValue = (value: string | null | undefined) => {
  const text = String(value ?? '').trim()
  return text || '—'
}

const normalizeFilterValue = (value: string | null | undefined) => renderTextValue(value)

const buildFilterOptions = (
  rows: LatestMonthClientRow[],
  selector: (row: LatestMonthClientRow) => string | null | undefined,
  allLabel: string,
): LedgerFilterOption[] => {
  const values = new Set<string>()
  rows.forEach((row) => {
    values.add(normalizeFilterValue(selector(row)))
  })

  return [
    { value: FILTER_ALL_VALUE, label: allLabel },
    ...Array.from(values)
      .sort((a, b) => a.localeCompare(b, 'zh-Hans-CN'))
      .map((value) => ({ value, label: value })),
  ]
}

const renderMetricCell = (
  row: LatestMonthClientRow,
  column: LedgerColumn,
  latestMonth: string | null,
  formatNumber: (value: string | number) => string,
) => {
  if (column.key === 'month') {
    return renderTextValue(row.month || latestMonth)
  }
  if (column.key === 'bill_amount') {
    const billAmount = Number(row.bill_amount || row.total || 0)
    return formatNumber(Number.isFinite(billAmount) ? billAmount : 0)
  }
  if (column.key === 'entity') return renderTextValue(row.entity)
  if (column.key === 'note') return renderTextValue(row.note)
  return '—'
}

const getRowKey = (row: LatestMonthClientRow, latestMonth: string | null) =>
  `${row.month || latestMonth || 'unknown'}::${row.client_name}`

export function LatestMonthClientsPanel({
  active,
  isAuthenticated,
  selectedClientName,
  formatNumber,
  onOpenClientDetail,
  onNotify,
  onRequireAuth,
}: LatestMonthClientsPanelProps) {
  const [data, setData] = useState<LatestMonthClientsResponse>({ latest_month: null, rows: [] })
  const [loading, setLoading] = useState(false)
  const [errorMessage, setErrorMessage] = useState('')

  const [clientNameQuery, setClientNameQuery] = useState('')
  const [currentPage, setCurrentPage] = useState(1)
  const [pageSize, setPageSize] = useState(50)

  const [isClientDropdownOpen, setIsClientDropdownOpen] = useState(false)
  const [highlightedClientIndex, setHighlightedClientIndex] = useState(-1)
  const [showAllClientOptions, setShowAllClientOptions] = useState(false)

  const [noteDrafts, setNoteDrafts] = useState<Record<string, string>>({})
  const [noteOriginals, setNoteOriginals] = useState<Record<string, string>>({})
  const [editingNoteKey, setEditingNoteKey] = useState<string | null>(null)
  const [savingNoteKey, setSavingNoteKey] = useState<string | null>(null)

  const clientComboboxRef = useRef<HTMLDivElement | null>(null)
  const tableContainerRef = useRef<HTMLDivElement | null>(null)

  const clientNameOptions = useMemo(
    () => buildFilterOptions(data.rows, (row) => row.client_name, '全部客户简称'),
    [data.rows],
  )
  const normalizedClientQuery = clientNameQuery.trim().toLowerCase()

  const filteredClientNameOptions = useMemo(() => {
    if (!normalizedClientQuery) return clientNameOptions
    return clientNameOptions.filter((option) => option.label.toLowerCase().includes(normalizedClientQuery))
  }, [clientNameOptions, normalizedClientQuery])

  const clientDropdownOptions = useMemo(
    () => (showAllClientOptions ? clientNameOptions : filteredClientNameOptions),
    [clientNameOptions, filteredClientNameOptions, showAllClientOptions],
  )

  const isExactClientQuery = useMemo(
    () => clientNameOptions.some((option) => option.label.toLowerCase() === normalizedClientQuery),
    [clientNameOptions, normalizedClientQuery],
  )
  const clientAllOptionLabel = useMemo(
    () => (clientNameOptions.find((option) => option.value === FILTER_ALL_VALUE)?.label || '').toLowerCase(),
    [clientNameOptions],
  )

  useEffect(() => {
    if (!isClientDropdownOpen) return
    if (clientDropdownOptions.length === 0) {
      if (highlightedClientIndex !== -1) setHighlightedClientIndex(-1)
      return
    }
    if (highlightedClientIndex < 0 || highlightedClientIndex >= clientDropdownOptions.length) {
      setHighlightedClientIndex(0)
    }
  }, [clientDropdownOptions, highlightedClientIndex, isClientDropdownOpen])

  useEffect(() => {
    const nextNotes: Record<string, string> = {}
    data.rows.forEach((row) => {
      nextNotes[getRowKey(row, data.latest_month)] = String(row.note || '')
    })
    setNoteDrafts(nextNotes)
    setNoteOriginals(nextNotes)
    if (editingNoteKey && !(editingNoteKey in nextNotes)) {
      setEditingNoteKey(null)
    }
  }, [data.latest_month, data.rows, editingNoteKey])

  const filteredRows = useMemo(() => {
    return data.rows.filter((row) => {
      const clientNameValue = row.client_name.toLowerCase()

      const matchesClient = !normalizedClientQuery || normalizedClientQuery === clientAllOptionLabel
        ? true
        : isExactClientQuery
          ? clientNameValue === normalizedClientQuery
          : clientNameValue.includes(normalizedClientQuery)

      return matchesClient
    })
  }, [
    clientAllOptionLabel,
    data.rows,
    isExactClientQuery,
    normalizedClientQuery,
  ])

  useEffect(() => {
    setCurrentPage(1)
  }, [normalizedClientQuery])

  const paginatedRows = useMemo(() => {
    const startIndex = (currentPage - 1) * pageSize
    return filteredRows.slice(startIndex, startIndex + pageSize)
  }, [filteredRows, currentPage, pageSize])

  const totalPages = Math.ceil(filteredRows.length / pageSize)

  const closeClientDropdown = () => {
    setIsClientDropdownOpen(false)
    setHighlightedClientIndex(-1)
    setShowAllClientOptions(false)
  }

  const selectClientOption = (option: LedgerFilterOption) => {
    setClientNameQuery(option.value === FILTER_ALL_VALUE ? '' : option.label)
    closeClientDropdown()
  }

  useEffect(() => {
    const onMouseDown = (event: MouseEvent) => {
      if (clientComboboxRef.current && !clientComboboxRef.current.contains(event.target as Node)) {
        closeClientDropdown()
      }
    }

    document.addEventListener('mousedown', onMouseDown)
    return () => document.removeEventListener('mousedown', onMouseDown)
  }, [])

  const restoreNoteDraft = (rowKey: string) => {
    setNoteDrafts((current) => ({ ...current, [rowKey]: noteOriginals[rowKey] || '' }))
  }

  const isNoteDirty = (rowKey: string) =>
    (noteDrafts[rowKey] || '').trim() !== (noteOriginals[rowKey] || '').trim()

  const saveNote = async (row: LatestMonthClientRow): Promise<boolean> => {
    const month = row.month || data.latest_month
    if (!month) {
      onNotify?.('当前月份为空，无法保存备注', 'error')
      return false
    }

    const rowKey = getRowKey(row, data.latest_month)
    const nextNote = (noteDrafts[rowKey] || '').trim()
    setSavingNoteKey(rowKey)

    try {
      const { data: payload, res } = await apiJson<{ month: string; client_name: string; note: string | null }>(
        '/api/dashboard/latest-month/client-note',
        {
          method: 'PUT',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            month,
            client_name: row.client_name,
            note: nextNote || null,
          }),
        },
        { throwOnHttpError: false },
      )

      if (res.status === 401) {
        onRequireAuth?.()
        return false
      }
      if (!res.ok) {
        onNotify?.('保存备注失败', 'error')
        return false
      }

      const persistedNote = typeof payload?.note === 'string' ? payload.note.trim() : ''
      setData((current) => ({
        ...current,
        rows: current.rows.map((item) => {
          const itemMonth = item.month || current.latest_month
          if (item.client_name === row.client_name && itemMonth === month) {
            return { ...item, note: persistedNote || null }
          }
          return item
        }),
      }))

      setNoteDrafts((current) => ({ ...current, [rowKey]: persistedNote }))
      setNoteOriginals((current) => ({ ...current, [rowKey]: persistedNote }))
      setEditingNoteKey(null)
      onNotify?.('备注已保存', 'success')
      return true
    } catch (error: unknown) {
      if (isApiHttpError(error) && error.status === 401) {
        onRequireAuth?.()
        return false
      }
      const nextError = error instanceof Error ? error.message : '保存备注失败'
      onNotify?.(nextError, 'error')
      return false
    } finally {
      setSavingNoteKey(null)
    }
  }

  const confirmSwitchEditingNote = async (nextRowKey: string) => {
    if (!editingNoteKey || editingNoteKey === nextRowKey) return true
    if (!isNoteDirty(editingNoteKey)) return true

    const saveAndSwitch = window.confirm(
      '当前备注有未保存修改。\n点击“确定”：保存并切换。\n点击“取消”：继续选择其他操作。',
    )
    if (saveAndSwitch) {
      const currentRow = data.rows.find(
        (item) => getRowKey(item, data.latest_month) === editingNoteKey,
      )
      if (!currentRow) return false
      return saveNote(currentRow)
    }

    const discardAndSwitch = window.confirm(
      '是否放弃未保存修改并切换？\n点击“确定”：放弃并切换。\n点击“取消”：继续编辑当前备注。',
    )
    if (discardAndSwitch) {
      restoreNoteDraft(editingNoteKey)
      setEditingNoteKey(null)
      return true
    }

    return false
  }

  const startEditNote = async (row: LatestMonthClientRow) => {
    const rowKey = getRowKey(row, data.latest_month)
    const canSwitch = await confirmSwitchEditingNote(rowKey)
    if (!canSwitch) return

    setEditingNoteKey(rowKey)
    setNoteDrafts((current) => ({
      ...current,
      [rowKey]: current[rowKey] ?? noteOriginals[rowKey] ?? String(row.note || ''),
    }))
  }

  const cancelEditNote = (rowKey: string) => {
    restoreNoteDraft(rowKey)
    if (editingNoteKey === rowKey) {
      setEditingNoteKey(null)
    }
  }

  useEffect(() => {
    if (!tableContainerRef.current) return
    tableContainerRef.current.scrollTop = 0
  }, [normalizedClientQuery, currentPage, filteredRows.length])

  useEffect(() => {
    if (!active || !isAuthenticated) return

    const controller = new AbortController()
    setErrorMessage('')
    setLoading(true)

    apiJson<LatestMonthClientsResponse>(
      '/api/dashboard/latest-month/clients',
      { signal: controller.signal },
      { throwOnHttpError: false },
    )
      .then(({ data: payload, res }) => {
        if (controller.signal.aborted) return

        if (res.status === 401) {
          onRequireAuth?.()
          return
        }

        if (!res.ok) {
          const nextError = '加载最新月客户数据失败'
          setErrorMessage(nextError)
          onNotify?.(nextError, 'error')
          return
        }

        setData({
          latest_month: payload.latest_month ?? null,
          rows: Array.isArray(payload.rows) ? payload.rows : [],
        })
        setErrorMessage('')
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return
        if (isApiHttpError(error) && error.status === 401) {
          onRequireAuth?.()
          return
        }
        const nextError = error instanceof Error ? error.message : '加载最新月客户数据失败'
        setErrorMessage(nextError)
        onNotify?.(nextError, 'error')
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setLoading(false)
        }
      })

    return () => controller.abort()
  }, [active, isAuthenticated, onNotify, onRequireAuth])

  if (!active) return null

  if (!isAuthenticated) {
    return (
      <EmptyState
        title="请先登录"
        description="登录后即可查看最新月份的账单明细。"
      />
    )
  }

  return (
    <section className="latest-month-section">
      <div className="ledger-page-shell">
        <div className="table-wrapper latest-month-card">
          <div className="latest-month-toolbar">
            <div className="latest-month-filter-grid">
            <label className="latest-month-filter-field" htmlFor="ledger-filter-client-name">
              <span>客户简称</span>
              <div className={`combobox${isClientDropdownOpen ? ' is-open' : ''}`} ref={clientComboboxRef}>
                <input
                  id="ledger-filter-client-name"
                  className="combobox-input"
                  type="text"
                  placeholder="输入或选择客户简称"
                  value={clientNameQuery}
                  onFocus={() => {
                    setShowAllClientOptions(false)
                    setIsClientDropdownOpen(true)
                    if (filteredClientNameOptions.length > 0) setHighlightedClientIndex(0)
                  }}
                  onChange={(event) => {
                    setClientNameQuery(event.target.value)
                    setShowAllClientOptions(false)
                    setIsClientDropdownOpen(true)
                    setHighlightedClientIndex(0)
                  }}
                  onKeyDown={(event) => {
                    if (event.key === 'Escape') {
                      closeClientDropdown()
                      return
                    }
                    if (event.key === 'ArrowDown') {
                      event.preventDefault()
                      if (!isClientDropdownOpen) {
                        setShowAllClientOptions(false)
                        setIsClientDropdownOpen(true)
                        if (filteredClientNameOptions.length > 0) setHighlightedClientIndex(0)
                        return
                      }
                      if (clientDropdownOptions.length === 0) return
                      setHighlightedClientIndex((current) => Math.min(current + 1, clientDropdownOptions.length - 1))
                      return
                    }
                    if (event.key === 'ArrowUp') {
                      event.preventDefault()
                      if (!isClientDropdownOpen) {
                        setShowAllClientOptions(false)
                        setIsClientDropdownOpen(true)
                        if (filteredClientNameOptions.length > 0) {
                          setHighlightedClientIndex(filteredClientNameOptions.length - 1)
                        }
                        return
                      }
                      if (clientDropdownOptions.length === 0) return
                      setHighlightedClientIndex((current) => Math.max(current - 1, 0))
                      return
                    }
                    if (event.key === 'Enter') {
                      if (!isClientDropdownOpen) return
                      event.preventDefault()
                      const option = clientDropdownOptions[highlightedClientIndex]
                      if (option) selectClientOption(option)
                    }
                  }}
                />
                <button
                  type="button"
                  className="combobox-trigger"
                  aria-label={isClientDropdownOpen ? '收起客户简称筛选选项' : '展开客户简称筛选选项'}
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => {
                    if (isClientDropdownOpen && showAllClientOptions) {
                      closeClientDropdown()
                      return
                    }
                    setShowAllClientOptions(true)
                    setIsClientDropdownOpen(true)
                    setHighlightedClientIndex(clientNameOptions.length > 0 ? 0 : -1)
                  }}
                >
                  <span className="combobox-trigger-icon" aria-hidden="true" />
                </button>
                {isClientDropdownOpen && clientDropdownOptions.length > 0 && (
                  <div className="combobox-list">
                    {clientDropdownOptions.map((option, index) => (
                      <button
                        key={option.value}
                        type="button"
                        className={`combobox-item${index === highlightedClientIndex ? ' is-active' : ''}`}
                        onMouseEnter={() => setHighlightedClientIndex(index)}
                        onClick={() => selectClientOption(option)}
                      >
                        {option.label}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </label>
          </div>
        </div>

        {loading ? (
          <div className="latest-month-skeleton">
            <Skeleton variant="rect" height={44} />
            <Skeleton variant="rect" height={280} />
          </div>
        ) : errorMessage ? (
          <EmptyState
            title="最新月份数据加载失败"
            description={errorMessage}
          />
        ) : data.rows.length === 0 ? (
          <EmptyState
            title="暂无最新月份数据"
            description="请先完成月度计算后再查看账单明细。"
          />
        ) : (
          <div ref={tableContainerRef} className="data-table-container latest-month-table-wrap">
            <table className="data-table latest-month-table">
              <thead>
                <tr>
                  <th className="col-client">客户简称</th>
                  {LEDGER_TABLE_COLUMNS.map((column) => (
                    <th key={column.key} className={column.numeric ? 'cell-number' : 'cell-type'}>
                      {column.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {paginatedRows.length === 0 ? (
                  <tr className="latest-month-empty-row">
                    <td colSpan={LEDGER_TABLE_COLUMNS.length + 1}>没有匹配的筛选结果</td>
                  </tr>
                ) : (
                  paginatedRows.map((row) => {
                    const rowKey = getRowKey(row, data.latest_month)
                    const isEditingNote = editingNoteKey === rowKey
                    const draftNote = noteDrafts[rowKey] ?? ''
                    const persistedNote = noteOriginals[rowKey] ?? String(row.note || '')
                    const isSaving = savingNoteKey === rowKey

                    return (
                      <tr
                        key={rowKey}
                        className={row.client_name === selectedClientName ? 'is-selected' : ''}
                      >
                        <td className="cell-name">
                          <button
                            type="button"
                            className="ledger-link-btn"
                            onClick={() => onOpenClientDetail(row.client_name)}
                          >
                            {row.client_name}
                          </button>
                        </td>

                        {LEDGER_TABLE_COLUMNS.map((column) => {
                          if (column.key === 'note') {
                            if (!isEditingNote) {
                              return (
                                <td key={column.key} className="cell-type">
                                  <div className="ledger-note-display">
                                    <span className="ledger-note-text">{renderTextValue(persistedNote)}</span>
                                    <button
                                      type="button"
                                      className="ledger-note-edit-btn"
                                      onClick={() => void startEditNote(row)}
                                    >
                                      编辑
                                    </button>
                                  </div>
                                </td>
                              )
                            }

                            return (
                              <td key={column.key} className="cell-type">
                                <div className="ledger-note-editor">
                                  <input
                                    type="text"
                                    className="ledger-note-input"
                                    placeholder="输入备注"
                                    value={draftNote}
                                    onChange={(event) => {
                                      const value = event.target.value
                                      setNoteDrafts((current) => ({ ...current, [rowKey]: value }))
                                    }}
                                    onKeyDown={(event) => {
                                      if (event.key === 'Enter') {
                                        event.preventDefault()
                                        void saveNote(row)
                                      }
                                      if (event.key === 'Escape') {
                                        event.preventDefault()
                                        cancelEditNote(rowKey)
                                      }
                                    }}
                                  />
                                  <div className="ledger-note-actions">
                                    <button
                                      type="button"
                                      className="ledger-note-save-btn"
                                      disabled={isSaving}
                                      onClick={() => void saveNote(row)}
                                    >
                                      {isSaving ? '保存中' : '保存'}
                                    </button>
                                    <button
                                      type="button"
                                      className="ledger-note-cancel-btn"
                                      disabled={isSaving}
                                      onClick={() => cancelEditNote(rowKey)}
                                    >
                                      取消
                                    </button>
                                  </div>
                                </div>
                              </td>
                            )
                          }

                          return (
                            <td key={column.key} className={column.numeric ? 'cell-number' : 'cell-type'}>
                              {renderMetricCell(row, column, data.latest_month, formatNumber)}
                            </td>
                          )
                        })}
                      </tr>
                    )
                  })
                )}
              </tbody>
            </table>
            {data.rows.length > 0 && (
              <div className="table-pagination">
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span className="table-pagination-info">每页显示</span>
                  <select 
                    value={pageSize}
                    onChange={(e) => {
                      setPageSize(Number(e.target.value))
                      setCurrentPage(1)
                    }}
                    style={{ padding: '4px 8px', borderRadius: '4px', border: '1px solid var(--border-strong)', background: 'var(--bg-surface)', cursor: 'pointer' }}
                  >
                    <option value={20}>20</option>
                    <option value={50}>50</option>
                    <option value={100}>100</option>
                    <option value={500}>500</option>
                  </select>
                  <span className="table-pagination-info">项</span>
                </div>
                
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <button
                    type="button"
                    disabled={currentPage === 1}
                    onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                  >
                    上一页
                  </button>
                  <span className="table-pagination-info" style={{ margin: '0 8px' }}>
                    第 {currentPage} 页 / 共 {Math.max(1, totalPages)} 页
                  </span>
                  <button
                    type="button"
                    disabled={currentPage >= Math.max(1, totalPages)}
                    onClick={() => setCurrentPage((p) => Math.min(Math.max(1, totalPages), p + 1))}
                  >
                    下一页
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
        </div>
      </div>
    </section>
  )
}
