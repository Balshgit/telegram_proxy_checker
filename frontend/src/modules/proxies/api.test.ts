import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  ApiRequestError,
  createProxies,
  deleteAllProxies,
  deleteProxy,
  fetchProxies,
  fetchProxy,
  fetchRawProxies,
  updateAllProxies,
  updateProxy,
} from './api'
import type { TelegramProxy } from './api'

/** Мок глобального fetch: во всех тестах файла работаем только через него. */
const fetchMock = vi.fn()

beforeEach(() => {
  vi.stubGlobal('fetch', fetchMock)
  fetchMock.mockReset()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

/** Минимальная заглушка Response: клиент использует только ok/status/text(). */
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

const proxyFixture: TelegramProxy = {
  id: 1,
  name: 'Первая прокси',
  url: 'https://t.me/proxy?server=1.2.3.4&port=443',
  source_name: 'MTProto list',
  created_at: '2024-05-01T10:00:00Z',
  updated_at: null,
  status: 'enabled',
  latency: 120,
}

describe('fetchProxies', () => {
  it('передаёт limit и offset и распаковывает конверт', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        status: 200,
        payload: {
          data: [proxyFixture],
          pagination: { next_page: '/api/proxies?offset=10', previous_page: null },
          counters: { total: 42, active: 7 },
          proxies_share: 'https://t.me/proxy?server=1\nhttps://t.me/proxy?server=2',
        },
      }),
    )

    const result = await fetchProxies({ limit: 10, offset: 0 })

    expect(lastUrl()).toBe('/api/proxies?limit=10&offset=0')
    expect(result.items).toEqual([proxyFixture])
    expect(result.items[0].source_name).toBe('MTProto list')
    expect(result.pagination.next_page).toBe('/api/proxies?offset=10')
    expect(result.counters).toEqual({ total: 42, active: 7 })
    expect(result.share).toBe('https://t.me/proxy?server=1\nhttps://t.me/proxy?server=2')
  })

  it('добавляет proxy_status, только когда фильтр задан', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ status: 200, payload: null }))

    await fetchProxies({ limit: 25, offset: 50, status: 'disabled' })
    expect(lastUrl()).toBe('/api/proxies?limit=25&offset=50&proxy_status=disabled')

    await fetchProxies({ limit: 25, offset: 50, status: null })
    expect(lastUrl()).toBe('/api/proxies?limit=25&offset=50')
  })

  it('добавляет order_by, только когда сортировка задана', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ status: 200, payload: null }))

    await fetchProxies({ limit: 10, offset: 0, orderBy: 'created_at_desc' })
    expect(lastUrl()).toBe('/api/proxies?limit=10&offset=0&order_by=created_at_desc')

    await fetchProxies({ limit: 10, offset: 0, orderBy: null })
    expect(lastUrl()).toBe('/api/proxies?limit=10&offset=0')
  })

  it('возвращает безопасные значения по умолчанию при пустом payload', async () => {
    fetchMock.mockResolvedValue(makeResponse(''))

    const result = await fetchProxies({ limit: 10, offset: 0 })

    expect(result).toEqual({
      items: [],
      pagination: { next_page: null, previous_page: null },
      counters: { total: 0, active: 0 },
      share: '',
    })
  })

  it('прокидывает AbortSignal в fetch', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ status: 200, payload: null }))
    const controller = new AbortController()

    await fetchProxies({ limit: 10, offset: 0, signal: controller.signal })

    expect(lastInit().signal).toBe(controller.signal)
  })
})

describe('fetchProxy', () => {
  it('дочитывает одну прокси по id', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ status: 200, payload: { data: proxyFixture } }))

    const proxy = await fetchProxy(1)

    expect(lastUrl()).toBe('/api/proxies/1')
    expect(proxy).toEqual(proxyFixture)
  })

  it('отдаёт null, если бекенд вернул пустое тело', async () => {
    fetchMock.mockResolvedValue(makeResponse(''))

    await expect(fetchProxy(1)).resolves.toBeNull()
  })

  it('на 404 бросает ApiRequestError', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ status: 404, error: { type: 'ResourceNotFoundByID', detail: 'Не найдено' } }, 404),
    )

    await expect(fetchProxy(1)).rejects.toMatchObject({ name: 'ApiRequestError', status: 404 })
  })
})

describe('fetchRawProxies', () => {
  it('разбивает text/plain на строки, тримит и выкидывает пустые', async () => {
    fetchMock.mockResolvedValue(makeResponse('https://t.me/a\n  https://t.me/b  \n\n'))

    const urls = await fetchRawProxies()

    expect(lastUrl()).toBe('/api/proxies/raw')
    expect(urls).toEqual(['https://t.me/a', 'https://t.me/b'])
  })

  it('использует query-параметр status (не proxy_status)', async () => {
    fetchMock.mockResolvedValue(makeResponse(''))

    await fetchRawProxies({ status: 'enabled' })

    expect(lastUrl()).toBe('/api/proxies/raw?status=enabled')
  })

  it('на пустом ответе отдаёт пустой список', async () => {
    fetchMock.mockResolvedValue(makeResponse(''))

    await expect(fetchRawProxies()).resolves.toEqual([])
  })
})

describe('createProxies', () => {
  it('на 201 без тела сообщает, что прокси добавлены', async () => {
    fetchMock.mockResolvedValue(makeResponse('', 201))

    await expect(createProxies()).resolves.toBe('created')
    expect(lastUrl()).toBe('/api/proxies')
    expect(lastInit().method).toBe('POST')
    expect(lastInit().body).toBeUndefined()
  })

  it('передаёт source_ids, когда источники выбраны явно', async () => {
    fetchMock.mockResolvedValue(makeResponse('', 201))

    await createProxies({ sourceIds: [1, 2] })

    expect(JSON.parse(lastInit().body as string)).toEqual({ source_ids: [1, 2] })
  })

  it('пустой список источников телом не отправляет', async () => {
    fetchMock.mockResolvedValue(makeResponse('', 201))

    await createProxies({ sourceIds: [] })

    expect(lastInit().body).toBeUndefined()
  })

  it('202 с NoProxiesAddedError — штатный исход «нечего добавлять», а не ошибка', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ error: { type: 'NoProxiesAddedError', title: 'No proxies to add' } }, 202),
    )

    await expect(createProxies()).resolves.toBe('nothing-to-add')
  })

  it('на реальной ошибке бросает ApiRequestError', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ status: 502, error: { title: 'Bad gateway' } }, 502))

    const error = await createProxies().catch((raised: unknown) => raised)

    expect(error).toBeInstanceOf(ApiRequestError)
    expect((error as ApiRequestError).status).toBe(502)
  })
})

describe('изменяющие эндпоинты', () => {
  it('updateAllProxies шлёт POST /api/proxies/status', async () => {
    fetchMock.mockResolvedValue(makeResponse(''))

    await updateAllProxies()

    expect(lastUrl()).toBe('/api/proxies/status')
    expect(lastInit().method).toBe('POST')
  })

  it('deleteAllProxies шлёт DELETE /api/proxies и переваривает пустой 202', async () => {
    fetchMock.mockResolvedValue(makeResponse('', 202))

    await deleteAllProxies()

    expect(lastUrl()).toBe('/api/proxies')
    expect(lastInit().method).toBe('DELETE')
  })

  it('deleteProxy шлёт DELETE /api/proxies/{id} и переваривает пустой 204', async () => {
    fetchMock.mockResolvedValue(makeResponse('', 204))

    await deleteProxy(7)

    expect(lastUrl()).toBe('/api/proxies/7')
    expect(lastInit().method).toBe('DELETE')
  })
})

describe('updateProxy', () => {
  it('кладёт status в тело, когда он передан; ответ 202 приходит без тела', async () => {
    fetchMock.mockResolvedValue(makeResponse('', 202))

    await expect(updateProxy(7, { status: 'disabled' })).resolves.toBeUndefined()

    expect(lastUrl()).toBe('/api/proxies/7')
    expect(lastInit().method).toBe('PATCH')
    expect(JSON.parse(lastInit().body as string)).toEqual({ is_latency_update: false, status: 'disabled' })
  })

  it('не шлёт status, если он не задан, но передаёт is_latency_update', async () => {
    fetchMock.mockResolvedValue(makeResponse('', 202))

    await updateProxy(7, { isLatencyUpdate: true })

    expect(JSON.parse(lastInit().body as string)).toEqual({ is_latency_update: true })
  })

  it('на 404 бросает ApiRequestError', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ status: 404, error: { type: 'ResourceNotFoundByID', detail: 'Не найдено' } }, 404),
    )

    await expect(updateProxy(7, {})).rejects.toMatchObject({ status: 404, message: 'Не найдено' })
  })
})
