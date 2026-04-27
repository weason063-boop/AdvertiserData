import type { ChangeEvent, KeyboardEventHandler } from 'react'
import type {
  CalculationResult,
  Client,
  ContractChangeReview,
  DashboardData,
  OperationAuditLog,
  ResultRow,
  SyncResult,
} from './billingTypes'
import { ClientHistoryDetailPanel } from './ClientHistoryDetailPanel'
import { ClientsPanel } from './ClientsPanel'
import { Dashboard } from './DashboardV5'
import { ExchangeRates } from './ExchangeRates'
import { ErrorBoundary } from './ErrorBoundary'
import { LatestMonthClientsPanel } from './LatestMonthClientsPanelV2'
import { ResultsPanel } from './ResultsPanel'
import { TaskHistoryPanel } from './TaskHistoryPanel'
import { TopbarActions } from './TopbarActions'

type Tab =
  | 'dashboard'
  | 'clientLedger'
  | 'clientDetail'
  | 'clients'
  | 'results'
  | 'estimateResults'
  | 'rates'
  | 'taskHistory'

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
  hasEstimateResults: boolean
  onOpenLogin: () => void
  onAddClient: () => void
  onSyncFeishu: () => void
  onUploadContract: (event: ChangeEvent<HTMLInputElement>) => void
  onUploadConsumption: (event: ChangeEvent<HTMLInputElement>) => void
  onUploadEstimateConsumption: (event: ChangeEvent<HTMLInputElement>) => void
  onRecalculate: () => void
  onRecalculateEstimate: () => void
  onDownloadResult: () => void
  onDownloadEstimateResult: () => void
  dashboardData: DashboardData
  preferredDashboardMonth: string | null
  onNotify: (message: string, type: 'info' | 'success' | 'error') => void
  onRequireAuth: () => void
  selectedClientName: string | null
  onOpenClientDetail: (clientName: string) => void
  onCloseClientDetail: () => void
  syncResult: SyncResult | null
  contractChangeReviews: ContractChangeReview[]
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
  onApproveContractChangeReview: (reviewId: number, overrideNewFeeClause?: string) => void
  onIgnoreContractChangeReview: (reviewId: number) => void
  onBatchApproveContractChangeReviews: (
    reviewIds: number[],
    overrideNewFeeClauseByReviewId?: Record<number, string>,
  ) => void
  results: CalculationResult | null
  pagedResultsData: ResultRow[]
  resultsTotalRows: number
  resultsPage: number
  resultsTotalPages: number
  resultsPageSize: number
  onResultsPageSizeChange: (size: number) => void
  onPrevResultsPage: () => void
  onNextResultsPage: () => void
  estimateResults: CalculationResult | null
  pagedEstimateResultsData: ResultRow[]
  estimateResultsTotalRows: number
  estimateResultsPage: number
  estimateResultsTotalPages: number
  estimateResultsPageSize: number
  onEstimateResultsPageSizeChange: (size: number) => void
  onPrevEstimateResultsPage: () => void
  onNextEstimateResultsPage: () => void
  formatNumber: (value: string | number) => string
  taskHistoryItems: OperationAuditLog[]
  taskHistoryLoading: boolean
  taskHistoryLimit: number
  taskHistoryCurrentPage: number
  taskHistoryTotalCount: number
  taskHistoryActorFilter: string
  taskHistoryActionFilter: string
  taskHistoryStatusFilter: string
  taskHistoryDaysFilter: string
  onTaskHistoryLimitChange: (size: number) => void
  onTaskHistoryCurrentPageChange: (next: number) => void
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
    case 'clientLedger':
      return '客户明细'
    case 'clientDetail':
      return '客户历史账单'
    case 'results':
      return '账单明细'
    case 'estimateResults':
      return '预估消耗'
    case 'rates':
      return '实时汇率查询'
    case 'clients':
      return '客户条款管理'
    case 'taskHistory':
      return '任务历史'
    default:
      return '明细'
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
  hasEstimateResults,
  onOpenLogin,
  onAddClient,
  onSyncFeishu,
  onUploadContract,
  onUploadConsumption,
  onUploadEstimateConsumption,
  onRecalculate,
  onRecalculateEstimate,
  onDownloadResult,
  onDownloadEstimateResult,
  dashboardData,
  preferredDashboardMonth,
  onNotify,
  onRequireAuth,
  selectedClientName,
  onOpenClientDetail,
  onCloseClientDetail,
  syncResult,
  contractChangeReviews,
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
  onApproveContractChangeReview,
  onIgnoreContractChangeReview,
  onBatchApproveContractChangeReviews,
  results,
  pagedResultsData,
  resultsTotalRows,
  resultsPage,
  resultsTotalPages,
  resultsPageSize,
  onResultsPageSizeChange,
  onPrevResultsPage,
  onNextResultsPage,
  estimateResults,
  pagedEstimateResultsData,
  estimateResultsTotalRows,
  estimateResultsPage,
  estimateResultsTotalPages,
  estimateResultsPageSize,
  onEstimateResultsPageSizeChange,
  onPrevEstimateResultsPage,
  onNextEstimateResultsPage,
  formatNumber,
  taskHistoryItems,
  taskHistoryLoading,
  taskHistoryLimit,
  taskHistoryCurrentPage,
  taskHistoryTotalCount,
  taskHistoryActorFilter,
  taskHistoryActionFilter,
  taskHistoryStatusFilter,
  taskHistoryDaysFilter,
  onTaskHistoryLimitChange,
  onTaskHistoryCurrentPageChange,
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
          showEstimateResultsActions={activeTab === 'estimateResults'}
          search={search}
          onSearchChange={onSearchChange}
          onSearchKeyPress={onSearchKeyPress}
          canClientWrite={canClientWrite}
          canFeishuSync={canFeishuSync}
          canBillingRun={canBillingRun}
          loading={loading}
          isAddingClient={isAddingClient}
          hasResults={hasResults}
          hasEstimateResults={hasEstimateResults}
          onOpenLogin={onOpenLogin}
          onAddClient={onAddClient}
          onSyncFeishu={onSyncFeishu}
          onUploadContract={onUploadContract}
          onUploadConsumption={onUploadConsumption}
          onUploadEstimateConsumption={onUploadEstimateConsumption}
          onRecalculate={onRecalculate}
          onRecalculateEstimate={onRecalculateEstimate}
          onDownloadResult={onDownloadResult}
          onDownloadEstimateResult={onDownloadEstimateResult}
        />

        <ErrorBoundary>
          {activeTab === 'dashboard' && (
            <Dashboard
              data={dashboardData}
              preferredMonth={preferredDashboardMonth}
              loading={loading && !dashboardData.stats}
              onNotify={onNotify}
              onRequireAuth={onRequireAuth}
            />
          )}

          <LatestMonthClientsPanel
            active={activeTab === 'clientLedger'}
            isAuthenticated={isAuthenticated}
            selectedClientName={selectedClientName}
            formatNumber={formatNumber}
            onOpenClientDetail={onOpenClientDetail}
            onNotify={onNotify}
            onRequireAuth={onRequireAuth}
          />

          <ClientHistoryDetailPanel
            active={activeTab === 'clientDetail'}
            isAuthenticated={isAuthenticated}
            clientName={selectedClientName}
            formatNumber={formatNumber}
            onBack={onCloseClientDetail}
            onNotify={onNotify}
            onRequireAuth={onRequireAuth}
          />

          {activeTab === 'rates' && <ExchangeRates />}

          <ClientsPanel
            active={activeTab === 'clients'}
            syncResult={syncResult}
            loading={loading}
            search={search}
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
            contractChangeReviews={contractChangeReviews}
            onApproveContractChangeReview={onApproveContractChangeReview}
            onIgnoreContractChangeReview={onIgnoreContractChangeReview}
            onBatchApproveContractChangeReviews={onBatchApproveContractChangeReviews}
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

          {activeTab === 'estimateResults' && (
            <div className="results-section">
              <ResultsPanel
                active
                results={estimateResults}
                pagedResultsData={pagedEstimateResultsData}
                resultsTotalRows={estimateResultsTotalRows}
                resultsPage={estimateResultsPage}
                resultsTotalPages={estimateResultsTotalPages}
                resultsPageSize={estimateResultsPageSize}
                onPageSizeChange={onEstimateResultsPageSizeChange}
                onPrevPage={onPrevEstimateResultsPage}
                onNextPage={onNextEstimateResultsPage}
                formatNumber={formatNumber}
              />
            </div>
          )}

          {activeTab === 'taskHistory' && (
            <div className="results-section">
              <TaskHistoryPanel
                active
                items={taskHistoryItems}
                totalCount={taskHistoryTotalCount}
                currentPage={taskHistoryCurrentPage}
                onCurrentPageChange={onTaskHistoryCurrentPageChange}
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
