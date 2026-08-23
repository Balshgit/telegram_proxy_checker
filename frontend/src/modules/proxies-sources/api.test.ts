import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  createProxySource,
  deleteProxySource,
  fetchProxiesSources,
  updateProxySource,
} from './api'
import type { ProxySource } from './api'

const fetchMock = vi.fn()

beforeEach(() => {
  vi.stubGlobal('fetch', fetchMock)
  fetchMock.mockReset()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

function makeResponse(rawBody: string, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => rawBody,
  } as unknown as Response
}

function jsonResponse(body: unknown, status = 200): Response {
  return makeResponse(JSON.stringify(body), status)
}

function lastUrl(): string {
  return fetchMock.mock.calls.at(-1)?.[0] as string
}

function lastInit(): RequestInit {
  return (fetchMock.mock.calls.at(-1)?.[1] ?? {}) as RequestInit
}

const sourceFixture: ProxySource = {
  id: 1,
  name: 'MTProto list',
  url: 'https://raw.githubusercontent.com/owner/repo/main/list.txt',
  status: 'enabled',
  vendor: 'GitHub',
  created_at: '2024-05-01T10:00:00Z',
  updated_at: null,
  proxies_count: 120,
  active_proxies_count: 34,
}

describe('fetchProxiesSources', () => {
  it('без фильтра запрашивает весь список и распаковывает конверт', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ status: 200, payload: { data: [sourceFixture] } }))

    const sources = await fetchProxiesSources()

    expect(lastUrl()).toBe('/api/proxies/sources')
    expect(sources).toEqual([sourceFixture])
  })

  it('фильтр по статусу уезжает query-параметром status', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ status: 200, payload: { data: [] } }))

    await fetchProxiesSources({ status: 'disabled' })

    expect(lastUrl()).toBe('/api/proxies/sources?status=disabled')
  })

  it('на пустом теле отдаёт пустой список', async () => {
    fetchMock.mockResolvedValue(makeResponse(''))

    await expect(fetchProxiesSources()).resolves.toEqual([])
  })

  it('прокидывает AbortSignal в fetch', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ status: 200, payload: { data: [] } }))
    const controller = new AbortController()

    await fetchProxiesSources({ signal: controller.signal })

    expect(lastInit().signal).toBe(controller.signal)
  })
})

describe('createProxySource', () => {
  it('шлёт POST с телом источника и переваривает пустой 201', async () => {
    fetchMock.mockResolvedValue(makeResponse('', 201))

    await createProxySource({
      name: 'MTProto list',
      url: 'https://example.com/list.txt',
      status: 'enabled',
      vendor: 'external',
    })

    expect(lastUrl()).toBe('/api/proxies/sources')
    expect(lastInit().method).toBe('POST')
    expect(JSON.parse(lastInit().body as string)).toEqual({
      name: 'MTProto list',
      url: 'https://example.com/list.txt',
      status: 'enabled',
      vendor: 'external',
    })
  })

  it('ошибку валидации отдаёт как ApiRequestError', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ status: 422, error: { type: 'ParamValidationError', detail: 'Плохой url' } }, 422),
    )

    await expect(
      createProxySource({ name: 'x', url: 'нет', status: 'enabled', vendor: 'external' }),
    ).rejects.toMatchObject({ name: 'ApiRequestError', status: 422, message: 'Плохой url' })
  })
})

describe('updateProxySource', () => {
  it('шлёт PATCH только с изменёнными полями и переваривает пустой 204', async () => {
    fetchMock.mockResolvedValue(makeResponse('', 204))

    await updateProxySource(5, { status: 'disabled' })

    expect(lastUrl()).toBe('/api/proxies/sources/5')
    expect(lastInit().method).toBe('PATCH')
    expect(JSON.parse(lastInit().body as string)).toEqual({ status: 'disabled' })
  })

  it('на 404 бросает ApiRequestError', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ status: 404, error: { type: 'ResourceNotFoundByID', detail: 'Не найдено' } }, 404),
    )

    await expect(updateProxySource(5, { name: 'x' })).rejects.toMatchObject({ status: 404 })
  })
})

describe('deleteProxySource', () => {
  it('шлёт DELETE и переваривает пустой 204', async () => {
    fetchMock.mockResolvedValue(makeResponse('', 204))

    await deleteProxySource(5)

    expect(lastUrl()).toBe('/api/proxies/sources/5')
    expect(lastInit().method).toBe('DELETE')
  })
})
