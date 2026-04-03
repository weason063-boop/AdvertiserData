import type { CalculationResult, ResultRow } from './billingTypes'

interface ResultsPanelProps {
  active: boolean
  results: CalculationResult | null
  pagedResultsData: ResultRow[]
  resultsTotalRows: number
  resultsPage: number
  resultsTotalPages: number
  resultsPageSize: number
  onPageSizeChange: (size: number) => void
  onPrevPage: () => void
  onNextPage: () => void
  formatNumber: (value: string | number) => string
}

export function ResultsPanel({
  active,
  results,
  pagedResultsData,
  resultsTotalRows,
  resultsPage,
  resultsTotalPages,
  resultsPageSize,
  onPageSizeChange,
  onPrevPage,
  onNextPage,
  formatNumber,
}: ResultsPanelProps) {
  if (!active) return null

  if (!results) {
    return (
      <div className="empty">
        <div className="empty-icon">📄</div>
        <p>上传消耗数据后，计算结果将显示在这里</p>
      </div>
    )
  }

  return (
    <div className="module-card">
      <div className="table-wrapper results-wrapper">
        <div className="results-toolbar">
        <div className="results-meta">
          共 {resultsTotalRows} 条，当前第 {resultsPage}/{resultsTotalPages} 页
        </div>
        <div className="results-pager">
          <label className="results-page-size">
            每页
            <select
              value={resultsPageSize}
              onChange={(e) => {
                onPageSizeChange(Number(e.target.value))
              }}
            >
              <option value={100}>100</option>
              <option value={200}>200</option>
              <option value={500}>500</option>
            </select>
          </label>
          <button
            type="button"
            className="pager-btn"
            onClick={onPrevPage}
            disabled={resultsPage <= 1}
          >
            上一页
          </button>
          <button
            type="button"
            className="pager-btn"
            onClick={onNextPage}
            disabled={resultsPage >= resultsTotalPages}
          >
            下一页
          </button>
        </div>
      </div>
      <div className="data-table-container">
        <table className="data-table">
          <thead>
            <tr>
              {results.columns.map(col => (
                <th key={col}>{col}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {pagedResultsData.map((row, idx) => (
              <tr key={`${(resultsPage - 1) * resultsPageSize + idx}`}>
                {results.columns.map(col => (
                  <td key={col}>
                    {['代投消耗', '流水消耗', '服务费', '固定服务费', 'Summary'].includes(col)
                      ? formatNumber(row[col])
                      : (row[col] || '—')
                    }
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      </div>
    </div>
  )
}
