/**
 * Общий HTTP-клиент для всех модулей фронта.
 *
 * Бекенд отвечает конвертом:
 *   { status, error, payload: { ... } }
 *
 * Важные особенности контракта, из-за которых клиент устроен именно так:
 *
 * 1. Часть эндпоинтов вообще не возвращает тело (201/202/204) — `payload`
 *    у них `null`, и это не ошибка.
 * 2. Конверт с `error` может приезжать и с успешным HTTP-статусом.
 *    Например, POST /api/proxies на «нечего добавлять» отвечает 202
 *    с `error.type === 'NoProxiesAddedError'`. Поэтому `apiRequest`
 *    отдаёт наружу и статус, и код ошибки, а бросает `ApiRequestError`
 *    только на реальных не-2xx ответах.
 */

export const API_BASE = '/api'

export interface ApiError {
  type?: string | null
  title?: string | null
  detail?: string | null
  meta?: { message?: string | null } | null
}

export interface Envelope<TPayload> {
  status: number
  error?: ApiError | null
  payload?: TPayload | null
}

/** Полезная нагрузка эндпоинтов, отдающих одну сущность. */
export interface DataPayload<TData> {
  data: TData
}

export interface PaginationInfo {
  next_page: string | null
  previous_page: string | null
}

/** Полезная нагрузка постраничных эндпоинтов со счётчиками. */
export interface PaginatedPayload<TItem, TCounters> {
  pagination: PaginationInfo
  data: TItem[]
  counters: TCounters
}

/** Результат запроса: тело конверта плюс метаданные, по которым модуль решает, что произошло. */
export interface ApiResult<TPayload> {
  /** HTTP-статус ответа. */
  status: number
  /** `payload` конверта; `null`, если тела не было. */
  payload: TPayload | null
  /** `error.type` конверта — стабильный машиночитаемый код (приходит и на 2xx). */
  errorCode: string | null
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

const NETWORK_ERROR_TEXT = 'Не удалось связаться с сервером. Проверьте, что бекенд запущен.'

/**
 * Человеческие тексты вместо технических английских title'ов с бекенда.
 * Ключ — `error.type`. Модули дополняют реестр своими кодами через
 * `registerErrorTexts`, чтобы клиент не знал про их доменные ошибки.
 */
const ERROR_TEXT_BY_CODE: Record<string, string> = {}

export function registerErrorTexts(texts: Record<string, string>): void {
  Object.assign(ERROR_TEXT_BY_CODE, texts)
}

function parseBody(rawBody: string): unknown {
  if (!rawBody) {
    return null
  }
  try {
    return JSON.parse(rawBody)
  } catch {
    return null
  }
}

function extractErrorCode(body: unknown): string | null {
  return (body as Envelope<unknown> | null)?.error?.type ?? null
}

export function extractErrorMessage(body: unknown, status: number): string {
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

async function send(path: string, accept: string, init?: RequestInit): Promise<Response> {
  try {
    return await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { Accept: accept, ...(init?.headers as Record<string, string> | undefined) },
    })
  } catch {
    throw new ApiRequestError(NETWORK_ERROR_TEXT, 0)
  }
}

/** Запрос к JSON-эндпоинту. На не-2xx бросает `ApiRequestError`. */
export async function apiRequest<TPayload>(path: string, init?: RequestInit): Promise<ApiResult<TPayload>> {
  const response = await send(path, 'application/json', init)
  const body = parseBody(await response.text())

  if (!response.ok) {
    throw new ApiRequestError(
      extractErrorMessage(body, response.status),
      response.status,
      extractErrorCode(body),
    )
  }

  const envelope = body && typeof body === 'object' ? (body as Envelope<TPayload>) : null

  return {
    status: response.status,
    payload: envelope?.payload ?? null,
    errorCode: extractErrorCode(envelope),
  }
}

/** Короткая форма `apiRequest` там, где нужен только payload. */
export async function apiRequestPayload<TPayload>(
  path: string,
  init?: RequestInit,
): Promise<TPayload | null> {
  const result = await apiRequest<TPayload>(path, init)
  return result.payload
}

/**
 * Вариант для эндпоинтов, отдающих `text/plain` вместо конверта.
 * Ошибки бекенд всё равно возвращает конвертом, поэтому тело неуспешного
 * ответа пробуем разобрать как JSON.
 */
export async function apiRequestText(path: string, init?: RequestInit): Promise<string> {
  const response = await send(path, 'text/plain', init)
  const rawBody = await response.text()

  if (!response.ok) {
    const body = parseBody(rawBody)
    throw new ApiRequestError(
      extractErrorMessage(body, response.status),
      response.status,
      extractErrorCode(body),
    )
  }

  return rawBody
}

/** JSON-тело запроса: заголовок и сериализация в одном месте. */
export function jsonBody(payload: unknown): RequestInit {
  return {
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }
}
