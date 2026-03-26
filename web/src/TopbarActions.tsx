import type { ChangeEvent, KeyboardEventHandler } from 'react'
import {
  Download,
  LogIn,
  Plus,
  RefreshCw,
  Search,
  Upload,
} from 'lucide-react'

interface TopbarActionsProps {
  title: string
  showLoginButton: boolean
  showClientsActions: boolean
  showResultsActions: boolean
  search: string
  onSearchChange: (value: string) => void
  onSearchKeyPress: KeyboardEventHandler<HTMLInputElement>
  canClientWrite: boolean
  canFeishuSync: boolean
  canBillingRun: boolean
  loading: boolean
  isAddingClient: boolean
  hasResults: boolean
  onOpenLogin: () => void
  onAddClient: () => void
  onSyncFeishu: () => void
  onUploadContract: (event: ChangeEvent<HTMLInputElement>) => void
  onUploadConsumption: (event: ChangeEvent<HTMLInputElement>) => void
  onRecalculate: () => void
  onDownloadResult: () => void
}

export function TopbarActions({
  title,
  showLoginButton,
  showClientsActions,
  showResultsActions,
  search,
  onSearchChange,
  onSearchKeyPress,
  canClientWrite,
  canFeishuSync,
  canBillingRun,
  loading,
  isAddingClient,
  hasResults,
  onOpenLogin,
  onAddClient,
  onSyncFeishu,
  onUploadContract,
  onUploadConsumption,
  onRecalculate,
  onDownloadResult,
}: TopbarActionsProps) {
  return (
    <div className="topbar">
      <h2>{title}</h2>
      <div className="topbar-actions">
        {showLoginButton && (
          <button className="btn-action secondary" onClick={onOpenLogin} title="登录管理">
            <LogIn size={16} />
            <span>登录</span>
          </button>
        )}

        {showClientsActions && (
          <>
            <div className="search-box">
              <Search size={16} className="search-icon" />
              <input
                type="text"
                placeholder="搜索客户..."
                value={search}
                onChange={(e) => onSearchChange(e.target.value)}
                onKeyPress={onSearchKeyPress}
              />
            </div>
            {canClientWrite && (
              <button
                className="btn-action primary"
                onClick={onAddClient}
                disabled={loading || isAddingClient}
              >
                <Plus size={16} />
                新增客户
              </button>
            )}
            {canFeishuSync && (
              <button className="btn-action primary" onClick={onSyncFeishu} disabled={loading}>
                <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
                同步飞书条款
              </button>
            )}
            {canClientWrite && (
              <label className="btn-action secondary" style={{ display: 'none' }}>
                <Upload size={16} />
                上传合同条款
                <input
                  type="file"
                  accept=".xlsx,.xls"
                  onChange={onUploadContract}
                  hidden
                />
              </label>
            )}
          </>
        )}

        {showResultsActions && (
          <>
            {canBillingRun && (
              <label className="btn-action primary">
                <Upload size={16} />
                上传消耗数据
                <input
                  type="file"
                  accept=".xlsx,.xls"
                  onChange={onUploadConsumption}
                  hidden
                />
              </label>
            )}
            {canBillingRun && (
              <button className="btn-action secondary" onClick={onRecalculate} disabled={loading}>
                <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
                重新计算
              </button>
            )}
            {hasResults && (
              <button className="btn-action secondary" onClick={onDownloadResult}>
                <Download size={16} />
                下载 Excel
              </button>
            )}
          </>
        )}
      </div>
    </div>
  )
}
