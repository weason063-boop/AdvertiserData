import type { OperationAuditLog } from './billingTypes'

const ACTION_LABELS: Record<string, string> = {
  upload_consumption: '上传消耗',
  calculate: '计算',
  recalculate: '重新计算',
  download_result: '下载结果',
  upload_contract: '上传合同',
  sync_snapshot: '同步快照',
  upsert_snapshot: '手工补录快照',
  upsert_daily_snapshot: '更新日汇率',
  export_report: '导出看板报表',
}

const ACTION_OPTIONS = [
  { value: 'all', label: '全部动作' },
  { value: 'upload_consumption', label: '上传消耗' },
  { value: 'calculate', label: '计算' },
  { value: 'recalculate', label: '重新计算' },
  { value: 'download_result', label: '下载结果' },
  { value: 'upload_contract', label: '上传合同' },
  { value: 'sync_snapshot', label: '同步快照' },
  { value: 'upsert_snapshot', label: '手工补录快照' },
  { value: 'upsert_daily_snapshot', label: '更新日汇率' },
  { value: 'export_report', label: '导出看板报表' },
]

const STATUS_OPTIONS = [
  { value: 'all', label: '全部状态' },
  { value: 'success', label: '成功' },
  { value: 'failed', label: '失败' },
]

const DAYS_OPTIONS = [
  { value: 'all', label: '全部时间' },
  { value: '1', label: '最近 1 天' },
  { value: '7', label: '最近 7 天' },
  { value: '30', label: '最近 30 天' },
  { value: '90', label: '最近 90 天' },
]

interface TaskHistoryPanelProps {
  active: boolean
  items: OperationAuditLog[]
  loading: boolean
  limit: number
  actorFilter: string
  actionFilter: string
  statusFilter: string
  daysFilter: string
  onLimitChange: (next: number) => void
  onActorFilterChange: (next: string) => void
  onActionFilterChange: (next: string) => void
  onStatusFilterChange: (next: string) => void
  onDaysFilterChange: (next: string) => void
  onToggleFailedOnly: () => void
  onRefresh: () => void
  onExport: () => void
}

const summarizeFile = (value?: string | null): string => {
  if (!value) return '—'
  const parts = value.split(/[\\/]/).filter(Boolean)
  return parts.length ? String(parts[parts.length - 1]) : value
}

const toStatusClassName = (status: string): string => {
  const normalized = status.toLowerCase()
  if (normalized === 'success') return 'success'
  if (normalized === 'failed') return 'failed'
  return 'unknown'
}

const normalizeDateTime = (value: string): string => {
  if (!value) return '—'
  let candidate = value.includes('T') ? value : value.replace(' ', 'T')
  
  // 后端返回的通常是无时区信息的 UTC 时间，如 2026-03-26T07:21:12
  // 如果没有明确的时区标识 (Z, +, 后半部分的 -)，给它补上 Z 当作 UTC 处理
  const tIndex = candidate.indexOf('T')
  if (!candidate.endsWith('Z') && candidate.indexOf('+') === -1 && (tIndex === -1 || candidate.indexOf('-', tIndex) === -1)) {
    candidate += 'Z'
  }

  const date = new Date(candidate)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', { hour12: false })
}

export function TaskHistoryPanel({
  active,
  items,
  loading,
  limit,
  actorFilter,
  actionFilter,
  statusFilter,
  daysFilter,
  onLimitChange,
  onActorFilterChange,
  onActionFilterChange,
  onStatusFilterChange,
  onDaysFilterChange,
  onToggleFailedOnly,
  onRefresh,
  onExport,
}: TaskHistoryPanelProps) {
  if (!active) return null

  return (
    <div className="task-history-card">
      <div className="task-history-toolbar">
        <div className="task-history-title-block">
          <h3>任务历史</h3>
          <p>用于排查谁在什么时间执行了什么动作</p>
        </div>
        <div className="task-history-meta">{loading ? '加载中...' : `已加载 ${items.length} 条`}</div>
      </div>

      <div className="task-history-controls">
        <div className="task-history-filters">
          <label className="task-history-field task-history-input">
            <span className="task-history-field-label">操作人</span>
            <input
              type="text"
              value={actorFilter}
              onChange={(e) => onActorFilterChange(e.target.value)}
              placeholder="输入账号关键词"
            />
          </label>

          <label className="task-history-field task-history-select">
            <span className="task-history-field-label">动作</span>
            <select value={actionFilter} onChange={(e) => onActionFilterChange(e.target.value)}>
              {ACTION_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          <label className="task-history-field task-history-select">
            <span className="task-history-field-label">状态</span>
            <select value={statusFilter} onChange={(e) => onStatusFilterChange(e.target.value)}>
              {STATUS_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          <label className="task-history-field task-history-select">
            <span className="task-history-field-label">时间</span>
            <select value={daysFilter} onChange={(e) => onDaysFilterChange(e.target.value)}>
              {DAYS_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          <label className="task-history-field task-history-select">
            <span className="task-history-field-label">条数</span>
            <select value={limit} onChange={(e) => onLimitChange(Number(e.target.value))}>
              <option value={50}>50</option>
              <option value={100}>100</option>
              <option value={200}>200</option>
              <option value={500}>500</option>
            </select>
          </label>
        </div>

        <div className="task-history-actions">
          <button type="button" className="pager-btn" onClick={onRefresh} disabled={loading}>
            {loading ? '刷新中...' : '刷新'}
          </button>
          <button
            type="button"
            className={`pager-btn ${statusFilter === 'failed' ? 'active' : ''}`}
            onClick={onToggleFailedOnly}
            disabled={loading}
          >
            仅看失败
          </button>
          <button type="button" className="pager-btn" onClick={onExport} disabled={loading}>
            导出 CSV
          </button>
        </div>
      </div>

      {items.length === 0 ? (
        <div className="task-history-empty">
          {loading ? '正在加载任务历史...' : '暂无任务历史记录'}
        </div>
      ) : (
        <div className="task-history-table-wrap">
          <table className="data-table task-history-table">
            <thead>
              <tr>
                <th className="col-time">时间</th>
                <th className="col-action">动作</th>
                <th className="col-status">状态</th>
                <th className="col-actor">操作人</th>
                <th className="col-input">输入文件</th>
                <th className="col-output">输出文件</th>
                <th className="col-error">错误信息</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id}>
                  <td className="col-time">{normalizeDateTime(item.created_at)}</td>
                  <td className="col-action">{ACTION_LABELS[item.action] || item.action}</td>
                  <td className="col-status">
                    <span className={`task-history-status ${toStatusClassName(item.status)}`}>
                      {item.status || 'unknown'}
                    </span>
                  </td>
                  <td className="col-actor" title={item.actor || 'system'}>{item.actor || 'system'}</td>
                  <td className="col-input" title={summarizeFile(item.input_file)}>{summarizeFile(item.input_file)}</td>
                  <td className="col-output" title={summarizeFile(item.output_file)}>{summarizeFile(item.output_file)}</td>
                  <td className="col-error" title={item.error_message || '—'}>{item.error_message || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
