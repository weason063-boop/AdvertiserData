import { useEffect, useState } from 'react'
import { HandCoins, RefreshCw, Save, TrendingUp } from 'lucide-react'
import { apiJson } from './apiClient'

interface Rate {
  currency: string
  middle_rate?: number | null
  tt_buy?: string | null
  tt_sell?: string | null
  notes_buy?: string | null
  notes_sell?: string | null
  source?: string | null
  code?: string | null
  pub_time: string
}

interface DailySnapshot {
  rate_date: string
  cny_tt_buy: number
  usd_tt_sell: number
  jpy_tt_sell: number
  usd_tt_buy: number
  source: string
  pub_time: string
}

interface DailySnapshotPayload {
  date: string
  has_snapshot: boolean
  snapshot: DailySnapshot | null
}

interface SnapshotFormState {
  rateDate: string
  cny_tt_buy: string
  usd_tt_sell: string
  jpy_tt_sell: string
  usd_tt_buy: string
}

function toDateInputValue(date = new Date()): string {
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000)
  return local.toISOString().slice(0, 10)
}

export function ExchangeRates() {
  const [ratesData, setRatesData] = useState<Record<string, Rate[]>>({})
  const [dailySnapshot, setDailySnapshot] = useState<DailySnapshotPayload | null>(null)
  const [snapshotHistory, setSnapshotHistory] = useState<Array<Record<string, any>>>([])

  const [loading, setLoading] = useState(false)
  const [savingSnapshot, setSavingSnapshot] = useState(false)
  const [lastUpdated, setLastUpdated] = useState('')
  const [error, setError] = useState('')
  const [snapshotMessage, setSnapshotMessage] = useState('')

  const [form, setForm] = useState<SnapshotFormState>({
    rateDate: toDateInputValue(),
    cny_tt_buy: '',
    usd_tt_sell: '',
    jpy_tt_sell: '',
    usd_tt_buy: '',
  })

  const fetchRates = async () => {
    const { data } = await apiJson<{ rates?: Record<string, Rate[]> }>('/api/exchange-rates')
    setRatesData(data.rates || {})
  }

  const fetchDailySnapshot = async () => {
    const { data } = await apiJson<DailySnapshotPayload>('/api/exchange-rates/daily-snapshot')
    setDailySnapshot(data)

    if (data.snapshot) {
      const snapshot = data.snapshot
      setForm((prev) => ({
        ...prev,
        rateDate: snapshot.rate_date || data.date || prev.rateDate,
        cny_tt_buy: String(snapshot.cny_tt_buy),
        usd_tt_sell: String(snapshot.usd_tt_sell),
        jpy_tt_sell: String(snapshot.jpy_tt_sell),
        usd_tt_buy: String(snapshot.usd_tt_buy),
      }))
    } else {
      setForm((prev) => ({
        ...prev,
        rateDate: data.date || prev.rateDate,
      }))
    }
  }

  const fetchSnapshotHistory = async () => {
    const { data } = await apiJson<{ items?: Array<Record<string, any>> }>('/api/exchange-rates/daily-snapshots?limit=14')
    setSnapshotHistory(Array.isArray(data.items) ? data.items : [])
  }

  const refreshAll = async () => {
    setLoading(true)
    setError('')
    try {
      await Promise.all([fetchRates(), fetchDailySnapshot(), fetchSnapshotHistory()])
      setLastUpdated(new Date().toLocaleTimeString())
    } catch (err: any) {
      setError(err?.message || '加载汇率信息失败，请稍后重试')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    refreshAll()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleSaveSnapshot = async () => {
    setSavingSnapshot(true)
    setSnapshotMessage('')
    try {
      const payload = {
        cny_tt_buy: Number(form.cny_tt_buy),
        usd_tt_sell: Number(form.usd_tt_sell),
        jpy_tt_sell: Number(form.jpy_tt_sell),
        usd_tt_buy: Number(form.usd_tt_buy),
      }

      if (!form.rateDate) {
        throw new Error('请选择快照日期')
      }
      if (Object.values(payload).some((value) => Number.isNaN(value) || value <= 0)) {
        throw new Error('请输入大于 0 的汇率数值')
      }

      await apiJson(`/api/exchange-rates/daily-snapshots/${form.rateDate}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
      })

      setSnapshotMessage('✅ 已保存，该日期的账单计算将使用此汇率')
      await Promise.all([fetchRates(), fetchDailySnapshot(), fetchSnapshotHistory()])
    } catch (err: any) {
      setSnapshotMessage(err?.message || '保存失败')
    } finally {
      setSavingSnapshot(false)
    }
  }

  const renderTable = (sourceId: string) => {
    const data = ratesData[sourceId] || []
    const isCfets = sourceId === 'cfets'

    return (
      <div className="table-wrapper fx-margin-top">
        <table className="data-table">
          <thead>
            {isCfets ? (
              <tr>
                <th>货币名称</th>
                <th>汇率中间价</th>
                <th>发布日期</th>
              </tr>
            ) : (
              <tr>
                <th>货币</th>
                <th>电汇买入</th>
                <th>电汇卖出</th>
                <th>现钞买入</th>
                <th>现钞卖出</th>
                <th>发布时间</th>
              </tr>
            )}
          </thead>
          <tbody>
            {loading && data.length === 0 ? (
              <tr>
                <td colSpan={isCfets ? 3 : 6} className="loading">
                  加载中...
                </td>
              </tr>
            ) : (
              data.map((rate, idx) => (
                <tr key={`${rate.currency}-${idx}`}>
                  <td className="cell-name fx-currency-name">
                    {rate.currency}
                  </td>

                  {isCfets ? (
                    <>
                      <td className="fx-val-lg">{rate.middle_rate}</td>
                      <td className="fx-text-muted">{rate.pub_time}</td>
                    </>
                  ) : (
                    <>
                      <td>{rate.tt_buy || '-'}</td>
                      <td>{rate.tt_sell || '-'}</td>
                      <td>{rate.notes_buy || '-'}</td>
                      <td>{rate.notes_sell || '-'}</td>
                      <td className="fx-text-sm-muted">{rate.pub_time}</td>
                    </>
                  )}
                </tr>
              ))
            )}

            {!loading && data.length === 0 && (
              <tr>
                <td colSpan={isCfets ? 3 : 6} className="fx-empty-cell">
                  暂无数据
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    )
  }

  return (
    <div className="exchange-rates">
      <div className="page-header fx-page-header">
        <div className="fx-header-left">
          <span className="fx-header-subtitle">汇率维护与查询</span>
        </div>


      </div>

      {error && <div className="error-message fx-error">{error}</div>}

      <div className="rate-card fx-snapshot-card">
        <div className="fx-snapshot-header">
          <div>
            <h3>今日汇率</h3>
            <p>当日外币计算统一使用此处维护的汇率数据</p>
          </div>
          <span className={`fx-snapshot-status ${dailySnapshot?.has_snapshot ? 'ok' : 'warn'}`}>
            {dailySnapshot?.has_snapshot ? '已生效' : '未录入'}
          </span>
        </div>

        <div className="fx-snapshot-grid">
          <div>
            <span className="label">日期</span>
            <span>{dailySnapshot?.date || '-'}</span>
          </div>
          <div>
            <span className="label">状态</span>
            <span>{dailySnapshot?.has_snapshot ? '✅ 已录入' : '⚠️ 请录入今日汇率'}</span>
          </div>
        </div>

        {dailySnapshot?.snapshot ? (
          <div className="fx-snapshot-values">
            <div>人民币电汇买入: <strong>{dailySnapshot.snapshot.cny_tt_buy}</strong></div>
            <div>美元电汇卖出: <strong>{dailySnapshot.snapshot.usd_tt_sell}</strong></div>
            <div>日元电汇卖出: <strong>{dailySnapshot.snapshot.jpy_tt_sell}</strong></div>
            <div>美元电汇买入: <strong>{dailySnapshot.snapshot.usd_tt_buy}</strong></div>
            <div>录入时间: <strong>{dailySnapshot.snapshot.pub_time || '-'}</strong></div>
          </div>
        ) : (
          <div className="fx-snapshot-empty">今日尚未录入汇率，含 RMB/JPY 的账单计算会被阻断，请先录入。</div>
        )}
      </div>


      <div className="rate-card">
        <div className="fx-card-header">
          <div className="fx-header-left-md">
            <div className="fx-icon-green">
              <HandCoins size={20} />
            </div>
            <div>
              <h3 className="fx-section-title">恒生银行 (Hang Seng) - 日快照维护</h3>
              <div className="fx-section-subtitle">在此录入并维护恒生银行的外汇牌价快照数据</div>
            </div>
          </div>
        </div>

        <div className="fx-manual-card">
          <div className="fx-form-grid">
            <label>日期<input type="date" value={form.rateDate} onChange={(e) => setForm((prev) => ({ ...prev, rateDate: e.target.value }))} /></label>
            <label>CNY 电汇买入<input type="number" min="0" step="0.0001" value={form.cny_tt_buy} onChange={(e) => setForm((prev) => ({ ...prev, cny_tt_buy: e.target.value }))} /></label>
            <label>USD 电汇卖出<input type="number" min="0" step="0.0001" value={form.usd_tt_sell} onChange={(e) => setForm((prev) => ({ ...prev, usd_tt_sell: e.target.value }))} /></label>
            <label>JPY 电汇卖出<input type="number" min="0" step="0.0001" value={form.jpy_tt_sell} onChange={(e) => setForm((prev) => ({ ...prev, jpy_tt_sell: e.target.value }))} /></label>
            <label>USD 电汇买入<input type="number" min="0" step="0.0001" value={form.usd_tt_buy} onChange={(e) => setForm((prev) => ({ ...prev, usd_tt_buy: e.target.value }))} /></label>
          </div>
          <div className="fx-form-actions fx-margin-top">
            <button className="btn-action primary" onClick={handleSaveSnapshot} disabled={savingSnapshot}>
              <Save size={16} />{savingSnapshot ? '保存中...' : '保存至系统快照'}
            </button>
            {snapshotMessage && <span className="fx-form-message fx-margin-left">{snapshotMessage}</span>}
          </div>
        </div>
      </div>

      <div className="rate-card fx-history-card">
        <h3>历史汇率记录</h3>
        <div className="table-wrapper fx-history-wrapper">
          <table className="data-table">
            <thead className="fx-history-thead">
              <tr>
                <th>日期</th>
                <th>CNY 买入</th>
                <th>USD 卖出</th>
                <th>JPY 卖出</th>
                <th>USD 买入</th>
                <th>录入时间</th>
              </tr>
            </thead>
            <tbody>
              {snapshotHistory.length === 0 ? (
                <tr>
                  <td colSpan={6} className="fx-empty-cell">
                    暂无记录
                  </td>
                </tr>
              ) : (
                snapshotHistory.map((item) => (
                  <tr key={`${item.date}`}>
                    <td>{item.date || '-'}</td>
                    <td>{item.cny_tt_buy ?? '-'}</td>
                    <td>{item.usd_tt_sell ?? '-'}</td>
                    <td>{item.jpy_tt_sell ?? '-'}</td>
                    <td>{item.usd_tt_buy ?? '-'}</td>
                    <td>{item.pub_time || '-'}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="rate-card">
        <div className="fx-card-header">
          <div className="fx-header-left-md">
            <div className="fx-icon-blue">
              <TrendingUp size={20} />
            </div>
            <div>
              <h3 className="fx-section-title">中国外汇交易中心 (CFETS)</h3>
              <div className="fx-section-subtitle">中国人民银行授权公布的人民币汇率中间价</div>
            </div>
          </div>
          <div className="fx-header-right">
            <button
              className="btn-secondary fx-refresh-btn"
              onClick={refreshAll}
              disabled={loading}
            >
              <RefreshCw size={14} className={loading ? 'spin' : ''} />
              <span>刷新 CFETS</span>
            </button>
            {lastUpdated && <div className="fx-last-updated">更新于 {lastUpdated}</div>}
          </div>
        </div>
        {renderTable('cfets')}
      </div>



      <style>{`
        .spin { animation: spin 1s linear infinite; }
        @keyframes spin { 100% { transform: rotate(360deg); } }
      `}</style>
    </div>
  )
}
