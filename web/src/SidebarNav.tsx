import { FileClock, FileText, LayoutDashboard, TrendingUp, Users } from 'lucide-react'

type Tab = 'dashboard' | 'clients' | 'results' | 'rates' | 'taskHistory'

interface SidebarNavProps {
  activeTab: Tab
  onSwitchTab: (tab: Tab) => void
  canViewTaskHistory: boolean
}

export function SidebarNav({
  activeTab,
  onSwitchTab,
  canViewTaskHistory,
}: SidebarNavProps) {
  return (
    <nav className="nav">
      <button
        className={`nav-item ${activeTab === 'dashboard' ? 'active' : ''}`}
        onClick={() => onSwitchTab('dashboard')}
      >
        <LayoutDashboard size={18} />
        <span>数据看板</span>
      </button>
      <button
        className={`nav-item ${activeTab === 'rates' ? 'active' : ''}`}
        onClick={() => onSwitchTab('rates')}
      >
        <TrendingUp size={18} />
        <span>实时汇率</span>
      </button>
      <button
        className={`nav-item ${activeTab === 'clients' ? 'active' : ''}`}
        onClick={() => onSwitchTab('clients')}
      >
        <Users size={18} />
        <span>客户条款</span>
      </button>
      <button
        className={`nav-item ${activeTab === 'results' ? 'active' : ''}`}
        onClick={() => onSwitchTab('results')}
      >
        <FileText size={18} />
        <span>账单明细</span>
      </button>
      {canViewTaskHistory && (
        <button
          className={`nav-item ${activeTab === 'taskHistory' ? 'active' : ''}`}
          onClick={() => onSwitchTab('taskHistory')}
        >
          <FileClock size={18} />
          <span>任务历史</span>
        </button>
      )}
    </nav>
  )
}
