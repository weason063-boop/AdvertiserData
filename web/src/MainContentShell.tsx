import type { ChangeEvent, KeyboardEventHandler } from 'react'
import type { CalculationResult, Client, OperationAuditLog, ResultRow, SyncResult } from './billingTypes'
import { ClientsPanel } from './ClientsPanel'
import { Dashboard } from './DashboardV5'
import { ExchangeRates } from './ExchangeRates'
import { ErrorBoundary } from './ErrorBoundary'
import { ResultsPanel } from './ResultsPanel'
import { TaskHistoryPanel } from './TaskHistoryPanel'
import { TopbarActions } from './TopbarActions'

type Tab = 'dashboard' | 'clients' | 'results' | 'rates' | 'taskHistory'

interface DashboardData {
  stats: any
  trend: any[]
  top_clients?: any[]
}

interface MainContentShellProps {
  activeTab: Tab
  isAuthenticated: boolean
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
  dashboardData: DashboardData
  onNotify: (message: string, type: 'info' | 'success' | 'error') => void
  onRequireAuth: () => void
  syncResult: SyncResult | null
  clients: Client[]
  editingClient: Client | null
  editClause: string
  newClientData: { name: string; business_type: string; fee_clause: string }
  onNewClientDataChange: (patch: Partial<{ name: string; business_type: string; fee_clause: string }>) => void
  onSaveNewClient: () => void
  onCancelAddClient: () => void
  onEditClauseChange: (value: string) => void
  onSaveClause: () => void
  onCloseEdit: () => void
  onOpenEdit: (client: Client) => void
  results: CalculationResult | null
  pagedResultsData: ResultRow[]
  resultsTotalRows: number
  resultsPage: number
  resultsTotalPages: number
  resultsPageSize: number
  onResultsPageSizeChange: (size: number) => void
  onPrevResultsPage: () => void
  onNextResultsPage: () => void
  formatNumber: (value: string | number) => string
  taskHistoryItems: OperationAuditLog[]
  taskHistoryLoading: boolean
  taskHistoryLimit: number
  taskHistoryActorFilter: string
  taskHistoryActionFilter: string
  taskHistoryStatusFilter: string
  taskHistoryDaysFilter: string
  onTaskHistoryLimitChange: (size: number) => void
  onTaskHistoryActorFilterChange: (value: string) => void
  onTaskHistoryActionFilterChange: (value: string) => void
  onTaskHistoryStatusFilterChange: (value: string) => void
  onTaskHistoryDaysFilterChange: (value: string) => void
  onToggleTaskHistoryFailedOnly: () => void
  onRefreshTaskHistory: () => void
  onExportTaskHistory: () => void
}

const getTitle = (activeTab: Tab): string => {
  switch (activeTab) {
    case 'dashboard':
      return '数据概览'
    case 'rates':
      return '实时汇率查询'
    case 'clients':
      return '客户条款管理'
    case 'taskHistory':
      return '任务历史'
    default:
      return '账单明细'
  }
}

export function MainContentShell({
  activeTab,
  isAuthenticated,
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
  dashboardData,
  onNotify,
  onRequireAuth,
  syncResult,
  clients,
  editingClient,
  editClause,
  newClientData,
  onNewClientDataChange,
  onSaveNewClient,
  onCancelAddClient,
  onEditClauseChange,
  onSaveClause,
  onCloseEdit,
  onOpenEdit,
  results,
  pagedResultsData,
  resultsTotalRows,
  resultsPage,
  resultsTotalPages,
  resultsPageSize,
  onResultsPageSizeChange,
  onPrevResultsPage,
  onNextResultsPage,
  formatNumber,
  taskHistoryItems,
  taskHistoryLoading,
  taskHistoryLimit,
  taskHistoryActorFilter,
  taskHistoryActionFilter,
  taskHistoryStatusFilter,
  taskHistoryDaysFilter,
  onTaskHistoryLimitChange,
  onTaskHistoryActorFilterChange,
  onTaskHistoryActionFilterChange,
  onTaskHistoryStatusFilterChange,
  onTaskHistoryDaysFilterChange,
  onToggleTaskHistoryFailedOnly,
  onRefreshTaskHistory,
  onExportTaskHistory,
}: MainContentShellProps) {
  return (
    <main className="main">
      <div className="main-inner">
        <TopbarActions
          title={getTitle(activeTab)}
          showLoginButton={!isAuthenticated}
          showClientsActions={activeTab === 'clients'}
          showResultsActions={activeTab === 'results'}
          search={search}
          onSearchChange={onSearchChange}
          onSearchKeyPress={onSearchKeyPress}
          canClientWrite={canClientWrite}
          canFeishuSync={canFeishuSync}
          canBillingRun={canBillingRun}
          loading={loading}
          isAddingClient={isAddingClient}
          hasResults={hasResults}
          onOpenLogin={onOpenLogin}
          onAddClient={onAddClient}
          onSyncFeishu={onSyncFeishu}
          onUploadContract={onUploadContract}
          onUploadConsumption={onUploadConsumption}
          onRecalculate={onRecalculate}
          onDownloadResult={onDownloadResult}
        />

        <ErrorBoundary>
          {activeTab === 'dashboard' && (
            <Dashboard
              data={dashboardData}
              loading={loading && !dashboardData.stats}
              onNotify={onNotify}
              onRequireAuth={onRequireAuth}
            />
          )}

          {activeTab === 'rates' && <ExchangeRates />}

          <ClientsPanel
            active={activeTab === 'clients'}
            syncResult={syncResult}
            loading={loading}
            isAddingClient={isAddingClient}
            canClientWrite={canClientWrite}
            newClientData={newClientData}
            onNewClientDataChange={onNewClientDataChange}
            onSaveNewClient={onSaveNewClient}
            onCancelAddClient={onCancelAddClient}
            clients={clients}
            editingClient={editingClient}
            editClause={editClause}
            onEditClauseChange={onEditClauseChange}
            onSaveClause={onSaveClause}
            onCloseEdit={onCloseEdit}
            onOpenEdit={onOpenEdit}
          />

          {activeTab === 'results' && (
            <div className="results-section">
              <ResultsPanel
                active
                results={results}
                pagedResultsData={pagedResultsData}
                resultsTotalRows={resultsTotalRows}
                resultsPage={resultsPage}
                resultsTotalPages={resultsTotalPages}
                resultsPageSize={resultsPageSize}
                onPageSizeChange={onResultsPageSizeChange}
                onPrevPage={onPrevResultsPage}
                onNextPage={onNextResultsPage}
                formatNumber={formatNumber}
              />
            </div>
          )}

          {activeTab === 'taskHistory' && (
            <div className="results-section">
              <TaskHistoryPanel
                active
                items={taskHistoryItems}
                loading={taskHistoryLoading}
                limit={taskHistoryLimit}
                actorFilter={taskHistoryActorFilter}
                actionFilter={taskHistoryActionFilter}
                statusFilter={taskHistoryStatusFilter}
                daysFilter={taskHistoryDaysFilter}
                onLimitChange={onTaskHistoryLimitChange}
                onActorFilterChange={onTaskHistoryActorFilterChange}
                onActionFilterChange={onTaskHistoryActionFilterChange}
                onStatusFilterChange={onTaskHistoryStatusFilterChange}
                onDaysFilterChange={onTaskHistoryDaysFilterChange}
                onToggleFailedOnly={onToggleTaskHistoryFailedOnly}
                onRefresh={onRefreshTaskHistory}
                onExport={onExportTaskHistory}
              />
            </div>
          )}
        </ErrorBoundary>
      </div>
    </main>
  )
}
