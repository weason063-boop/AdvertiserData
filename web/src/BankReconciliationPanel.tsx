import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Download, FileSpreadsheet, Link2, RefreshCcw, Search, UploadCloud } from 'lucide-react'
import { apiBlob, apiJson, parseDownloadFilename } from './apiClient'
import type {
  BankReconciliationBatch,
  BankReconciliationBatchListResponse,
  BankReconciliationEntry,
  BankReconciliationRow,
} from './billingTypes'

type SourceView = 'bank' | 'ledger'
type ResultFilter = 'unmatched' | 'matched' | 'duplicate' | 'all'
type SideFilter = 'all' | 'debit' | 'credit'

interface BankReconciliationPanelProps {
  active: boolean
  canRun: boolean
  onNotify: (message: string, type: 'info' | 'success' | 'error') => void
  onRequireAuth: () => void
}

interface SourceDisplayRow {
  key: string
  status: BankReconciliationRow['status']
  status_label: string
  direction_label: string
  entry: BankReconciliationEntry
  counterpart?: BankReconciliationEntry | null
}

const statusClass: Record<BankReconciliationRow['status'], string> = {
  matched: 'matched',
  bank_unmatched: 'bank',
  ledger_unmatched: 'ledger',
  duplicate_pending: 'duplicate',
}

const sourceTitle: Record<SourceView, string> = {
  bank: '银行流水',
  ledger: '会计明细账',
}

const sideLabel: Record<BankReconciliationEntry['side'], string> = {
  debit: '借方',
  credit: '贷方',
}

const formatAmount = (value: number | string | null | undefined): string => {
  const numeric = Number(value || 0)
  return numeric.toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

const unmatchedStatusFor = (sourceView: SourceView): BankReconciliationRow['status'] =>
  sourceView === 'bank' ? 'bank_unmatched' : 'ledger_unmatched'

const makeSourceRows = (
  rows: BankReconciliationRow[],
  sourceView: SourceView,
): SourceDisplayRow[] => rows.flatMap((row, index) => {
  const entry = sourceView === 'bank' ? row.bank : row.ledger
  if (!entry) return []
  const counterpart = sourceView === 'bank' ? row.ledger : row.bank
  return [{
    key: `${sourceView}-${entry.source_id || index}-${row.status}-${index}`,
    status: row.status,
    status_label: row.status_label,
    direction_label: row.direction_label,
    entry,
    counterpart,
  }]
})

const matchesSourceSearch = (row: SourceDisplayRow, keyword: string): boolean => {
  const token = keyword.trim().toLowerCase()
  if (!token) return true
  return [
    row.status_label,
    row.direction_label,
    row.entry.date,
    row.entry.debit,
    row.entry.credit,
    row.entry.summary,
    row.entry.ref_no,
    row.entry.account,
    row.entry.currency,
    row.counterpart?.summary,
    row.counterpart?.ref_no,
    row.counterpart?.account,
  ].some((value) => String(value ?? '').toLowerCase().includes(token))
}

const filterSourceRows = (
  rows: SourceDisplayRow[],
  sourceView: SourceView,
  resultFilter: ResultFilter,
  sideFilter: SideFilter,
  search: string,
): SourceDisplayRow[] => {
  const unmatchedStatus = unmatchedStatusFor(sourceView)
  return rows.filter((row) => {
    if (resultFilter === 'matched' && row.status !== 'matched') return false
    if (resultFilter === 'unmatched' && row.status !== unmatchedStatus) return false
    if (resultFilter === 'duplicate' && row.status !== 'duplicate_pending') return false
    if (sideFilter !== 'all' && row.entry.side !== sideFilter) return false
    return matchesSourceSearch(row, search)
  })
}

const sourceCounts = (rows: SourceDisplayRow[], sourceView: SourceView) => {
  const unmatchedStatus = unmatchedStatusFor(sourceView)
  return {
    all: rows.length,
    matched: rows.filter((row) => row.status === 'matched').length,
    unmatched: rows.filter((row) => row.status === unmatchedStatus).length,
    duplicate: rows.filter((row) => row.status === 'duplicate_pending').length,
  }
}

interface SourceTableProps {
  title: string
  rows: SourceDisplayRow[]
  sourceView: SourceView
  selectedSourceId: string
  onSelect: (sourceId: string | null) => void
}

function SourceTable({ title, rows, sourceView, selectedSourceId, onSelect }: SourceTableProps) {
  const [resultFilter, setResultFilter] = useState<ResultFilter>('unmatched')
  const [sideFilter, setSideFilter] = useState<SideFilter>('all')
  const [search, setSearch] = useState('')

  const counts = useMemo(() => sourceCounts(rows, sourceView), [rows, sourceView])
  const filteredRows = useMemo(
    () => filterSourceRows(rows, sourceView, resultFilter, sideFilter, search),
    [rows, sourceView, resultFilter, sideFilter, search]
  )

  const unmatchedTotal = counts.unmatched
  const matchedTotal = counts.matched
  const duplicateTotal = counts.duplicate
  const allTotal = counts.all
  return (
    <section className="bank-recon-source-panel">
      <div className="bank-recon-source-head" style={{ flexDirection: 'column', alignItems: 'stretch', gap: '12px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h4 style={{ margin: 0 }}>{title} <span style={{ fontSize: '12px', color: '#64748b', fontWeight: 'normal', marginLeft: '8px' }}>{filteredRows.length} / {counts.all}</span></h4>
          <div className="bank-recon-side-group" style={{ margin: 0 }}>
             <button className={sideFilter === 'all' ? 'active' : ''} onClick={() => setSideFilter('all')}>全部</button>
             <button className={sideFilter === 'debit' ? 'active' : ''} onClick={() => setSideFilter('debit')}>借方</button>
             <button className={sideFilter === 'credit' ? 'active' : ''} onClick={() => setSideFilter('credit')}>贷方</button>
          </div>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: '#f8fafc', padding: '6px 12px', borderRadius: '6px', border: '1px solid #e2e8f0' }}>
           <div className="bank-recon-segment-group" style={{ margin: 0, gap: '4px' }}>
             <button className={resultFilter === 'unmatched' ? 'active' : ''} onClick={() => setResultFilter('unmatched')}>
               <span>未匹配</span><b>{unmatchedTotal}</b>
             </button>
             <button className={resultFilter === 'matched' ? 'active' : ''} onClick={() => setResultFilter('matched')}>
               <span>已匹配</span><b>{matchedTotal}</b>
             </button>
             <button className={resultFilter === 'duplicate' ? 'active' : ''} onClick={() => setResultFilter('duplicate')}>
               <span>重复</span><b>{duplicateTotal}</b>
             </button>
             <button className={resultFilter === 'all' ? 'active' : ''} onClick={() => setResultFilter('all')}>
               <span>全部</span><b>{allTotal}</b>
             </button>
           </div>
           <div className="bank-recon-search" style={{ margin: 0, width: '220px', background: 'white' }}>
             <Search size={14} />
             <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜索摘要、账号..." />
           </div>
        </div>
      </div>
      <div className="data-table-container bank-recon-table-wrap">
        <table className="data-table bank-recon-table">
          <thead>
            <tr>
              <th className="bank-recon-check-col">选择</th>
              <th>状态</th>
              <th>借贷方</th>
              <th>日期</th>
              <th>借方金额</th>
              <th>贷方金额</th>
              <th>摘要</th>
              <th>编号</th>
              <th>匹配对方</th>
            </tr>
          </thead>
          <tbody>
            {filteredRows.map((row) => {
              const sourceId = row.entry.source_id || ''
              const selectable = row.status !== 'matched' && Boolean(sourceId)
              const checked = Boolean(sourceId && selectedSourceId === sourceId)
              return (
              <tr key={row.key} className={checked ? 'is-selected' : undefined}>
                <td className="bank-recon-check-cell">
                  <label className="bank-recon-check">
                    <input
                      type="checkbox"
                      checked={checked}
                      disabled={!selectable}
                      onChange={(event) => onSelect(event.target.checked ? sourceId : null)}
                    />
                    <span />
                  </label>
                </td>
                <td><span className={`bank-recon-status ${statusClass[row.status]}`}>{row.status_label}</span></td>
                <td>{sideLabel[row.entry.side]}</td>
                <td>{row.entry.date}</td>
                <td className="numeric">{row.entry.debit ? formatAmount(row.entry.debit) : '-'}</td>
                <td className="numeric">{row.entry.credit ? formatAmount(row.entry.credit) : '-'}</td>
                <td>
                  <div className="bank-recon-cell-main">{row.entry.summary || '-'}</div>
                  <div className="bank-recon-cell-sub">{row.entry.account || row.entry.currency || ''}</div>
                </td>
                <td>{row.entry.ref_no || '-'}</td>
                <td>
                  <div className="bank-recon-cell-main">{row.counterpart?.summary || '-'}</div>
                  <div className="bank-recon-cell-sub">{row.counterpart?.ref_no || row.counterpart?.account || ''}</div>
                </td>
              </tr>
              )
            })}
            {!filteredRows.length && (
              <tr>
                <td colSpan={9} className="bank-recon-empty-row">
                  <FileSpreadsheet size={18} />
                  暂无数据
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  )
}

export function BankReconciliationPanel({
  active,
  canRun,
  onNotify,
  onRequireAuth,
}: BankReconciliationPanelProps) {
  const [selectedBatch, setSelectedBatch] = useState<BankReconciliationBatch | null>(null)
  const [month, setMonth] = useState(() => new Date().toISOString().substring(0, 7))
  const [company, setCompany] = useState('')
  const [companyOptions, setCompanyOptions] = useState<string[]>([])
  const [bankFile, setBankFile] = useState<File | null>(null)
  const [ledgerFile, setLedgerFile] = useState<File | null>(null)
  const [loading, setLoading] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [downloading, setDownloading] = useState(false)
  const [manualMatching, setManualMatching] = useState(false)
  const [selectedBankSourceId, setSelectedBankSourceId] = useState('')
  const [selectedLedgerSourceId, setSelectedLedgerSourceId] = useState('')
  const initialLoadRef = useRef(false)

  const rawRows = useMemo(() => selectedBatch?.rows ?? [], [selectedBatch?.rows])
  const bankRows = useMemo(() => makeSourceRows(rawRows, 'bank'), [rawRows])
  const ledgerRows = useMemo(() => makeSourceRows(rawRows, 'ledger'), [rawRows])
  const selectedBankRow = useMemo(
    () => bankRows.find((row) => row.entry.source_id === selectedBankSourceId) ?? null,
    [bankRows, selectedBankSourceId],
  )
  const selectedLedgerRow = useMemo(
    () => ledgerRows.find((row) => row.entry.source_id === selectedLedgerSourceId) ?? null,
    [ledgerRows, selectedLedgerSourceId],
  )

  const loadBatchDetail = useCallback(async (batchId: number) => {
    setLoading(true)
    try {
      const { data } = await apiJson<BankReconciliationBatch>(`/api/bank-reconciliation/batches/${batchId}`)
      setSelectedBatch(data)
      setSelectedBankSourceId('')
      setSelectedLedgerSourceId('')
    } catch (error) {
      if (String(error).includes('401')) {
        onRequireAuth()
      }
      onNotify(error instanceof Error ? error.message : '银行对账详情加载失败', 'error')
    } finally {
      setLoading(false)
    }
  }, [onNotify, onRequireAuth])

  const loadBatchForPeriod = useCallback(async (targetMonth: string, targetCompany: string) => {
    if (!canRun) return
    setLoading(true)
    try {
      const params = new URLSearchParams({ limit: '1' })
      if (targetMonth) params.append('month', targetMonth)
      if (targetCompany) params.append('company', targetCompany)
      const { data } = await apiJson<BankReconciliationBatchListResponse>(`/api/bank-reconciliation/batches?${params.toString()}`)
      const latest = data.rows?.[0]
      if (latest) {
        await loadBatchDetail(latest.id)
      } else {
        setSelectedBatch(null)
      }
    } catch (error) {
      if (String(error).includes('401')) {
        onRequireAuth()
      }
      onNotify(error instanceof Error ? error.message : '银行对账结果加载失败', 'error')
    } finally {
      setLoading(false)
    }
  }, [canRun, loadBatchDetail, onNotify, onRequireAuth])

  const loadCompanies = useCallback(async () => {
    try {
      const { data } = await apiJson<{ companies: string[] }>('/api/bank-reconciliation/companies')
      setCompanyOptions(data.companies || [])
      if (data.companies?.length && !company) {
        setCompany(data.companies[0])
      }
    } catch (error) {
      console.error('Failed to load companies', error)
    }
  }, [company])

  useEffect(() => {
    if (!active || !canRun) {
      initialLoadRef.current = false
      return
    }
    if (initialLoadRef.current) return
    initialLoadRef.current = true
    void loadCompanies().then(() => {
      // The subsequent effect will trigger loadBatchForPeriod once company is set
    })
  }, [active, canRun, loadCompanies])

  // When month or company changes, fetch the batch for that period
  useEffect(() => {
    if (active && canRun && initialLoadRef.current) {
      void loadBatchForPeriod(month, company)
    }
  }, [month, company, active, canRun, loadBatchForPeriod])

  if (!active) return null

  const handleSubmit = async () => {
    if (!canRun) {
      onRequireAuth()
      return
    }
    if (!bankFile || !ledgerFile) {
      onNotify('请同时选择银行流水和会计银行明细账', 'error')
      return
    }

    const formData = new FormData()
    if (month) formData.append('month', month)
    if (company) formData.append('company', company)
    formData.append('bank_file', bankFile)
    formData.append('ledger_file', ledgerFile)
    setSubmitting(true)
    try {
      const { data } = await apiJson<BankReconciliationBatch>('/api/bank-reconciliation/reconcile', {
        method: 'POST',
        body: formData,
      })
      setSelectedBatch(data)
      setBankFile(null)
      setLedgerFile(null)
      setSelectedBankSourceId('')
      setSelectedLedgerSourceId('')
      onNotify('银行对账完成', 'success')
    } catch (error) {
      if (String(error).includes('401')) {
        onRequireAuth()
      }
      onNotify(error instanceof Error ? error.message : '银行对账失败', 'error')
    } finally {
      setSubmitting(false)
    }
  }

  const handleDownload = async () => {
    if (!selectedBatch) return
    setDownloading(true)
    try {
      const { blob, res } = await apiBlob(`/api/bank-reconciliation/batches/${selectedBatch.id}/download`)
      const filename = parseDownloadFilename(res.headers.get('content-disposition'), `银行对账结果_${selectedBatch.month}.xlsx`)
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = filename
      document.body.appendChild(anchor)
      anchor.click()
      anchor.remove()
      URL.revokeObjectURL(url)
    } catch (error) {
      onNotify(error instanceof Error ? error.message : '银行对账结果下载失败', 'error')
    } finally {
      setDownloading(false)
    }
  }

  const handleManualMatch = async () => {
    if (!selectedBatch) return
    if (!canRun) {
      onRequireAuth()
      return
    }
    if (!selectedBankRow || !selectedLedgerRow) {
      onNotify('请选择一条银行流水和一条会计明细', 'error')
      return
    }
    if (selectedBankRow.entry.amount !== selectedLedgerRow.entry.amount) {
      onNotify('人工匹配要求两边金额一致', 'error')
      return
    }
    if (selectedBankRow.entry.side === selectedLedgerRow.entry.side) {
      onNotify('人工匹配要求银行与会计借贷方向相反', 'error')
      return
    }

    setManualMatching(true)
    try {
      const { data } = await apiJson<BankReconciliationBatch>(
        `/api/bank-reconciliation/batches/${selectedBatch.id}/manual-match`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            bank_source_id: selectedBankRow.entry.source_id,
            ledger_source_id: selectedLedgerRow.entry.source_id,
          }),
        },
      )
      setSelectedBatch(data)
      setSelectedBankSourceId('')
      setSelectedLedgerSourceId('')
      onNotify('人工匹配已保存', 'success')
    } catch (error) {
      if (String(error).includes('401')) {
        onRequireAuth()
      }
      onNotify(error instanceof Error ? error.message : '人工匹配失败', 'error')
    } finally {
      setManualMatching(false)
    }
  }

  const summary = selectedBatch?.summary

  return (
    <div className="bank-recon-page">
      <div className="chart-card bank-recon-upload-card" style={{ paddingBottom: '16px' }}>
        <div className="dashboard-card-header bank-recon-card-head" style={{ borderBottom: 'none', paddingBottom: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '20px', flexWrap: 'wrap' }}>
            <h3 style={{ margin: 0 }}>银行对账</h3>
            
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', background: '#f8fafc', padding: '6px 12px', borderRadius: '6px', border: '1px solid #e2e8f0' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px', margin: 0 }}>
                <span style={{ color: '#64748b', fontWeight: 500 }}>对账月份</span>
                <input type="month" value={month} onChange={(event) => setMonth(event.target.value)} style={{ padding: '4px 8px', border: '1px solid #cbd5e1', borderRadius: '4px', background: 'white' }} />
              </label>
              <div style={{ width: '1px', height: '16px', background: '#cbd5e1' }} />
              <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px', margin: 0 }}>
                <span style={{ color: '#64748b', fontWeight: 500 }}>公司主体</span>
                <select 
                  value={company} 
                  onChange={(event) => setCompany(event.target.value)} 
                  style={{ padding: '4px 8px', border: '1px solid #cbd5e1', borderRadius: '4px', background: 'white', width: '140px', cursor: 'pointer' }}
                >
                  <option value="" disabled>请选择主体</option>
                  {companyOptions.map((opt) => (
                    <option key={opt} value={opt}>{opt}</option>
                  ))}
                </select>
              </label>
              <div style={{ width: '1px', height: '16px', background: '#cbd5e1' }} />
              <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px', margin: 0, cursor: 'pointer' }}>
                <span style={{ color: '#64748b', fontWeight: 500 }}>银行流水</span>
                <div style={{ position: 'relative', overflow: 'hidden' }}>
                  <button className="btn-action secondary" style={{ pointerEvents: 'none', padding: '4px 8px', fontSize: '12px', minWidth: '80px', justifyContent: 'flex-start' }}>
                    <FileSpreadsheet size={14} />
                    <span style={{ maxWidth: '120px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{bankFile?.name || '选择文件'}</span>
                  </button>
                  <input type="file" accept=".xlsx,.xls,.csv" onChange={(event) => setBankFile(event.target.files?.[0] ?? null)} style={{ position: 'absolute', left: 0, top: 0, opacity: 0, cursor: 'pointer', height: '100%', width: '100%' }} />
                </div>
              </label>
              <div style={{ width: '1px', height: '16px', background: '#cbd5e1' }} />
              <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px', margin: 0, cursor: 'pointer' }}>
                <span style={{ color: '#64748b', fontWeight: 500 }}>明细账</span>
                <div style={{ position: 'relative', overflow: 'hidden' }}>
                  <button className="btn-action secondary" style={{ pointerEvents: 'none', padding: '4px 8px', fontSize: '12px', minWidth: '80px', justifyContent: 'flex-start' }}>
                    <FileSpreadsheet size={14} />
                    <span style={{ maxWidth: '120px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{ledgerFile?.name || '选择文件'}</span>
                  </button>
                  <input type="file" accept=".xlsx,.xls,.csv" onChange={(event) => setLedgerFile(event.target.files?.[0] ?? null)} style={{ position: 'absolute', left: 0, top: 0, opacity: 0, cursor: 'pointer', height: '100%', width: '100%' }} />
                </div>
              </label>
            </div>
          </div>

          <div className="bank-recon-actions">
            <button className="btn-action secondary" onClick={() => void loadBatchForPeriod(month, company)} disabled={loading || !canRun}>
              <RefreshCcw size={16} />
              刷新
            </button>
            <button className="btn-action primary" onClick={handleSubmit} disabled={submitting || !canRun}>
              <UploadCloud size={16} />
              {submitting ? '对账中' : '开始对账'}
            </button>
          </div>
        </div>
      </div>

      {summary && selectedBatch ? (
        <>

          <div className="chart-card bank-recon-result-card">
            <div className="dashboard-card-header bank-recon-card-head" style={{ paddingBottom: '16px' }}>
              <div>
                <h3>对账结果</h3>
                <p>{selectedBatch.bank_filename} / {selectedBatch.ledger_filename}</p>
              </div>
              <div className="bank-recon-actions">
                <button className="btn-action secondary" onClick={handleDownload} disabled={downloading}>
                  <Download size={16} />
                  {downloading ? '下载中' : '下载结果'}
                </button>
                <button 
                  className="btn-action primary" 
                  onClick={handleManualMatch} 
                  disabled={manualMatching || !selectedBankSourceId || !selectedLedgerSourceId}
                >
                  <Link2 size={16} />
                  手工匹配
                </button>
              </div>
            </div>

            <div className="bank-recon-split-grid" style={{ gap: '20px' }}>
              <SourceTable 
                title={sourceTitle.bank} 
                rows={bankRows} 
                sourceView="bank"
                selectedSourceId={selectedBankSourceId}
                onSelect={(id) => setSelectedBankSourceId(id ?? '')}
              />
              <SourceTable 
                title={sourceTitle.ledger} 
                rows={ledgerRows} 
                sourceView="ledger"
                selectedSourceId={selectedLedgerSourceId}
                onSelect={(id) => setSelectedLedgerSourceId(id ?? '')}
              />
            </div>
          </div>
        </>
      ) : (
        <div className="chart-card bank-recon-placeholder">
          <FileSpreadsheet size={28} />
          <span>{canRun ? '上传当月银行流水和会计银行明细账后生成对账结果' : '当前账号没有银行对账权限'}</span>
        </div>
      )}
    </div>
  )
}
