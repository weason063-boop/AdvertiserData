import { RefreshCw } from 'lucide-react'
import type { Client, SyncResult } from './billingTypes'

interface NewClientData {
  name: string
  business_type: string
  fee_clause: string
}

interface ClientsPanelProps {
  active: boolean
  syncResult: SyncResult | null
  loading: boolean
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
}

export function ClientsPanel({
  active,
  syncResult,
  loading,
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
}: ClientsPanelProps) {
  if (!active) return null

  return (
    <div className="tab-content">
      {syncResult && (
        <div className="sync-status-card">
          <div className="sync-status-header">
            <RefreshCw size={18} className="text-primary" />
            <h3>飞书同步状态</h3>
            <span className="sync-time">{syncResult.time}</span>
          </div>
          <div className="sync-status-body">
            <p>{syncResult.message}</p>
            <div className="sync-stats">
              <span className="stat-label">更新记录数</span>
              <span className="stat-value">{syncResult.count}</span>
            </div>
          </div>
        </div>
      )}

      <div className="module-card">
        <div className="table-wrapper clients-table-wrap">
          <table className="data-table clients-table">
            <thead>
              <tr>
                <th>客户名称</th>
                <th>业务类型</th>
                <th>服务费条款</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {loading && (
                <tr><td colSpan={4} className="loading">加载中...</td></tr>
              )}
              {isAddingClient && canClientWrite && (
                <tr className="editing-row">
                  <td className="cell-name">
                    <input
                      className="edit-clause-input"
                      style={{ height: '36px' }}
                      value={newClientData.name}
                      onChange={e => onNewClientDataChange({ name: e.target.value })}
                      placeholder="输入客户名称"
                      autoFocus
                    />
                  </td>
                  <td className="cell-type">
                    <input
                      className="edit-clause-input"
                      style={{ height: '36px' }}
                      value={newClientData.business_type}
                      onChange={e => onNewClientDataChange({ business_type: e.target.value })}
                      placeholder="输入业务类型"
                    />
                  </td>
                  <td className="cell-clause">
                    <textarea
                      className="edit-clause-input"
                      value={newClientData.fee_clause}
                      onChange={(e) => onNewClientDataChange({ fee_clause: e.target.value })}
                      placeholder="输入服务费条款..."
                    />
                  </td>
                  <td className="cell-action">
                    <div className="action-buttons">
                      <button className="btn-save" onClick={onSaveNewClient} disabled={loading}>
                        保存
                      </button>
                      <button className="btn-cancel" onClick={onCancelAddClient}>
                        取消
                      </button>
                    </div>
                  </td>
                </tr>
              )}
              {clients.map(client => (
                <tr key={client.id} className={editingClient?.id === client.id ? 'editing-row' : ''}>
                  <td className="cell-name">{client.name}</td>
                  <td className="cell-type">{client.business_type || '—'}</td>
                  <td className="cell-clause">
                    {editingClient?.id === client.id ? (
                      <textarea
                        className="edit-clause-input"
                        value={editClause}
                        onChange={(e) => onEditClauseChange(e.target.value)}
                        placeholder="输入服务费条款..."
                        autoFocus
                      />
                    ) : (
                      client.fee_clause || '—'
                    )}
                  </td>
                  <td className="cell-action">
                    {editingClient?.id === client.id ? (
                      <div className="action-buttons">
                        <button className="btn-save" onClick={onSaveClause} disabled={loading}>
                          保存
                        </button>
                        <button className="btn-cancel" onClick={onCloseEdit}>
                          取消
                        </button>
                      </div>
                    ) : (
                      canClientWrite ? (
                        <button className="btn-edit" onClick={() => onOpenEdit(client)}>
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
    </div>
  )
}
