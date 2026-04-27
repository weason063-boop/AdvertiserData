import { useEffect, useMemo, useState } from 'react'
import { RefreshCw } from 'lucide-react'
import type { Client, ContractChangeReview, SyncResult } from './billingTypes'
import styles from './ClientsPanel.module.css'

interface NewClientData {
  name: string
  business_type: string
  fee_clause: string
}

interface ClientsPanelProps {
  active: boolean
  syncResult: SyncResult | null
  loading: boolean
  search: string
  isAddingClient: boolean
  canClientWrite: boolean
  newClientData: NewClientData
  onNewClientDataChange: (patch: Partial<NewClientData>) => void
  onSaveNewClient: () => void
  onCancelAddClient: () => void
  clients: Client[]
  editingClient: Client | null
  editClause: string
  onEditClauseChange: (value: string) => void
  onSaveClause: () => void
  onCloseEdit: () => void
  onOpenEdit: (client: Client) => void
  contractChangeReviews: ContractChangeReview[]
  onApproveContractChangeReview: (reviewId: number, overrideNewFeeClause?: string) => void
  onIgnoreContractChangeReview: (reviewId: number) => void
  onBatchApproveContractChangeReviews: (
    reviewIds: number[],
    overrideNewFeeClauseByReviewId?: Record<number, string>,
  ) => void
}

const REVIEW_FIELD_LABELS: Record<string, string> = {
  department: '\u6267\u884c\u90e8\u95e8',
  business_type: '业务类型',
  entity: '主体',
  fee_clause: '服务费条款',
  payment_term: '账期',
}

const normalizeSearchText = (value: unknown): string =>
  String(value ?? '')
    .toLowerCase()
    .replace(/\s+/g, '')

const formatText = (value: string | null | undefined): string => {
  const text = String(value ?? '').trim()
  return text || '—'
}

const parseBackendDate = (value: string): Date | null => {
  const text = String(value || '').trim()
  if (!text) return null

  if (/[zZ]|[+-]\d{2}:\d{2}$/.test(text)) {
    const parsed = new Date(text)
    return Number.isNaN(parsed.getTime()) ? null : parsed
  }

  // Backend stores naive timestamps (SQLite CURRENT_TIMESTAMP) in UTC.
  const compactUtc = text.replace(' ', 'T')
  const utcCandidate = compactUtc.endsWith('Z') ? compactUtc : `${compactUtc}Z`
  const utcParsed = new Date(utcCandidate)
  if (!Number.isNaN(utcParsed.getTime())) {
    return utcParsed
  }

  const fallback = new Date(text)
  return Number.isNaN(fallback.getTime()) ? null : fallback
}

const formatDateTime = (value: string): string => {
  const date = parseBackendDate(value)
  if (!date) return value
  return date.toLocaleString('zh-CN', {
    hour12: false,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

const isNewClientReview = (review: ContractChangeReview): boolean =>
  ![
    review.current_business_type,
    review.current_department,
    review.current_entity,
    review.current_fee_clause,
    review.current_payment_term,
  ].some((value) => String(value ?? '').trim())

const getReviewFieldValues = (review: ContractChangeReview, fieldName: string) => {
  switch (fieldName) {
    case 'business_type':
      return {
        current: review.current_business_type,
        next: review.new_business_type,
      }
    case 'department':
      return {
        current: review.current_department,
        next: review.new_department,
      }
    case 'entity':
      return {
        current: review.current_entity,
        next: review.new_entity,
      }
    case 'fee_clause':
      return {
        current: review.current_fee_clause,
        next: review.new_fee_clause,
      }
    case 'payment_term':
      return {
        current: review.current_payment_term,
        next: review.new_payment_term,
      }
    default:
      return {
        current: null,
        next: null,
      }
  }
}

export function ClientsPanel({
  active,
  syncResult,
  loading,
  search,
  isAddingClient,
  canClientWrite,
  newClientData,
  onNewClientDataChange,
  onSaveNewClient,
  onCancelAddClient,
  clients,
  editingClient,
  editClause,
  onEditClauseChange,
  onSaveClause,
  onCloseEdit,
  onOpenEdit,
  contractChangeReviews,
  onApproveContractChangeReview,
  onIgnoreContractChangeReview,
  onBatchApproveContractChangeReviews,
}: ClientsPanelProps) {
  const [viewMode, setViewMode] = useState<'clients' | 'reviews'>('clients')
  const [selectedReviewIds, setSelectedReviewIds] = useState<number[]>([])
  const [editedFeeClauseByReviewId, setEditedFeeClauseByReviewId] = useState<Record<number, string>>({})
  const [editingFeeClauseReviewId, setEditingFeeClauseReviewId] = useState<number | null>(null)
  const [feeClauseEditorValue, setFeeClauseEditorValue] = useState('')
  const pendingCount = contractChangeReviews.length

  const latestNewClientNames = useMemo(
    () => new Set((syncResult?.new_clients || []).map((item) => String(item))),
    [syncResult],
  )

  const filteredReviews = useMemo(() => {
    const keyword = normalizeSearchText(search)
    if (!keyword) return contractChangeReviews
    return contractChangeReviews.filter((review) => {
      const reviewText = [
        review.client_name,
        ...(review.change_fields || []),
        review.current_business_type,
        review.new_business_type,
        review.current_department,
        review.new_department,
        review.current_entity,
        review.new_entity,
        review.current_fee_clause,
        review.new_fee_clause,
        review.current_payment_term,
        review.new_payment_term,
      ]
      return reviewText.some((value) => normalizeSearchText(value).includes(keyword))
    })
  }, [contractChangeReviews, search])

  useEffect(() => {
    const availableIds = new Set(contractChangeReviews.map((review) => review.id))
    setSelectedReviewIds((current) => current.filter((reviewId) => availableIds.has(reviewId)))
  }, [contractChangeReviews])

  useEffect(() => {
    setEditedFeeClauseByReviewId((current) => {
      const next: Record<number, string> = {}
      contractChangeReviews.forEach((review) => {
        next[review.id] = current[review.id] ?? review.new_fee_clause ?? ''
      })
      return next
    })
  }, [contractChangeReviews])

  useEffect(() => {
    if (viewMode === 'reviews' && contractChangeReviews.length === 0) {
      setViewMode('clients')
    }
  }, [contractChangeReviews.length, viewMode])

  const filteredReviewIds = filteredReviews.map((review) => review.id)
  const allFilteredSelected =
    filteredReviewIds.length > 0 && filteredReviewIds.every((reviewId) => selectedReviewIds.includes(reviewId))

  const reviewsById = useMemo(
    () => new Map(contractChangeReviews.map((review) => [review.id, review])),
    [contractChangeReviews],
  )

  const toggleReviewSelection = (reviewId: number) => {
    setSelectedReviewIds((current) =>
      current.includes(reviewId)
        ? current.filter((id) => id !== reviewId)
        : [...current, reviewId],
    )
  }

  const toggleAllFilteredReviews = () => {
    if (allFilteredSelected) {
      setSelectedReviewIds((current) => current.filter((id) => !filteredReviewIds.includes(id)))
      return
    }
    setSelectedReviewIds((current) => Array.from(new Set([...current, ...filteredReviewIds])))
  }

  const openReviewsPage = () => {
    if (pendingCount === 0) return
    setViewMode('reviews')
  }

  const openFeeClauseEditor = (review: ContractChangeReview) => {
    setEditingFeeClauseReviewId(review.id)
    setFeeClauseEditorValue(editedFeeClauseByReviewId[review.id] ?? review.new_fee_clause ?? '')
  }

  const closeFeeClauseEditor = () => {
    setEditingFeeClauseReviewId(null)
    setFeeClauseEditorValue('')
  }

  const saveFeeClauseEditor = () => {
    if (editingFeeClauseReviewId == null) return
    setEditedFeeClauseByReviewId((current) => ({
      ...current,
      [editingFeeClauseReviewId]: feeClauseEditorValue,
    }))
    closeFeeClauseEditor()
  }

  const buildFeeClauseOverrideByReviewIds = (reviewIds: number[]): Record<number, string> => {
    const overrides: Record<number, string> = {}
    reviewIds.forEach((reviewId) => {
      const review = reviewsById.get(reviewId)
      if (!review || !(review.change_fields || []).includes('fee_clause')) return

      const editedValue = editedFeeClauseByReviewId[reviewId] ?? ''
      const originalValue = review.new_fee_clause ?? ''
      if (editedValue !== originalValue) {
        overrides[reviewId] = editedValue
      }
    })
    return overrides
  }

  const handleBatchApproveClick = () => {
    if (selectedReviewIds.length === 0) return
    const overrides = buildFeeClauseOverrideByReviewIds(selectedReviewIds)
    onBatchApproveContractChangeReviews(
      selectedReviewIds,
      Object.keys(overrides).length > 0 ? overrides : undefined,
    )
  }

  if (!active) return null

  return (
    <div className={styles.tabContent}>
      {syncResult && (
        <div className={styles.syncStatusCard}>
          <div className={styles.syncStatusHeader}>
            <RefreshCw size={18} className="text-primary" />
            <h3>同步成功概览</h3>
            <span className={styles.syncTime}>{syncResult.time}</span>
          </div>
          <div className="sync-status-body">
            <div className={`${styles.syncStats} ${styles.syncStatsGrid}`}>
              <div className={styles.syncStatChip}>
                <span className={styles.syncStatLabel}>聚合客户</span>
                <span className={styles.syncStatValue}>{syncResult.client_count ?? syncResult.count}</span>
              </div>
              <div className={`${styles.syncStatChip} ${styles.syncStatChipNew}`}>
                <span className={styles.syncStatLabel}>新增客户</span>
                <span className={styles.syncStatValue}>{syncResult.new_client_count ?? 0}</span>
              </div>
              <div className={`${styles.syncStatChip} ${styles.syncStatChipPending}`}>
                <span className={styles.syncStatLabel}>待确认变更</span>
                <button
                  type="button"
                  className={`${styles.syncStatValue} ${styles.syncStatChipButton}`}
                  onClick={openReviewsPage}
                  disabled={pendingCount <= 0}
                >
                  {pendingCount}
                </button>
              </div>
              <div className={styles.syncStatChip}>
                <span className={styles.syncStatLabel}>未变化</span>
                <span className={styles.syncStatValue}>{syncResult.unchanged_count ?? 0}</span>
              </div>
            </div>
          </div>
        </div>
      )}

      {viewMode === 'reviews' && (
        <div className={`module-card ${styles.contractReviewCard}`}>
          <div className={styles.contractReviewHeader}>
            <div className={styles.contractReviewTitle}>
              <span className={styles.reviewKicker}>人工确认</span>
              <h3>待确认条款变更列表</h3>
            </div>
            <div className={styles.contractReviewNav}>
              {canClientWrite && (
                <button
                  className="btn-action secondary"
                  onClick={handleBatchApproveClick}
                  disabled={loading || selectedReviewIds.length === 0}
                >
                  批量确认
                </button>
              )}
              <button className="btn-action secondary" onClick={() => setViewMode('clients')}>
                返回客户条款管理
              </button>
            </div>
          </div>

          <div className={styles.contractReviewTableWrap}>
            <table className={`data-table ${styles.contractReviewTable}`}>
              <thead>
                <tr>
                  {canClientWrite && (
                    <th className={styles.reviewCheckCol}>
                      <input
                        type="checkbox"
                        checked={allFilteredSelected}
                        onChange={toggleAllFilteredReviews}
                        aria-label="勾选当前筛选范围内全部待确认条款"
                      />
                    </th>
                  )}
                  <th>客户名称</th>
                  <th>变化字段</th>
                  <th>原条款内容</th>
                  <th>更新条款内容</th>
                  <th>同步时间</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {filteredReviews.length === 0 && (
                  <tr>
                    <td colSpan={canClientWrite ? 7 : 6} className="loading">
                      当前筛选条件下暂无待确认条款
                    </td>
                  </tr>
                )}

                {filteredReviews.map((review) => {
                  const reviewIsNewClient = isNewClientReview(review)
                  const reviewItems = (review.change_fields || []).map((fieldName) => ({
                    fieldName,
                    label: REVIEW_FIELD_LABELS[fieldName] || fieldName,
                    values: getReviewFieldValues(review, fieldName),
                  }))

                  return (
                    <tr key={review.id}>
                      {canClientWrite && (
                        <td className={styles.reviewCheckCol}>
                          <input
                            type="checkbox"
                            checked={selectedReviewIds.includes(review.id)}
                            onChange={() => toggleReviewSelection(review.id)}
                            aria-label={`勾选 ${review.client_name}`}
                          />
                        </td>
                      )}
                      <td className="cell-name">
                        <div className={styles.clientNameCell}>
                          <span>{review.client_name}</span>
                          {reviewIsNewClient && (
                            <span className={styles.clientSyncBadge}>
                              {'\u65b0\u589e\u5f85\u786e\u8ba4'}
                            </span>
                          )}
                        </div>
                      </td>
                      <td className={styles.reviewFieldsCell}>
                        <div className={styles.reviewFieldTags}>
                          {reviewItems.map((item) => (
                            <span key={`${review.id}-${item.fieldName}`} className={styles.reviewFieldTag}>
                              {item.label}
                            </span>
                          ))}
                        </div>
                      </td>
                      <td className={styles.reviewDiffCell}>
                        {reviewItems.map((item) => (
                          <div key={`current-${review.id}-${item.fieldName}`} className={styles.reviewDiffItem}>
                            <span>{formatText(item.values.current)}</span>
                          </div>
                        ))}
                      </td>
                      <td className={styles.reviewDiffCell}>
                        {reviewItems.map((item) => (
                          <div
                            key={`next-${review.id}-${item.fieldName}`}
                            className={`${styles.reviewDiffItem} ${styles.reviewDiffItemNext}`}
                          >
                            {item.fieldName === 'fee_clause' && canClientWrite ? (
                              <div className={styles.reviewNextFeeClauseBlock}>
                                <div
                                  className={styles.reviewNextFeeClauseDisplay}
                                  title="服务费条款更新内容"
                                >
                                  {formatText(editedFeeClauseByReviewId[review.id] ?? review.new_fee_clause)}
                                </div>
                                <button
                                  type="button"
                                  className={`${styles.btnEdit} ${styles.reviewNextFeeClauseEditBtn}`}
                                  onClick={() => openFeeClauseEditor(review)}
                                >
                                  编辑
                                </button>
                              </div>
                            ) : (
                              <span>{formatText(item.values.next)}</span>
                            )}
                          </div>
                        ))}
                      </td>
                      <td className={styles.reviewTimeCell}>{formatDateTime(review.updated_at)}</td>
                      <td className="cell-action">
                        {canClientWrite ? (
                          <div className={`${styles.actionButtons} ${styles.reviewActionButtons}`}>
                            <button
                              className={styles.btnSave}
                              onClick={() =>
                                onApproveContractChangeReview(
                                  review.id,
                                  buildFeeClauseOverrideByReviewIds([review.id])[review.id],
                                )
                              }
                              disabled={loading}
                            >
                              确认
                            </button>
                            <button
                              className={styles.btnCancel}
                              onClick={() => onIgnoreContractChangeReview(review.id)}
                              disabled={loading}
                            >
                              忽略
                            </button>
                          </div>
                        ) : (
                          <span className={styles.reviewReadonlyTip}>仅可查看</span>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {viewMode === 'clients' && (
        <>
          {pendingCount > 0 && (
            <div className={styles.reviewEntryBanner}>
              <div className={styles.reviewEntryCopy}>
                <strong>当前有 {pendingCount} 条待确认条款变更</strong>
              </div>
              <button className="btn-action primary" onClick={openReviewsPage}>
                查看待确认变更
              </button>
            </div>
          )}

          <div className="module-card">
            <div className={`table-wrapper ${styles.clientsTableWrap}`}>
              <table className={`data-table ${styles.clientsTable}`}>
                <thead>
                  <tr>
                    <th>客户名称</th>
                    <th>主体</th>
                    <th>业务类型</th>
                    <th>账期</th>
                    <th>服务费条款</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {loading && (
                    <tr>
                      <td colSpan={6} className="loading">加载中...</td>
                    </tr>
                  )}

                  {!loading && isAddingClient && canClientWrite && (
                    <tr className={styles.editingRow}>
                      <td className="cell-name">
                        <input
                          className={styles.editClauseInput}
                          style={{ height: '36px' }}
                          value={newClientData.name}
                          onChange={(e) => onNewClientDataChange({ name: e.target.value })}
                          placeholder="请输入客户名称"
                          autoFocus
                        />
                      </td>
                      <td className="cell-entity">—</td>
                      <td className="cell-type">
                        <select
                          className={styles.editClauseInput}
                          style={{ height: '36px' }}
                          value={newClientData.business_type}
                          onChange={(e) => onNewClientDataChange({ business_type: e.target.value })}
                        >
                          <option value="">请选择业务类型</option>
                          <option value="广告代投">广告代投</option>
                          <option value="KOL">KOL</option>
                          <option value="代运营">代运营</option>
                          <option value="TTS">TTS</option>
                        </select>
                      </td>
                      <td className="cell-payment-term">—</td>
                      <td className="cell-clause">
                        <textarea
                          className={styles.editClauseInput}
                          value={newClientData.fee_clause}
                          onChange={(e) => onNewClientDataChange({ fee_clause: e.target.value })}
                          placeholder="请输入服务费条款..."
                        />
                      </td>
                      <td className="cell-action">
                        <div className={styles.actionButtons}>
                          <button className={styles.btnSave} onClick={onSaveNewClient} disabled={loading}>
                            保存
                          </button>
                          <button className={styles.btnCancel} onClick={onCancelAddClient}>
                            取消
                          </button>
                        </div>
                      </td>
                    </tr>
                  )}

                  {!loading && clients.length === 0 && (
                    <tr>
                      <td colSpan={6} className="loading">暂无客户条款数据</td>
                    </tr>
                  )}

                  {clients.map((client) => (
                    <tr key={client.id} className={editingClient?.id === client.id ? styles.editingRow : ''}>
                      <td className="cell-name">
                        <div className={styles.clientNameCell}>
                          <span>{client.name}</span>
                          {latestNewClientNames.has(client.name) && (
                            <span className={styles.clientSyncBadge}>本次同步新增</span>
                          )}
                        </div>
                      </td>
                      <td className="cell-entity">{client.entity || '—'}</td>
                      <td className="cell-type">{client.business_type || '—'}</td>
                      <td className="cell-payment-term">{client.payment_term || '—'}</td>
                      <td className="cell-clause">
                        {editingClient?.id === client.id ? (
                          <textarea
                            className={styles.editClauseInput}
                            value={editClause}
                            onChange={(e) => onEditClauseChange(e.target.value)}
                            placeholder="请输入服务费条款..."
                            autoFocus
                          />
                        ) : (
                          client.fee_clause || '—'
                        )}
                      </td>
                      <td className="cell-action">
                        {editingClient?.id === client.id ? (
                          <div className={styles.actionButtons}>
                            <button className={styles.btnSave} onClick={onSaveClause} disabled={loading}>
                              保存
                            </button>
                            <button className={styles.btnCancel} onClick={onCloseEdit}>
                              取消
                            </button>
                          </div>
                        ) : (
                          canClientWrite ? (
                            <button className={styles.btnEdit} onClick={() => onOpenEdit(client)}>
                              编辑
                            </button>
                          ) : (
                            <span>-</span>
                          )
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {canClientWrite && editingFeeClauseReviewId !== null && (
        <div className={styles.reviewClauseEditorOverlay} onClick={closeFeeClauseEditor}>
          <div className={styles.reviewClauseEditorModal} onClick={(event) => event.stopPropagation()}>
            <div className={styles.reviewClauseEditorHeader}>
              <h3>编辑服务费条款</h3>
              <button
                type="button"
                className={styles.reviewClauseEditorClose}
                onClick={closeFeeClauseEditor}
                aria-label="关闭编辑对话框"
              >
                ×
              </button>
            </div>
            <textarea
              className={styles.reviewClauseEditorTextarea}
              value={feeClauseEditorValue}
              onChange={(event) => setFeeClauseEditorValue(event.target.value)}
              rows={8}
              autoFocus
            />
            <div className={styles.reviewClauseEditorActions}>
              <button type="button" className="btn-action secondary" onClick={closeFeeClauseEditor}>
                取消
              </button>
              <button type="button" className="btn-action primary" onClick={saveFeeClauseEditor}>
                保存修改
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
