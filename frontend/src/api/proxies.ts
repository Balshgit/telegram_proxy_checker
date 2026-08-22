/**
 * Клиент для работы с эндпоинтами /api/proxies.
 *
 * Бекенд отдаёт ответы в общем конверте:
 *   { status, error, payload: { ... } }
 */

export type ProxyStatus = 'enabled' | 'disabled'

/**
 * Значения query-параметра `order_by` у GET /api/proxies (бекендовый `ProxyOrderByEnum`).
 * Без суффикса `_desc` — по возрастанию.
 */
export type ProxyOrderBy = 'latency' | 'latency_desc' | 'created_at' | 'created_at_desc'

export interface TelegramProxy {
  id: number
  /** Человекочитаемое имя прокси, приходит из GET /api/proxies. */
  name: string
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
  /** Всего проксей в базе (с учётом фильтров). */
  total: number
  /** Всего активных проксей — счётчик по всей выборке, а не по текущей странице. */
  active: number
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

/**
 * Машиночитаемые коды ошибок бекенда (`payload.error.type`).
 * Именно по ним, а не по тексту, стоит развешивать особую обработку в UI.
 */
export const API_ERROR_CODES = {
  /** POST /api/proxies: в источнике не оказалось ни одной новой прокси. */
  noProxiesAdded: 'NoProxiesAddedError',
} as const

/**
 * Человеческие тексты вместо технических английских title'ов с бекенда.
 * Ключ — `error.type`.
 */
const ERROR_TEXT_BY_CODE: Record<string, string> = {
  [API_ERROR_CODES.noProxiesAdded]: 'Нечего добавлять — новых прокси в источнике не нашлось',
}

export class ApiRequestError extends Error {
  readonly status: number
  /** `error.type` из конверта — стабильный код ошибки, если бекенд его прислал. */
  readonly code: string | null

  constructor(message: string, status: number, code: string | null = null) {
    super(message)
    this.name = 'ApiRequestError'
    this.status = status
    this.code = code
  }
}

function extractErrorCode(body: unknown): string | null {
  return (body as Envelope<unknown> | null)?.error?.type ?? null
}

function extractErrorMessage(body: unknown, status: number): string {
  const error = (body as Envelope<unknown> | null)?.error
  const known = error?.type ? ERROR_TEXT_BY_CODE[error.type] : undefined
  if (known) {
    return known
  }

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
      headers: { Accept: 'application/json', ...(init?.headers as Record<string, string> | undefined) },
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
    throw new ApiRequestError(
      extractErrorMessage(body, response.status),
      response.status,
      extractErrorCode(body),
    )
  }

  if (body === null || typeof body !== 'object') {
    return null
  }

  return (body as Envelope<TPayload>).payload ?? null
}

/**
 * Вариант `request` для эндпоинтов, отдающих text/plain вместо конверта.
 * Ошибки бекенд всё равно возвращает конвертом, поэтому тело неуспешного
 * ответа пробуем разобрать как JSON.
 */
async function requestText(path: string, init?: RequestInit): Promise<string> {
  let response: Response

  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { Accept: 'text/plain', ...(init?.headers as Record<string, string> | undefined) },
    })
  } catch {
    throw new ApiRequestError('Не удалось связаться с сервером. Проверьте, что бекенд запущен.', 0)
  }

  const rawBody = await response.text()

  if (!response.ok) {
    let body: unknown = null

    if (rawBody) {
      try {
        body = JSON.parse(rawBody)
      } catch {
        body = null
      }
    }

    throw new ApiRequestError(
      extractErrorMessage(body, response.status),
      response.status,
      extractErrorCode(body),
    )
  }

  return rawBody
}

export interface FetchProxiesParams {
  limit: number
  offset: number
  status?: ProxyStatus | null
  /** Сортировка выборки. Если не передана — бекенд сортирует по латенси по возрастанию. */
  orderBy?: ProxyOrderBy | null
  signal?: AbortSignal
}

export async function fetchProxies({
  limit,
  offset,
  status,
  orderBy,
  signal,
}: FetchProxiesParams): Promise<ProxiesPageResult> {
  const query = new URLSearchParams({ limit: String(limit), offset: String(offset) })
  if (status) {
    query.set('proxy_status', status)
  }
  if (orderBy) {
    query.set('order_by', orderBy)
  }

  const payload = await request<PaginatedPayload>(`/proxies?${query.toString()}`, { signal })

  return {
    items: payload?.data ?? [],
    pagination: payload?.pagination ?? { next_page: null, previous_page: null },
    counters: payload?.counters ?? { total: 0, active: 0 },
  }
}

export interface FetchRawProxiesParams {
  /** Фильтр по статусу. `null`/не передан — выгружаются все прокси. */
  status?: ProxyStatus | null
  signal?: AbortSignal
}

/**
 * GET /api/proxies/raw — урлы проксей одним текстовым буфером, каждый с новой строки.
 *
 * Ответ приходит как `text/plain`, а не в общем конверте. Фильтр передаётся
 * query-параметром `status` (внимание: тут именно `status`, а не `proxy_status`,
 * как в GET /api/proxies).
 */
export async function fetchRawProxies({ status, signal }: FetchRawProxiesParams = {}): Promise<string[]> {
  const query = new URLSearchParams()
  if (status) {
    query.set('status', status)
  }

  const search = query.toString()
  const raw = await requestText(`/proxies/raw${search ? `?${search}` : ''}`, { signal })

  return raw
    .split('\n')
    .map((url) => url.trim())
    .filter(Boolean)
}

/**
 * POST /api/proxies — бекенд сам подтягивает и пингует прокси, тело не нужно.
 *
 * Если в источнике не оказалось ни одной новой прокси, бекенд отвечает 400
 * с `error.type === 'NoProxiesAddedError'` — это не поломка, а штатный исход.
 */
export async function createProxies(): Promise<TelegramProxy[]> {
  const payload = await request<DataPayload<TelegramProxy[]>>('/proxies', { method: 'POST' })
  return payload?.data ?? []
}

/**
 * POST /api/proxies/status — бекенд перепроверяет все прокси:
 * обновляет латенси и выставляет статус по результату пинга. Тело не нужно, ответ пустой.
 */
export async function updateAllProxies(): Promise<void> {
  await request<never>('/proxies/status', { method: 'POST' })
}

/** DELETE /api/proxies — удаляет все прокси из базы. */
export async function deleteAllProxies(): Promise<void> {
  await request<never>('/proxies', { method: 'DELETE' })
}

/** DELETE /api/proxies/{proxy_id} — удаляет одну прокси. Ответ пустой (204). */
export async function deleteProxy(proxyId: number): Promise<void> {
  await request<never>(`/proxies/${proxyId}`, { method: 'DELETE' })
}

export interface UpdateProxyParams {
  /** Новый статус прокси. Если не передан — статус не меняется. */
  status?: ProxyStatus | null
  /**
   * Попросить бекенд заново пропинговать прокси.
   * Внимание: в этом случае бекенд сам выставит статус по результату пинга
   * (enabled, если ответ получен, иначе disabled), перекрыв переданный `status`.
   */
  isLatencyUpdate?: boolean
}

/**
 * PATCH /api/proxies/{proxy_id} — обновление одной прокси.
 *
 * Тело запроса: `{ status?: 'enabled' | 'disabled', is_latency_update: boolean }`.
 * Ответ: конверт с обновлённой проксей в `payload.data`.
 */
export async function updateProxy(
  proxyId: number,
  { status = null, isLatencyUpdate = false }: UpdateProxyParams,
): Promise<TelegramProxy | null> {
  const body: { status?: ProxyStatus; is_latency_update: boolean } = {
    is_latency_update: isLatencyUpdate,
  }

  if (status) {
    body.status = status
  }

  const payload = await request<DataPayload<TelegramProxy>>(`/proxies/${proxyId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })

  return payload?.data ?? null
}
