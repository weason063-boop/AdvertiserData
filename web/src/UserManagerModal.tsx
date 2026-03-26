import type { Dispatch, SetStateAction } from 'react'
import { ShieldCheck, Trash2 } from 'lucide-react'

import type { ManagedUser, UserPermission, UserRole } from './userManagement'

interface NewAccountForm {
  username: string
  password: string
  role: UserRole
  permissions: UserPermission[]
}

interface UserManagerModalProps {
  visible: boolean
  canManageAccounts: boolean
  currentRole: UserRole
  roleLabels: Record<UserRole, string>
  allPermissions: UserPermission[]
  permissionMeta: Record<UserPermission, { label: string; description: string }>
  newAccount: NewAccountForm
  setNewAccount: Dispatch<SetStateAction<NewAccountForm>>
  userOpLoading: boolean
  onClose: () => void
  onCreateAccount: () => void
  managedUsers: ManagedUser[]
  filteredManagedUsers: ManagedUser[]
  pagedManagedUsers: ManagedUser[]
  userSearchKeyword: string
  setUserSearchKeyword: (value: string) => void
  userListPage: number
  setUserListPage: Dispatch<SetStateAction<number>>
  userListTotalPages: number
  onDeleteAccount: (user: ManagedUser) => void
  normalizePermissions: (values: unknown) => UserPermission[]
}

export function UserManagerModal({
  visible,
  canManageAccounts,
  currentRole,
  roleLabels,
  allPermissions,
  permissionMeta,
  newAccount,
  setNewAccount,
  userOpLoading,
  onClose,
  onCreateAccount,
  managedUsers,
  filteredManagedUsers,
  pagedManagedUsers,
  userSearchKeyword,
  setUserSearchKeyword,
  userListPage,
  setUserListPage,
  userListTotalPages,
  onDeleteAccount,
  normalizePermissions,
}: UserManagerModalProps) {
  if (!visible || !canManageAccounts) return null

  return (
    <div className="user-manager-overlay" onMouseDown={onClose}>
      <div className="user-manager-modal" onMouseDown={(e) => e.stopPropagation()}>
        <div className="user-manager-modal-header">
          <div>
            <h3>账号管理</h3>
            <p>管理登录账号、角色及业务权限</p>
          </div>
          <button
            type="button"
            className="user-manager-close-btn"
            onClick={onClose}
            aria-label="关闭账号管理"
            title="关闭"
          >
            <span className="close-symbol" aria-hidden="true">×</span>
          </button>
        </div>

        <div className="settings-role-hint modal-role-hint">
          <ShieldCheck size={14} />
          <span>当前角色: {roleLabels[currentRole]}</span>
        </div>

        <div className="create-user-form">
          <div className="create-user-title">创建账号</div>
          <input
            type="text"
            placeholder="新账号用户名"
            value={newAccount.username}
            onChange={(e) => setNewAccount(v => ({ ...v, username: e.target.value }))}
          />
          <input
            type="password"
            placeholder="新账号密码"
            value={newAccount.password}
            onChange={(e) => setNewAccount(v => ({ ...v, password: e.target.value }))}
          />
          <select
            value={newAccount.role}
            onChange={(e) => {
              const role = e.target.value as UserRole
              setNewAccount((v) => ({
                ...v,
                role,
                permissions: role === 'admin' || role === 'super_admin' ? [...allPermissions] : [],
              }))
            }}
          >
            <option value="user">普通用户</option>
            <option value="admin">管理员</option>
            {currentRole === 'super_admin' && <option value="super_admin">超级管理员</option>}
          </select>

          <div className="permission-section-title">权限类型</div>
          {newAccount.role === 'user' && (
            <div className="permission-picker">
              {allPermissions.map((perm) => (
                <label className="permission-option" key={perm}>
                  <input
                    type="checkbox"
                    checked={newAccount.permissions.includes(perm)}
                    onChange={(e) => {
                      setNewAccount((v) => {
                        const next = e.target.checked
                          ? [...v.permissions, perm]
                          : v.permissions.filter((item) => item !== perm)
                        return { ...v, permissions: normalizePermissions(next) }
                      })
                    }}
                  />
                  <span className="permission-option-main">{permissionMeta[perm].label}</span>
                  <span className="permission-option-desc">{permissionMeta[perm].description}</span>
                </label>
              ))}
            </div>
          )}
          {newAccount.role !== 'user' && (
            <div className="permission-picker permission-note">管理员角色默认拥有全部业务权限</div>
          )}
          <button type="button" onClick={onCreateAccount} disabled={userOpLoading}>
            创建账号
          </button>
        </div>

        <div className="user-list-toolbar">
          <div className="user-list-title">账号列表（共 {filteredManagedUsers.length} 个）</div>
          <input
            type="text"
            className="user-list-search"
            placeholder="搜索账号名/角色"
            value={userSearchKeyword}
            onChange={(e) => {
              setUserSearchKeyword(e.target.value)
              setUserListPage(1)
            }}
          />
        </div>

        <div className="user-list">
          {pagedManagedUsers.length === 0 && (
            <div className="user-manager-empty">{managedUsers.length === 0 ? '暂无账号数据' : '没有匹配的账号'}</div>
          )}
          {pagedManagedUsers.map((u) => {
            const permissionText =
              normalizePermissions(u.permissions || []).map((perm) => permissionMeta[perm].label).join('、') || '无业务权限'
            return (
              <div className="user-row" key={u.id}>
                <div className="user-row-main">
                  <div className="user-row-top">
                    <span className="name">{u.username}</span>
                    <span className="role">{roleLabels[u.role]}</span>
                  </div>
                  <span className="permission-summary" title={permissionText}>
                    {permissionText}
                  </span>
                </div>
                {currentRole === 'super_admin' && (
                  <button
                    type="button"
                    className="delete-user-btn"
                    onClick={() => onDeleteAccount(u)}
                    disabled={userOpLoading}
                  >
                    <Trash2 size={13} />
                    删除
                  </button>
                )}
              </div>
            )
          })}
        </div>

        {filteredManagedUsers.length > 0 && userListTotalPages > 1 && (
          <div className="user-list-pagination">
            <span className="user-list-page-info">第 {userListPage} / {userListTotalPages} 页</span>
            <div className="user-list-pagination-actions">
              <button
                type="button"
                className="user-list-page-btn"
                onClick={() => setUserListPage((v) => Math.max(1, v - 1))}
                disabled={userListPage <= 1}
              >
                上一页
              </button>
              <button
                type="button"
                className="user-list-page-btn"
                onClick={() => setUserListPage((v) => Math.min(userListTotalPages, v + 1))}
                disabled={userListPage >= userListTotalPages}
              >
                下一页
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
