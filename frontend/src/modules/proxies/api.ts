/**
 * Клиент эндпоинтов /api/proxies.
 *
 * Контракт бекенда (см. openapi.json):
 *   GET    /api/proxies              200 — конверт со списком, пагинацией и счётчиками
 *   GET    /api/proxies/raw          200 — text/plain, урлы построчно
 *   GET    /api/proxies/{id}         200 — конверт с одной проксей
 *   POST   /api/proxies              201 — без тела; 202 + error.type=NoProxiesAddedError,
 *                                          если добавлять нечего
 *   POST   /api/proxies/status       200 — без тела
 *   PATCH  /api/proxies/{id}         202 — без тела
 *   DELETE /api/proxies              202 — без тела
 *   DELETE /api/proxies/{id}         204 — без тела
 *
 * Изменяющие эндпоинты тело не возвращают, поэтому актуальные данные страница
 * забирает отдельным запросом: список — через `fetchProxies`, одну строку —
 * через `fetchProxy`.
 */

import {
  apiRequest,
  apiRequestPayload,
  apiRequestText,
  jsonBody,
  registerErrorTexts,
} from '../../shared/api/client'
import type { DataPayload, PaginatedPayload, PaginationInfo } from '../../shared/api/client'

export { ApiRequestError } from '../../shared/api/client'
export type { PaginationInfo } from '../../shared/api/client'

export type ProxyStatus = 'enabled' | 'disabled'

/**
 * Значения query-параметра `order_by` у GET /api/proxies (бекендовый `ProxyOrderByEnum`).
 * Без суффикса `_desc` — по возрастанию.
 */
export type ProxyOrderBy = 'latency' | 'latency_desc' | 'created_at' | 'created_at_desc'

export interface TelegramProxy {
  id: number
  /** Человекочитаемое имя прокси. */
  name: string
  url: string
  /** Название источника, из которого прокси приехала. `null` — источник удалён. */
  source_name: string | null
  created_at: string
  updated_at: string | null
  status: ProxyStatus
  latency: number | null
}

export interface ProxiesCounters {
  /** Всего проксей в базе. */
  total: number
  /** Всего активных проксей — счётчик по всей выборке, а не по текущей странице. */
  active: number
}

export interface ProxiesPageResult {
  items: TelegramProxy[]
  pagination: PaginationInfo
  counters: ProxiesCounters
}

/**
 * Машиночитаемые коды ошибок бекенда (`error.type`).
 * Именно по ним, а не по тексту, стоит развешивать особую обработку в UI.
 */
export const API_ERROR_CODES = {
  /** POST /api/proxies: в источниках не оказалось ни одной новой прокси. */
  noProxiesAdded: 'NoProxiesAddedError',
} as const

registerErrorTexts({
  [API_ERROR_CODES.noProxiesAdded]: 'Нечего добавлять — новых прокси в источниках не нашлось',
})

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

  const payload = await apiRequestPayload<PaginatedPayload<TelegramProxy, ProxiesCounters>>(
    `/proxies?${query.toString()}`,
    { signal },
  )

  return {
    items: payload?.data ?? [],
    pagination: payload?.pagination ?? { next_page: null, previous_page: null },
    counters: payload?.counters ?? { total: 0, active: 0 },
  }
}

/**
 * GET /api/proxies/{id} — детальная информация по одной прокси.
 *
 * Нужен после PATCH и POST /proxies/status: изменяющие эндпоинты тело не
 * возвращают, поэтому свежую строку забираем отдельным запросом.
 */
export async function fetchProxy(proxyId: number, signal?: AbortSignal): Promise<TelegramProxy | null> {
  const payload = await apiRequestPayload<DataPayload<TelegramProxy>>(`/proxies/${proxyId}`, { signal })
  return payload?.data ?? null
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
  const raw = await apiRequestText(`/proxies/raw${search ? `?${search}` : ''}`, { signal })

  return raw
    .split('\n')
    .map((url) => url.trim())
    .filter(Boolean)
}

/**
 * Чем закончился POST /api/proxies.
 * `nothing-to-add` — штатный исход, а не поломка: бекенд отвечает 202
 * с `error.type === 'NoProxiesAddedError'`.
 */
export type CreateProxiesOutcome = 'created' | 'nothing-to-add'

export interface CreateProxiesParams {
  /**
   * ID источников, которые нужно опросить.
   * Пусто/не передано — бекенд обходит все включённые источники.
   */
  sourceIds?: number[] | null
}

/**
 * POST /api/proxies — бекенд сам подтягивает и пингует прокси.
 * Ответ 201 приходит без тела, поэтому список после успеха нужно перезагрузить.
 */
export async function createProxies({ sourceIds }: CreateProxiesParams = {}): Promise<CreateProxiesOutcome> {
  const init: RequestInit = { method: 'POST' }
  const body = sourceIds && sourceIds.length > 0 ? jsonBody({ source_ids: sourceIds }) : null

  const result = await apiRequest<never>('/proxies', body ? { ...init, ...body } : init)

  return result.errorCode === API_ERROR_CODES.noProxiesAdded ? 'nothing-to-add' : 'created'
}

/**
 * POST /api/proxies/status — бекенд перепроверяет все прокси:
 * обновляет латенси и выставляет статус по результату пинга. Ответ пустой (200).
 */
export async function updateAllProxies(): Promise<void> {
  await apiRequest<never>('/proxies/status', { method: 'POST' })
}

/** DELETE /api/proxies — удаляет все прокси из базы. Ответ пустой (202). */
export async function deleteAllProxies(): Promise<void> {
  await apiRequest<never>('/proxies', { method: 'DELETE' })
}

/** DELETE /api/proxies/{id} — удаляет одну прокси. Ответ пустой (204). */
export async function deleteProxy(proxyId: number): Promise<void> {
  await apiRequest<never>(`/proxies/${proxyId}`, { method: 'DELETE' })
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
 * PATCH /api/proxies/{id} — обновление одной прокси.
 *
 * Тело запроса: `{ status?: 'enabled' | 'disabled', is_latency_update: boolean }`.
 * Ответ — 202 без тела, поэтому обновлённую строку страница забирает
 * отдельным `fetchProxy`.
 */
export async function updateProxy(
  proxyId: number,
  { status = null, isLatencyUpdate = false }: UpdateProxyParams,
): Promise<void> {
  const body: { status?: ProxyStatus; is_latency_update: boolean } = {
    is_latency_update: isLatencyUpdate,
  }

  if (status) {
    body.status = status
  }

  await apiRequest<never>(`/proxies/${proxyId}`, { method: 'PATCH', ...jsonBody(body) })
}
