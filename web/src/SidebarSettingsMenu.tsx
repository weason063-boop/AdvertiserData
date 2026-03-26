import type { RefObject } from 'react'
import {
  ChevronRight,
  FileText,
  LogOut,
  Settings,
  ShieldCheck,
  User,
  UserPlus,
} from 'lucide-react'

interface SidebarSettingsMenuProps {
  containerRef: RefObject<HTMLDivElement | null>
  showSettingsMenu: boolean
  onToggle: () => void
  userDisplay: string
  workspaceDisplay: string
  canManageAccounts: boolean
  currentRoleLabel: string
  isAuthenticated: boolean
  onOpenUserManager: () => void
  onLogout: () => void
}

export function SidebarSettingsMenu({
  containerRef,
  showSettingsMenu,
  onToggle,
  userDisplay,
  workspaceDisplay,
  canManageAccounts,
  currentRoleLabel,
  isAuthenticated,
  onOpenUserManager,
  onLogout,
}: SidebarSettingsMenuProps) {
  return (
    <div className="sidebar-footer" ref={containerRef}>
      <button
        className={`settings-trigger ${showSettingsMenu ? 'active' : ''}`}
        onClick={onToggle}
        title="设置"
      >
        <Settings size={16} />
        <span>设置</span>
      </button>

      {showSettingsMenu && (
        <div className="settings-menu">
          <div className="settings-user-block">
            <div className="settings-user-line">
              <User size={15} />
              <span>{userDisplay}</span>
            </div>
            <div className="settings-user-line muted">
              <FileText size={15} />
              <span>{workspaceDisplay}</span>
            </div>
          </div>

          <button type="button" className="settings-menu-item active">
            <div className="item-left">
              <Settings size={15} />
              <span>设置</span>
            </div>
          </button>

          {canManageAccounts && (
            <button type="button" className="settings-menu-item" onClick={onOpenUserManager}>
              <div className="item-left">
                <UserPlus size={15} />
                <span>账号管理</span>
              </div>
              <ChevronRight size={14} />
            </button>
          )}

          <div className="settings-role-hint">
            <ShieldCheck size={14} />
            <span>当前角色: {currentRoleLabel}</span>
          </div>

          {isAuthenticated && (
            <button type="button" className="settings-menu-item danger" onClick={onLogout}>
              <div className="item-left">
                <LogOut size={15} />
                <span>退出登录</span>
              </div>
            </button>
          )}
        </div>
      )}
    </div>
  )
}
