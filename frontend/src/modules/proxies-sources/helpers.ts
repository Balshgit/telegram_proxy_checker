/**
 * Чистые хелперы страницы источников: подписи, фильтры и валидация формы.
 * Вынесены отдельно, чтобы тестировать без рендера компонента.
 */

import { truncate } from '../../shared/ui/format'
import { SOURCE_NAME_MAX_LENGTH, SOURCE_URL_MAX_LENGTH } from './api'
import type { ProxySource, ProxySourceStatus, ProxySourceVendor } from './api'

export const STATUS_LABELS: Record<ProxySourceStatus, string> = {
  enabled: 'Включён',
  disabled: 'Выключен',
}

export const STATUS_OPTIONS: ProxySourceStatus[] = ['enabled', 'disabled']

export type StatusFilter = ProxySourceStatus | 'all'

export const STATUS_FILTERS: { value: StatusFilter; label: string }[] = [
  { value: 'all', label: 'Все' },
  { value: 'enabled', label: 'Включённые' },
  { value: 'disabled', label: 'Выключенные' },
]

/**
 * Вендор определяет, как бекенд разбирает ответ источника:
 * `GitHub` — сырой файл в репозитории, `external` — произвольный внешний адрес.
 */
export const VENDOR_LABELS: Record<ProxySourceVendor, string> = {
  GitHub: 'GitHub',
  external: 'Внешний источник',
}

export const VENDOR_OPTIONS: ProxySourceVendor[] = ['GitHub', 'external']

export const DEFAULT_VENDOR: ProxySourceVendor = 'GitHub'
export const DEFAULT_STATUS: ProxySourceStatus = 'enabled'

/** Как называть источник в тостах и заголовках модалок. */
export function sourceLabel(source: ProxySource): string {
  return source.name ? `«${truncate(source.name, 32)}»` : `#${source.id}`
}

export interface SourceFormValues {
  name: string
  url: string
  status: ProxySourceStatus
  vendor: ProxySourceVendor
}

export const EMPTY_FORM: SourceFormValues = {
  name: '',
  url: '',
  status: DEFAULT_STATUS,
  vendor: DEFAULT_VENDOR,
}

export function formValuesFrom(source: ProxySource): SourceFormValues {
  return { name: source.name, url: source.url, status: source.status, vendor: source.vendor }
}

export type SourceFormErrors = Partial<Record<'name' | 'url', string>>

/**
 * Проверяем то же, что и бекенд (`AddProxySourceRequestSerializer`), только
 * заранее — чтобы не гонять заведомо невалидную форму по сети.
 */
export function validateSourceForm(values: SourceFormValues): SourceFormErrors {
  const errors: SourceFormErrors = {}

  const name = values.name.trim()
  if (!name) {
    errors.name = 'Укажите название источника'
  } else if (name.length > SOURCE_NAME_MAX_LENGTH) {
    errors.name = `Слишком длинное название: максимум ${SOURCE_NAME_MAX_LENGTH} символов`
  }

  const url = values.url.trim()
  if (!url) {
    errors.url = 'Укажите адрес источника'
  } else if (url.length > SOURCE_URL_MAX_LENGTH) {
    errors.url = `Слишком длинный адрес: максимум ${SOURCE_URL_MAX_LENGTH} символов`
  } else if (!isHttpUrl(url)) {
    errors.url = 'Адрес должен начинаться с http:// или https://'
  }

  return errors
}

/** Бекенд ждёт `HttpUrl`, поэтому другие схемы отсекаем сразу. */
export function isHttpUrl(value: string): boolean {
  let parsed: URL
  try {
    parsed = new URL(value)
  } catch {
    return false
  }
  return parsed.protocol === 'http:' || parsed.protocol === 'https:'
}

export function hasErrors(errors: SourceFormErrors): boolean {
  return Object.keys(errors).length > 0
}

/**
 * Что реально изменилось в форме редактирования: PATCH принимает только те поля,
 * которые нужно поменять, поэтому неизменённые не отправляем.
 */
export function changedFields(source: ProxySource, values: SourceFormValues): Partial<SourceFormValues> {
  const changes: Partial<SourceFormValues> = {}
  const name = values.name.trim()
  const url = values.url.trim()

  if (name !== source.name) {
    changes.name = name
  }
  if (url !== source.url) {
    changes.url = url
  }
  if (values.status !== source.status) {
    changes.status = values.status
  }
  if (values.vendor !== source.vendor) {
    changes.vendor = values.vendor
  }

  return changes
}
