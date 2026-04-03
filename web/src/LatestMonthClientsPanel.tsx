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
  { key: 'bill_type', label: '账单类型' },
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
  if (column.key === 'bill_type') return renderTextValue(row.bill_type)
  return '—'
}

const getRowKey = (row: LatestMonthClientRow, latestMonth: string | null) => `${row.month || latestMonth || 'unknown'}::${row.client_name}`

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
  const [isClientDropdownOpen, setIsClientDropdownOpen] = useState(false)
  const [highlightedClientIndex, setHighlightedClientIndex] = useState(-1)
  const [showAllClientOptions, setShowAllClientOptions] = useState(false)
  const [billTypeQuery, setBillTypeQuery] = useState('')
  const [isBillTypeDropdownOpen, setIsBillTypeDropdownOpen] = useState(false)
  const [highlightedBillTypeIndex, setHighlightedBillTypeIndex] = useState(-1)
  const [showAllBillTypeOptions, setShowAllBillTypeOptions] = useState(false)
  const [noteDrafts, setNoteDrafts] = useState<Record<string, string>>({})
  const [noteOriginals, setNoteOriginals] = useState<Record<string, string>>({})
  const [editingNoteKey, setEditingNoteKey] = useState<string | null>(null)
  const [savingNoteKey, setSavingNoteKey] = useState<string | null>(null)
  const clientComboboxRef = useRef<HTMLDivElement | null>(null)
  const billTypeComboboxRef = useRef<HTMLDivElement | null>(null)

  const clientNameOptions = useMemo(
    () => buildFilterOptions(data.rows, (row) => row.client_name, '全部客户简称')
    [data.rows],
  )
  const billTypeOptions = useMemo(
    () => buildFilterOptions(data.rows, (row) => row.bill_type, '全部账单类型'),
    [data.rows],
  )

  const normalizedClientQuery = clientNameQuery.trim().toLowerCase()
  const normalizedBillTypeQuery = billTypeQuery.trim().toLowerCase()
  const filteredClientNameOptions = useMemo(() => {
    if (!normalizedClientQuery) return clientNameOptions
    return clientNameOptions.filter((option) => option.label.toLowerCase().includes(normalizedClientQuery))
  }, [clientNameOptions, normalizedClientQuery])
  const filteredBillTypeOptions = useMemo(() => {
    if (!normalizedBillTypeQuery) return billTypeOptions
    return billTypeOptions.filter((option) => option.label.toLowerCase().includes(normalizedBillTypeQuery))
  }, [billTypeOptions, normalizedBillTypeQuery])
  const clientDropdownOptions = useMemo(
    () => (showAllClientOptions ? clientNameOptions : filteredClientNameOptions),
    [clientNameOptions, filteredClientNameOptions, showAllClientOptions],
  )
  const billTypeDropdownOptions = useMemo(
    () => (showAllBillTypeOptions ? billTypeOptions : filteredBillTypeOptions),
    [billTypeOptions, filteredBillTypeOptions, showAllBillTypeOptions],
  )

  const isExactClientQuery = useMemo(
    () => clientNameOptions.some((option) => option.label.toLowerCase() === normalizedClientQuery),
    [clientNameOptions, normalizedClientQuery],
  )
  const isExactBillTypeQuery = useMemo(
    () => billTypeOptions.some((option) => option.label.toLowerCase() === normalizedBillTypeQuery),
    [billTypeOptions, normalizedBillTypeQuery],
  )
  const billTypeAllOptionLabel = useMemo(
    () => (billTypeOptions.find((option) => option.value === FILTER_ALL_VALUE)?.label || '').toLowerCase(),
    [billTypeOptions],
  )
  const clientAllOptionLabel = useMemo(
    () => (clientNameOptions.find((option) => option.value === FILTER_ALL_VALUE)?.label || '').toLowerCase(),
    [clientNameOptions],
  )

  useEffect(() => {
    if (!isClientDropdownOpen) return
    if (clientDropdownOptions.length === 0) {
      if (highlightedClientIndex !== -1) setHighlightedClientIndex(-1)
      return false
    }
    if (highlightedClientIndex < 0 || highlightedClientIndex >= clientDropdownOptions.length) {
      setHighlightedClientIndex(0)
    }
  }, [clientDropdownOptions, highlightedClientIndex, isClientDropdownOpen])
  useEffect(() => {
    if (!isBillTypeDropdownOpen) return
    if (billTypeDropdownOptions.length === 0) {
      if (highlightedBillTypeIndex !== -1) setHighlightedBillTypeIndex(-1)
      return
    }
    if (highlightedBillTypeIndex < 0 || highlightedBillTypeIndex >= billTypeDropdownOptions.length) {
      setHighlightedBillTypeIndex(0)
    }
  }, [billTypeDropdownOptions, highlightedBillTypeIndex, isBillTypeDropdownOpen])

  useEffect(() => {
    const nextDrafts: Record<string, string> = {}
    data.rows.forEach((row) => {
      nextDrafts[getRowKey(row, data.latest_month)] = String(row.note || '')
    })
    setNoteDrafts(nextDrafts)
    setNoteOriginals(nextDrafts)
    if (editingNoteKey && !(editingNoteKey in nextDrafts)) {
      setEditingNoteKey(null)
    }
  }, [data.latest_month, data.rows, editingNoteKey])

  const filteredRows = useMemo(() => {
    return data.rows.filter((row) => {
      const clientNameValue = row.client_name.toLowerCase()
      const billTypeValue = normalizeFilterValue(row.bill_type).toLowerCase()
      const matchesClient = !normalizedClientQuery || normalizedClientQuery === clientAllOptionLabel
        ? true
        : isExactClientQuery
          ? clientNameValue === normalizedClientQuery
          : clientNameValue.includes(normalizedClientQuery)
      const matchesBillType = !normalizedBillTypeQuery || normalizedBillTypeQuery === billTypeAllOptionLabel
        ? true
        : isExactBillTypeQuery
          ? billTypeValue === normalizedBillTypeQuery
          : billTypeValue.includes(normalizedBillTypeQuery)
      return (
        matchesClient && matchesBillType
      )
    })
  }, [
    clientAllOptionLabel,
    billTypeAllOptionLabel,
    data.rows,
    isExactBillTypeQuery,
    isExactClientQuery,
    normalizedBillTypeQuery,
    normalizedClientQuery,
  ])

  const closeClientDropdown = () => {
    setIsClientDropdownOpen(false)
    setHighlightedClientIndex(-1)
    setShowAllClientOptions(false)
  }
  const closeBillTypeDropdown = () => {
    setIsBillTypeDropdownOpen(false)
    setHighlightedBillTypeIndex(-1)
    setShowAllBillTypeOptions(false)
  }

  const selectClientOption = (option: LedgerFilterOption) => {
    setClientNameQuery(option.value === FILTER_ALL_VALUE ? '' : option.label)
    closeClientDropdown()
  }
  const selectBillTypeOption = (option: LedgerFilterOption) => {
    setBillTypeQuery(option.value === FILTER_ALL_VALUE ? '' : option.label)
    closeBillTypeDropdown()
  }

  useEffect(() => {
    const onMouseDown = (event: MouseEvent) => {
      if (clientComboboxRef.current && !clientComboboxRef.current.contains(event.target as Node)) {
        closeClientDropdown()
      }
      if (billTypeComboboxRef.current && !billTypeComboboxRef.current.contains(event.target as Node)) {
        closeBillTypeDropdown()
      }
    }
    document.addEventListener('mousedown', onMouseDown)
    return () => document.removeEventListener('mousedown', onMouseDown)
  }, [])

  const isNoteDirty = (rowKey: string) =>
    (noteDrafts[rowKey] || '').trim() !== (noteOriginals[rowKey] || '').trim()

  const restoreNoteDraft = (rowKey: string) => {
    setNoteDrafts((current) => ({ ...current, [rowKey]: noteOriginals[rowKey] || '' }))
  }

  const saveNote = async (row: LatestMonthClientRow): Promise<boolean> => {
    const month = row.month || data.latest_month
    if (!month) {
      onNotify?.('当前月份为空，无法保存备注', 'error')
      return
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
      onNotify?.('备注已保存', 'success')
    } catch (error: unknown) {
      if (isApiHttpError(error) && error.status === 401) {
        onRequireAuth?.()
        return false
      }
      const nextError = error instanceof Error ? error.message : '保存备注失败'
      onNotify?.(nextError, 'error')
    } finally {
      setSavingNoteKey(null)
    }
  }

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
      <div className="table-wrapper latest-month-card">
        <div className="latest-month-toolbar">
          <div className="latest-month-toolbar-top">
            <div className="latest-month-title-block">
              <h3>账单明细</h3>
            </div>
          </div>
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
                    setIsClientDropdownOpen(true)
                    if (filteredClientNameOptions.length > 0) setHighlightedClientIndex(0)
                  }}
                  onChange={(event) => {
                    setClientNameQuery(event.target.value)
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
                        setIsClientDropdownOpen(true)
                        if (filteredClientNameOptions.length > 0) setHighlightedClientIndex(0)
                        return
                      }
                      if (filteredClientNameOptions.length === 0) return
                      setHighlightedClientIndex((current) =>
                        Math.min(current + 1, filteredClientNameOptions.length - 1),
                      )
                      return
                    }
                    if (event.key === 'ArrowUp') {
                      event.preventDefault()
                      if (!isClientDropdownOpen) {
                        setIsClientDropdownOpen(true)
                        if (filteredClientNameOptions.length > 0) {
                          setHighlightedClientIndex(filteredClientNameOptions.length - 1)
                        }
                        return
                      }
                      if (filteredClientNameOptions.length === 0) return
                      setHighlightedClientIndex((current) => Math.max(current - 1, 0))
                      return
                    }
                    if (event.key === 'Enter') {
                      if (!isClientDropdownOpen) return
                      event.preventDefault()
                      const option = filteredClientNameOptions[highlightedClientIndex]
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
                    setIsClientDropdownOpen((current) => {
                      const next = !current
                      if (next) {
                        setHighlightedClientIndex(filteredClientNameOptions.length > 0 ? 0 : -1)
                      } else {
                        setHighlightedClientIndex(-1)
                      }
                      return next
                    })
                  }}
                >
                  <span className="combobox-trigger-icon" aria-hidden="true" />
                </button>
                {isClientDropdownOpen && filteredClientNameOptions.length > 0 && (
                  <div className="combobox-list">
                    {filteredClientNameOptions.map((option, index) => (
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
            <label className="latest-month-filter-field" htmlFor="ledger-filter-bill-type">
              <span>账单类型</span>
              <div className={`combobox${isBillTypeDropdownOpen ? ' is-open' : ''}`} ref={billTypeComboboxRef}>
                <input
                  id="ledger-filter-bill-type"
                  className="combobox-input"
                  type="text"
                  placeholder="输入或选择账单类型"
                  value={billTypeQuery}
                  onFocus={() => {
                    setIsBillTypeDropdownOpen(true)
                    if (filteredBillTypeOptions.length > 0) setHighlightedBillTypeIndex(0)
                  }}
                  onChange={(event) => {
                    setBillTypeQuery(event.target.value)
                    setIsBillTypeDropdownOpen(true)
                    setHighlightedBillTypeIndex(0)
                  }}
                  onKeyDown={(event) => {
                    if (event.key === 'Escape') {
                      closeBillTypeDropdown()
                      return
                    }
                    if (event.key === 'ArrowDown') {
                      event.preventDefault()
                      if (!isBillTypeDropdownOpen) {
                        setIsBillTypeDropdownOpen(true)
                        if (filteredBillTypeOptions.length > 0) setHighlightedBillTypeIndex(0)
                        return
                      }
                      if (filteredBillTypeOptions.length === 0) return
                      setHighlightedBillTypeIndex((current) =>
                        Math.min(current + 1, filteredBillTypeOptions.length - 1),
                      )
                      return
                    }
                    if (event.key === 'ArrowUp') {
                      event.preventDefault()
                      if (!isBillTypeDropdownOpen) {
                        setIsBillTypeDropdownOpen(true)
                        if (filteredBillTypeOptions.length > 0) {
                          setHighlightedBillTypeIndex(filteredBillTypeOptions.length - 1)
                        }
                        return
                      }
                      if (filteredBillTypeOptions.length === 0) return
                      setHighlightedBillTypeIndex((current) => Math.max(current - 1, 0))
                      return
                    }
                    if (event.key === 'Enter') {
                      if (!isBillTypeDropdownOpen) return
                      event.preventDefault()
                      const option = filteredBillTypeOptions[highlightedBillTypeIndex]
                      if (option) selectBillTypeOption(option)
                    }
                  }}
                />
                <button
                  type="button"
                  className="combobox-trigger"
                  aria-label={isBillTypeDropdownOpen ? '收起账单类型筛选选项' : '展开账单类型筛选选项'}
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => {
                    setIsBillTypeDropdownOpen((current) => {
                      const next = !current
                      if (next) {
                        setHighlightedBillTypeIndex(filteredBillTypeOptions.length > 0 ? 0 : -1)
                      } else {
                        setHighlightedBillTypeIndex(-1)
                      }
                      return next
                    })
                  }}
                >
                  <span className="combobox-trigger-icon" aria-hidden="true" />
                </button>
                {isBillTypeDropdownOpen && filteredBillTypeOptions.length > 0 && (
                  <div className="combobox-list">
                    {filteredBillTypeOptions.map((option, index) => (
                      <button
                        key={option.value}
                        type="button"
                        className={`combobox-item${index === highlightedBillTypeIndex ? ' is-active' : ''}`}
                        onMouseEnter={() => setHighlightedBillTypeIndex(index)}
                        onClick={() => selectBillTypeOption(option)}
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
        ) : filteredRows.length === 0 ? (
          <EmptyState
            title={data.rows.length === 0 ? '暂无最新月份数据' : '没有匹配的筛选结果'}
            description={data.rows.length === 0 ? '请先完成月度计算后再查看账单明细。' : '请调整筛选条件后重试。'}
          />
        ) : (
          <div className="data-table-container latest-month-table-wrap">
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
                {filteredRows.map((row) => (
                  <tr
                    key={getRowKey(row, data.latest_month)}
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
                        const rowKey = getRowKey(row, data.latest_month)
                        const draftNote = noteDrafts[rowKey] ?? ''
                        const isSaving = savingNoteKey === rowKey
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
                                }}
                              />
                              <button
                                type="button"
                                className="ledger-note-save-btn"
                                disabled={isSaving}
                                onClick={() => void saveNote(row)}
                              >
                                {isSaving ? '保存中' : '保存'}
                              </button>
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
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  )
}
