/**
 * Клиент для работы с эндпоинтами /api/proxies.
 *
 * Бекенд отдаёт ответы в общем конверте:
 *   { status, error, payload: { ... } }
 */

export type ProxyStatus = 'enabled' | 'disabled'

export interface TelegramProxy {
  id: number
  url: string
  created_at: string
  updated_at: string | null
  status: ProxyStatus
  latency: number | null
}

export interface PaginationInfo {
  next_page: string | null
  previous_page: string | null
}

export interface ProxiesCounters {
  total: number
}

export interface ProxiesPageResult {
  items: TelegramProxy[]
  pagination: PaginationInfo
  counters: ProxiesCounters
}

interface ApiError {
  type?: string | null
  title?: string | null
  detail?: string | null
  meta?: { message?: string | null } | null
}

interface Envelope<TPayload> {
  status: number
  error?: ApiError | null
  payload: TPayload
}

interface PaginatedPayload {
  pagination: PaginationInfo
  data: TelegramProxy[]
  counters: ProxiesCounters
}

interface DataPayload<T> {
  data: T
}

const API_BASE = '/api'

export class ApiRequestError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiRequestError'
    this.status = status
  }
}

function extractErrorMessage(body: unknown, status: number): string {
  const error = (body as Envelope<unknown> | null)?.error
  const message = error?.meta?.message ?? error?.detail ?? error?.title
  if (message) {
    return message
  }
  return `Запрос завершился с ошибкой (HTTP ${status})`
}

async function request<TPayload>(path: string, init?: RequestInit): Promise<TPayload | null> {
  let response: Response

  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { Accept: 'application/json' },
    })
  } catch {
    throw new ApiRequestError('Не удалось связаться с сервером. Проверьте, что бекенд запущен.', 0)
  }

  const rawBody = await response.text()
  let body: unknown = null

  if (rawBody) {
    try {
      body = JSON.parse(rawBody)
    } catch {
      body = null
    }
  }

  if (!response.ok) {
    throw new ApiRequestError(extractErrorMessage(body, response.status), response.status)
  }

  if (body === null || typeof body !== 'object') {
    return null
  }

  return (body as Envelope<TPayload>).payload ?? null
}

export interface FetchProxiesParams {
  limit: number
  offset: number
  status?: ProxyStatus | null
  signal?: AbortSignal
}

export async function fetchProxies({
  limit,
  offset,
  status,
  signal,
}: FetchProxiesParams): Promise<ProxiesPageResult> {
  const query = new URLSearchParams({ limit: String(limit), offset: String(offset) })
  if (status) {
    query.set('proxy_status', status)
  }

  const payload = await request<PaginatedPayload>(`/proxies?${query.toString()}`, { signal })

  return {
    items: payload?.data ?? [],
    pagination: payload?.pagination ?? { next_page: null, previous_page: null },
    counters: payload?.counters ?? { total: 0 },
  }
}

/** POST /api/proxies — бекенд сам подтягивает и пингует прокси, тело не нужно. */
export async function createProxies(): Promise<TelegramProxy[]> {
  const payload = await request<DataPayload<TelegramProxy[]>>('/proxies', { method: 'POST' })
  return payload?.data ?? []
}

/** DELETE /api/proxies — удаляет все прокси из базы. */
export async function deleteAllProxies(): Promise<void> {
  await request<never>('/proxies', { method: 'DELETE' })
}
