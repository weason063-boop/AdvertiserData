export type UserPermission = 'client_write' | 'feishu_sync' | 'billing_run'
export type UserRole = 'user' | 'admin' | 'super_admin'

export interface ManagedUser {
  id: number
  username: string
  role: UserRole
  permissions?: UserPermission[]
  created_at?: string
}

export const ALL_PERMISSIONS: UserPermission[] = ['client_write', 'feishu_sync', 'billing_run']

export const ROLE_LABELS: Record<UserRole, string> = {
  user: '普通用户',
  admin: '管理员',
  super_admin: '超级管理员',
}

export const PERMISSION_META: Record<UserPermission, { label: string; description: string }> = {
  client_write: {
    label: '客户条款维护',
    description: '可新增客户、编辑条款和上传合同',
  },
  feishu_sync: {
    label: '飞书条款同步',
    description: '可执行飞书条款同步任务',
  },
  billing_run: {
    label: '账单上传与重算',
    description: '可上传账单并执行重算',
  },
}

export const USER_MANAGER_PAGE_SIZE = 8

export const normalizePermissions = (values: unknown): UserPermission[] => {
  if (!Array.isArray(values)) return []
  const normalized = values
    .map((item) => String(item || '').trim().toLowerCase())
    .filter((item): item is UserPermission => ALL_PERMISSIONS.includes(item as UserPermission))
  return Array.from(new Set(normalized))
}
