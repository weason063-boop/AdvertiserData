import { normalizePermissions, type UserPermission, type UserRole } from './userManagement'

const parseJwtPayload = (token: string): Record<string, unknown> | null => {
  try {
    const payload = token.split('.')[1]
    if (!payload) return null
    const normalized = payload.replace(/-/g, '+').replace(/_/g, '/')
    const padLen = (4 - (normalized.length % 4)) % 4
    const padded = normalized + '='.repeat(padLen)
    return JSON.parse(atob(padded))
  } catch {
    return null
  }
}

export const extractUsernameFromToken = (token: string): string => {
  const payload = parseJwtPayload(token)
  if (!payload) return ''
  return String(payload.sub || payload.username || '').trim()
}

export const extractRoleFromToken = (token: string): UserRole => {
  const payload = parseJwtPayload(token)
  if (!payload) return 'user'
  const role = String(payload.role || 'user').toLowerCase()
  if (role === 'super_admin' || role === 'admin' || role === 'user') return role
  return 'user'
}

export const extractPermissionsFromToken = (token: string): UserPermission[] => {
  const payload = parseJwtPayload(token)
  if (!payload) return []
  return normalizePermissions(payload.permissions || payload.perms || [])
}
