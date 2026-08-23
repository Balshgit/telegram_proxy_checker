import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  apiRequest,
  apiRequestPayload,
  apiRequestText,
  ApiRequestError,
  jsonBody,
  registerErrorTexts,
} from './client'

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

describe('apiRequest', () => {
  it('добавляет префикс /api и заголовок Accept', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ status: 200, payload: { data: 1 } }))

    await apiRequest('/proxies')

    expect(lastUrl()).toBe('/api/proxies')
    expect((lastInit().headers as Record<string, string>).Accept).toBe('application/json')
  })

  it('распаковывает конверт и отдаёт статус ответа', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ status: 200, payload: { data: [1, 2] } }, 200))

    const result = await apiRequest<{ data: number[] }>('/proxies')

    expect(result).toEqual({ status: 200, payload: { data: [1, 2] }, errorCode: null })
  })

  it('на пустом теле (204) отдаёт payload: null, а не падает', async () => {
    fetchMock.mockResolvedValue(makeResponse('', 204))

    const result = await apiRequest('/proxies/1', { method: 'DELETE' })

    expect(result).toEqual({ status: 204, payload: null, errorCode: null })
  })

  it('отдаёт error.type даже на успешном статусе — так бекенд шлёт 202 «нечего добавлять»', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ error: { type: 'NoProxiesAddedError', title: 'No proxies to add' } }, 202),
    )

    const result = await apiRequest('/proxies', { method: 'POST' })

    expect(result.status).toBe(202)
    expect(result.errorCode).toBe('NoProxiesAddedError')
    expect(result.payload).toBeNull()
  })

  it('на не-2xx бросает ApiRequestError с кодом и статусом', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ status: 404, error: { type: 'ResourceNotFoundByID', detail: 'Не найдено' } }, 404),
    )

    const error = await apiRequest('/proxies/1').catch((raised: unknown) => raised)

    expect(error).toBeInstanceOf(ApiRequestError)
    expect((error as ApiRequestError).status).toBe(404)
    expect((error as ApiRequestError).code).toBe('ResourceNotFoundByID')
    expect((error as ApiRequestError).message).toBe('Не найдено')
  })

  it('падение сети превращается в ApiRequestError со status 0', async () => {
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'))

    const error = await apiRequest('/proxies').catch((raised: unknown) => raised)

    expect(error).toBeInstanceOf(ApiRequestError)
    expect((error as ApiRequestError).status).toBe(0)
    expect((error as ApiRequestError).message).toBe(
      'Не удалось связаться с сервером. Проверьте, что бекенд запущен.',
    )
  })

  it('приоритет текста ошибки: meta.message > detail > title', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ error: { title: 'T', detail: 'D', meta: { message: 'M' } } }, 422),
    )
    await expect(apiRequest('/proxies')).rejects.toMatchObject({ message: 'M' })

    fetchMock.mockResolvedValue(jsonResponse({ error: { title: 'T', detail: 'D' } }, 422))
    await expect(apiRequest('/proxies')).rejects.toMatchObject({ message: 'D' })

    fetchMock.mockResolvedValue(jsonResponse({ error: { title: 'T' } }, 422))
    await expect(apiRequest('/proxies')).rejects.toMatchObject({ message: 'T' })
  })

  it('на неразбираемом теле подставляет запасной текст с кодом ответа', async () => {
    fetchMock.mockResolvedValue(makeResponse('<html>502 Bad Gateway</html>', 502))

    await expect(apiRequest('/proxies')).rejects.toMatchObject({
      message: 'Запрос завершился с ошибкой (HTTP 502)',
      status: 502,
      code: null,
    })
  })

  it('зарегистрированный текст перекрывает технический title бекенда', async () => {
    registerErrorTexts({ SomeDomainError: 'Понятное объяснение' })
    fetchMock.mockResolvedValue(
      jsonResponse({ error: { type: 'SomeDomainError', title: 'Some domain error' } }, 400),
    )

    await expect(apiRequest('/proxies')).rejects.toMatchObject({ message: 'Понятное объяснение' })
  })
})

describe('apiRequestPayload', () => {
  it('отдаёт только payload конверта', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ status: 200, payload: { data: 'ok' } }))

    await expect(apiRequestPayload('/proxies')).resolves.toEqual({ data: 'ok' })
  })
})

describe('apiRequestText', () => {
  it('возвращает сырое тело как есть', async () => {
    fetchMock.mockResolvedValue(makeResponse('a\nb'))

    await expect(apiRequestText('/proxies/raw')).resolves.toBe('a\nb')
    expect((lastInit().headers as Record<string, string>).Accept).toBe('text/plain')
  })

  it('разбирает конверт с ошибкой даже для text/plain-эндпоинта', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ status: 500, error: { title: 'Boom', detail: 'Всё сломалось' } }, 500),
    )

    await expect(apiRequestText('/proxies/raw')).rejects.toMatchObject({
      name: 'ApiRequestError',
      status: 500,
      message: 'Всё сломалось',
    })
  })
})

describe('jsonBody', () => {
  it('собирает заголовок и сериализованное тело', () => {
    expect(jsonBody({ a: 1 })).toEqual({
      headers: { 'Content-Type': 'application/json' },
      body: '{"a":1}',
    })
  })
})
