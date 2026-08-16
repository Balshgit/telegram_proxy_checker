import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  API_ERROR_CODES,
  ApiRequestError,
  createProxies,
  deleteAllProxies,
  fetchProxies,
  fetchRawProxies,
  updateAllProxies,
  updateProxy,
} from './proxies'
import type { TelegramProxy } from './proxies'

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

/** Достаёт URL из последнего вызова fetch. */
function lastUrl(): string {
  return fetchMock.mock.calls.at(-1)?.[0] as string
}

/** Достаёт init-объект из последнего вызова fetch. */
function lastInit(): RequestInit {
  return (fetchMock.mock.calls.at(-1)?.[1] ?? {}) as RequestInit
}

const proxyFixture: TelegramProxy = {
  id: 1,
  name: 'Первая прокси',
  url: 'https://t.me/proxy?server=1.2.3.4&port=443',
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
        },
      }),
    )

    const result = await fetchProxies({ limit: 10, offset: 0 })

    expect(lastUrl()).toBe('/api/proxies?limit=10&offset=0')
    expect(result.items).toEqual([proxyFixture])
    expect(result.pagination.next_page).toBe('/api/proxies?offset=10')
    expect(result.counters).toEqual({ total: 42, active: 7 })
  })

  it('добавляет proxy_status, только когда фильтр задан', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ status: 200, payload: null }))

    await fetchProxies({ limit: 25, offset: 50, status: 'disabled' })
    expect(lastUrl()).toBe('/api/proxies?limit=25&offset=50&proxy_status=disabled')

    await fetchProxies({ limit: 25, offset: 50, status: null })
    expect(lastUrl()).toBe('/api/proxies?limit=25&offset=50')
  })

  it('возвращает безопасные значения по умолчанию при пустом payload', async () => {
    fetchMock.mockResolvedValue(makeResponse(''))

    const result = await fetchProxies({ limit: 10, offset: 0 })

    expect(result).toEqual({
      items: [],
      pagination: { next_page: null, previous_page: null },
      counters: { total: 0, active: 0 },
    })
  })

  it('прокидывает AbortSignal в fetch', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ status: 200, payload: null }))
    const controller = new AbortController()

    await fetchProxies({ limit: 10, offset: 0, signal: controller.signal })

    expect(lastInit().signal).toBe(controller.signal)
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

  it('разбирает конверт с ошибкой даже для text/plain-эндпоинта', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ status: 500, error: { title: 'Boom', detail: 'Всё сломалось' }, payload: null }, 500),
    )

    await expect(fetchRawProxies()).rejects.toMatchObject({
      name: 'ApiRequestError',
      status: 500,
      message: 'Всё сломалось',
    })
  })
})

describe('createProxies', () => {
  it('шлёт POST и возвращает созданные прокси', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ status: 200, payload: { data: [proxyFixture] } }))

    const created = await createProxies()

    expect(lastUrl()).toBe('/api/proxies')
    expect(lastInit().method).toBe('POST')
    expect(created).toEqual([proxyFixture])
  })

  it('возвращает пустой список, если payload пустой', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ status: 200, payload: null }))

    await expect(createProxies()).resolves.toEqual([])
  })

  it('на 400 NoProxiesAddedError отдаёт понятный текст и машиночитаемый код', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        { status: 400, error: { type: 'NoProxiesAddedError', title: 'No proxies added' }, payload: null },
        400,
      ),
    )

    const error = await createProxies().catch((raised: unknown) => raised)

    expect(error).toBeInstanceOf(ApiRequestError)
    expect((error as ApiRequestError).code).toBe(API_ERROR_CODES.noProxiesAdded)
    expect((error as ApiRequestError).status).toBe(400)
    expect((error as ApiRequestError).message).toBe('Нечего добавлять — новых прокси в источнике не нашлось')
  })
})

describe('updateAllProxies / deleteAllProxies', () => {
  it('updateAllProxies шлёт POST /api/proxies/status', async () => {
    fetchMock.mockResolvedValue(makeResponse(''))

    await updateAllProxies()

    expect(lastUrl()).toBe('/api/proxies/status')
    expect(lastInit().method).toBe('POST')
  })

  it('deleteAllProxies шлёт DELETE /api/proxies', async () => {
    fetchMock.mockResolvedValue(makeResponse(''))

    await deleteAllProxies()

    expect(lastUrl()).toBe('/api/proxies')
    expect(lastInit().method).toBe('DELETE')
  })
})

describe('updateProxy', () => {
  it('кладёт status в тело, когда он передан', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ status: 200, payload: { data: proxyFixture } }))

    const updated = await updateProxy(7, { status: 'disabled' })

    expect(lastUrl()).toBe('/api/proxies/7')
    expect(lastInit().method).toBe('PATCH')
    expect(JSON.parse(lastInit().body as string)).toEqual({ is_latency_update: false, status: 'disabled' })
    expect(updated).toEqual(proxyFixture)
  })

  it('не шлёт status, если он не задан, но передаёт is_latency_update', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ status: 200, payload: { data: proxyFixture } }))

    await updateProxy(7, { isLatencyUpdate: true })

    expect(JSON.parse(lastInit().body as string)).toEqual({ is_latency_update: true })
  })

  it('возвращает null, если бекенд не прислал данные', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ status: 200, payload: null }))

    await expect(updateProxy(7, {})).resolves.toBeNull()
  })
})

describe('обработка ошибок', () => {
  it('падение сети превращается в ApiRequestError со status 0', async () => {
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'))

    const error = await fetchProxies({ limit: 10, offset: 0 }).catch((raised: unknown) => raised)

    expect(error).toBeInstanceOf(ApiRequestError)
    expect((error as ApiRequestError).status).toBe(0)
    expect((error as ApiRequestError).message).toBe(
      'Не удалось связаться с сервером. Проверьте, что бекенд запущен.',
    )
  })

  it('приоритет текста ошибки: meta.message > detail > title', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        { status: 422, error: { title: 'T', detail: 'D', meta: { message: 'M' } }, payload: null },
        422,
      ),
    )
    await expect(fetchProxies({ limit: 10, offset: 0 })).rejects.toMatchObject({ message: 'M' })

    fetchMock.mockResolvedValue(
      jsonResponse({ status: 422, error: { title: 'T', detail: 'D' }, payload: null }, 422),
    )
    await expect(fetchProxies({ limit: 10, offset: 0 })).rejects.toMatchObject({ message: 'D' })

    fetchMock.mockResolvedValue(jsonResponse({ status: 422, error: { title: 'T' }, payload: null }, 422))
    await expect(fetchProxies({ limit: 10, offset: 0 })).rejects.toMatchObject({ message: 'T' })
  })

  it('на неразбираемом теле подставляет запасной текст с кодом ответа', async () => {
    fetchMock.mockResolvedValue(makeResponse('<html>502 Bad Gateway</html>', 502))

    await expect(fetchProxies({ limit: 10, offset: 0 })).rejects.toMatchObject({
      message: 'Запрос завершился с ошибкой (HTTP 502)',
      status: 502,
      code: null,
    })
  })
})
