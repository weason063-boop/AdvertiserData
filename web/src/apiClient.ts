const resolveApiHost = () => {
  const host = window.location.hostname
  if (!host || host === '0.0.0.0' || host === '::' || host === '[::]') return '127.0.0.1'
  return host
}

const isLoopbackHost = () => {
  const host = window.location.hostname.toLowerCase()
  return host === 'localhost' || host === '127.0.0.1' || host === '::1' || host === '[::1]'
}

export const API_BASE = `http://${resolveApiHost()}:8000`
export const API_FALLBACK_BASE = `http://${resolveApiHost()}:8001`
export const SAME_ORIGIN_BASE = ''

const isDevFrontendPort = () => window.location.port === '5174'

const shouldUseSameOriginApi = () => {
  const port = window.location.port || ''
  // Frontend dev/prod ports are not API servers; avoid same-origin /api 404s.
  // Avoid same-origin /api fallback here to prevent noisy 404 loops.
  return port !== '5173' && port !== '5174' && port !== '4173'
}

const resolveLocalFallbackBases = (preferredPort: '8000' | '8001') => {
  if (!isLoopbackHost()) return []
  const first = preferredPort === '8001'
    ? ['http://127.0.0.1:8001', 'http://localhost:8001']
    : ['http://127.0.0.1:8000', 'http://localhost:8000']
  const second = preferredPort === '8001'
    ? ['http://127.0.0.1:8000', 'http://localhost:8000']
    : ['http://127.0.0.1:8001', 'http://localhost:8001']
  return [...first, ...second]
}

const resolveFallbackBases = () => (isDevFrontendPort() ? [
  API_FALLBACK_BASE,
  API_BASE,
  ...resolveLocalFallbackBases('8001'),
] : [
  API_BASE,
  API_FALLBACK_BASE,
  ...resolveLocalFallbackBases('8000'),
  ...(shouldUseSameOriginApi() ? [SAME_ORIGIN_BASE] : []),
])

const FALLBACK_BASES = Array.from(new Set(resolveFallbackBases()))

let lastKnownGoodBase: string | null = null

export const buildApiUrl = (base: string, path: string): string => (base ? `${base}${path}` : path)

export const getAuthHeaders = (): HeadersInit => {
  const token = window.localStorage.getItem('token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

const withAuthHeaders = (init: RequestInit | undefined, authEnabled: boolean): RequestInit => {
  const headers = new Headers(init?.headers ?? {})
  if (authEnabled) {
    const token = window.localStorage.getItem('token')
    if (token && !headers.has('Authorization')) {
      headers.set('Authorization', `Bearer ${token}`)
    }
  }
  return {
    ...init,
    headers,
  }
}

const parsePayload = async (res: Response): Promise<unknown> => {
  const contentType = (res.headers.get('content-type') || '').toLowerCase()
  if (contentType.includes('application/json')) {
    try {
      return await res.json()
    } catch {
      return null
    }
  }
  const text = await res.text()
  if (!text) return null
  try {
    return JSON.parse(text)
  } catch {
    return text
  }
}

const parseErrorMessage = (payload: unknown, status: number): string => {
  if (payload && typeof payload === 'object') {
    const record = payload as Record<string, unknown>
    const detail = record.detail ?? record.message ?? record.error
    if (typeof detail === 'string' && detail.trim()) return detail.trim()
  }
  if (typeof payload === 'string' && payload.trim()) return payload.trim()
  return `请求失败 (${status})`
}

export class ApiHttpError extends Error {
  status: number
  payload: unknown
  path: string
  base: string

  constructor(status: number, message: string, payload: unknown, path: string, base: string) {
    super(message)
    this.name = 'ApiHttpError'
    this.status = status
    this.payload = payload
    this.path = path
    this.base = base
  }
}

export const isApiHttpError = (error: unknown): error is ApiHttpError => error instanceof ApiHttpError

export interface ApiRequestOptions {
  auth?: boolean
  throwOnHttpError?: boolean
}

export const fetchWithPortFallback = async (
  path: string,
  init?: RequestInit,
): Promise<{ res: Response; base: string }> => {
  let lastErr: unknown = null
  let lastServerResp: { res: Response; base: string } | null = null
  const orderedBases = lastKnownGoodBase
    ? [lastKnownGoodBase, ...FALLBACK_BASES.filter((base) => base !== lastKnownGoodBase)]
    : FALLBACK_BASES

  for (const base of orderedBases) {
    try {
      const url = buildApiUrl(base, path)
      const res = await fetch(url, init)
      if (res.status === 404 || res.status >= 500) {
        lastServerResp = { res, base }
        continue
      }
      lastKnownGoodBase = base
      return { res, base }
    } catch (error) {
      lastErr = error
    }
  }

  if (lastServerResp) return lastServerResp
  if (lastErr instanceof Error) throw lastErr
  throw new Error('Failed to fetch')
}

export const apiJson = async <T = unknown>(
  path: string,
  init?: RequestInit,
  options?: ApiRequestOptions,
): Promise<{ data: T; res: Response; base: string }> => {
  const auth = options?.auth !== false
  const throwOnHttpError = options?.throwOnHttpError !== false
  const requestInit = withAuthHeaders(init, auth)
  const { res, base } = await fetchWithPortFallback(path, requestInit)
  const payload = await parsePayload(res)
  if (!res.ok && throwOnHttpError) {
    throw new ApiHttpError(res.status, parseErrorMessage(payload, res.status), payload, path, base)
  }
  return { data: payload as T, res, base }
}

export const apiBlob = async (
  path: string,
  init?: RequestInit,
  options?: ApiRequestOptions,
): Promise<{ blob: Blob; res: Response; base: string }> => {
  const auth = options?.auth !== false
  const throwOnHttpError = options?.throwOnHttpError !== false
  const requestInit = withAuthHeaders(init, auth)
  const { res, base } = await fetchWithPortFallback(path, requestInit)
  if (!res.ok && throwOnHttpError) {
    const payload = await parsePayload(res)
    throw new ApiHttpError(res.status, parseErrorMessage(payload, res.status), payload, path, base)
  }
  return { blob: await res.blob(), res, base }
}

export const parseDownloadFilename = (contentDisposition: string | null, fallback: string): string => {
  if (!contentDisposition) return fallback
  const encoded = /filename\*=UTF-8''([^;]+)/i.exec(contentDisposition)
  if (encoded?.[1]) return decodeURIComponent(encoded[1])
  const plain = /filename="?([^";]+)"?/i.exec(contentDisposition)
  if (plain?.[1]) return plain[1]
  return fallback
}
