/**
 * Клиент эндпоинтов /api/proxies/sources — источников, из которых собираются прокси.
 *
 * Контракт бекенда (см. openapi.json):
 *   GET    /api/proxies/sources        200 — конверт со списком источников
 *   POST   /api/proxies/sources        201 — без тела
 *   PATCH  /api/proxies/sources/{id}   204 — без тела
 *   DELETE /api/proxies/sources/{id}   204 — без тела
 *
 * Изменяющие эндпоинты тело не возвращают, поэтому после каждого успешного
 * действия список перезагружается через `fetchProxiesSources`.
 */

import { apiRequest, apiRequestPayload, jsonBody } from '../../shared/api/client'
import type { DataPayload } from '../../shared/api/client'

export { ApiRequestError } from '../../shared/api/client'

export type ProxySourceStatus = 'enabled' | 'disabled'

/** Бекендовый `ProxyVendorNameEnum`: как разбирать ответ источника. */
export type ProxySourceVendor = 'external' | 'GitHub'

export interface ProxySource {
  id: number
  name: string
  url: string
  status: ProxySourceStatus
  vendor: ProxySourceVendor
  created_at: string
  updated_at: string | null
  /** Всего проксей, собранных из этого источника. */
  proxies_count: number
  /** Из них активных. */
  active_proxies_count: number
}

/** Ограничения полей из бекендовых валидаторов (app/api/proxies_sources/constants.py). */
export const SOURCE_NAME_MAX_LENGTH = 200
export const SOURCE_URL_MAX_LENGTH = 4000

export interface FetchProxiesSourcesParams {
  /** Фильтр по статусу источника. `null`/не передан — отдаются все. */
  status?: ProxySourceStatus | null
  signal?: AbortSignal
}

export async function fetchProxiesSources({
  status,
  signal,
}: FetchProxiesSourcesParams = {}): Promise<ProxySource[]> {
  const query = new URLSearchParams()
  if (status) {
    query.set('status', status)
  }

  const search = query.toString()
  const payload = await apiRequestPayload<DataPayload<ProxySource[]>>(
    `/proxies/sources${search ? `?${search}` : ''}`,
    { signal },
  )

  return payload?.data ?? []
}

export interface CreateProxySourcePayload {
  name: string
  url: string
  status: ProxySourceStatus
  vendor: ProxySourceVendor
}

/** POST /api/proxies/sources — добавление источника. Ответ пустой (201). */
export async function createProxySource(payload: CreateProxySourcePayload): Promise<void> {
  await apiRequest<never>('/proxies/sources', { method: 'POST', ...jsonBody(payload) })
}

/**
 * Поля, которые можно поменять. `undefined` означает «поле не трогаем»:
 * бекенд трактует отсутствующее (или `null`) поле именно так.
 */
export interface UpdateProxySourcePayload {
  name?: string
  url?: string
  status?: ProxySourceStatus
  vendor?: ProxySourceVendor
}

/** PATCH /api/proxies/sources/{id} — обновление источника. Ответ пустой (204). */
export async function updateProxySource(
  sourceId: number,
  payload: UpdateProxySourcePayload,
): Promise<void> {
  await apiRequest<never>(`/proxies/sources/${sourceId}`, { method: 'PATCH', ...jsonBody(payload) })
}

/**
 * DELETE /api/proxies/sources/{id} — удаление источника. Ответ пустой (204).
 * Прокси, собранные из него, остаются в базе и теряют привязку к источнику.
 */
export async function deleteProxySource(sourceId: number): Promise<void> {
  await apiRequest<never>(`/proxies/sources/${sourceId}`, { method: 'DELETE' })
}
