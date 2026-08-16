/**
 * Чистые (не завязанные на React) хелперы страницы со списком прокси.
 *
 * Вынесены из `ProxiesPage.tsx` отдельным модулем, чтобы их можно было
 * покрыть unit-тестами без рендера всего компонента.
 */

import type { ProxyStatus, TelegramProxy } from '../api/proxies'

export const PAGE_SIZE_OPTIONS = [10, 25, 50, 100]

/** Сколько соседних страниц показываем слева и справа от текущей. */
export const PAGE_WINDOW = 2
/** До этого количества страниц список выводим целиком, без многоточий. */
export const PAGES_WITHOUT_GAPS = 7

/** Элемент пагинации: либо номер страницы, либо «…» (ключи разные, чтобы React не ругался). */
export type PageItem = number | 'gap-start' | 'gap-end'

export type StatusFilter = ProxyStatus | 'all'

/**
 * Какую выборку копируем карточкой-счётчиком:
 * `all` — все прокси, `active` — только со статусом `enabled`.
 */
export type CopyScope = 'all' | 'active'

export const COPY_SCOPE_STATUS: Record<CopyScope, ProxyStatus | null> = {
  all: null,
  active: 'enabled',
}

export const COPY_SCOPE_EMPTY_TEXT: Record<CopyScope, string> = {
  all: 'Список прокси пуст',
  active: 'Активных прокси нет',
}

export const STATUS_LABELS: Record<ProxyStatus, string> = {
  enabled: 'Активен',
  disabled: 'Неактивен',
}

export const STATUS_OPTIONS: ProxyStatus[] = ['enabled', 'disabled']

export const STATUS_FILTERS: { value: StatusFilter; label: string }[] = [
  { value: 'all', label: 'Все' },
  { value: 'enabled', label: 'Активные' },
  { value: 'disabled', label: 'Неактивные' },
]

/**
 * Штатный ответ бекенда «нечего добавлять»: в источнике не нашлось ни одной
 * прокси, которой ещё нет в базе. Это не ошибка, поэтому показываем спокойный
 * info-тост, а не красный «что-то сломалось».
 */
export const NOTHING_TO_ADD_TOAST = {
  text: 'Новых прокси не нашлось',
  hint: 'Источник не отдал ничего, чего ещё нет в списке. Загляните позже — список пополняется.',
} as const

/**
 * Собирает список страниц вида «1 … 4 5 6 … 20»:
 * первая и последняя всегда на месте, вокруг текущей — окно из соседей.
 */
export function buildPageItems(currentPage: number, totalPages: number): PageItem[] {
  if (totalPages <= PAGES_WITHOUT_GAPS) {
    return Array.from({ length: totalPages }, (_, index) => index + 1)
  }

  const items: PageItem[] = [1]
  const from = Math.max(2, currentPage - PAGE_WINDOW)
  const to = Math.min(totalPages - 1, currentPage + PAGE_WINDOW)

  if (from > 2) {
    items.push('gap-start')
  }
  for (let page = from; page <= to; page += 1) {
    items.push(page)
  }
  if (to < totalPages - 1) {
    items.push('gap-end')
  }
  items.push(totalPages)

  return items
}

export function formatDate(value: string | null): string {
  if (!value) {
    return '—'
  }
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }
  return new Intl.DateTimeFormat('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

export function latencyTone(latency: number | null): string {
  if (latency == null) {
    return 'none'
  }
  if (latency < 300) {
    return 'good'
  }
  if (latency < 1000) {
    return 'medium'
  }
  return 'bad'
}

export function truncate(value: string, max: number): string {
  return value.length > max ? `${value.slice(0, max)}…` : value
}

/** Как называть прокси в тостах и подписях: по имени, а если его нет — по id. */
export function proxyLabel(proxy: TelegramProxy): string {
  return proxy.name ? `«${truncate(proxy.name, 32)}»` : `#${proxy.id}`
}

/**
 * Считает размер текущей выборки: бекенд отдаёт счётчики по всей базе
 * (`total`) и по активным (`active`), без учёта выбранного фильтра.
 */
export function filteredTotalFor(statusFilter: StatusFilter, total: number, activeCount: number): number {
  if (statusFilter === 'enabled') {
    return activeCount
  }
  if (statusFilter === 'disabled') {
    return Math.max(0, total - activeCount)
  }
  return total
}

/**
 * Копирование с запасным вариантом: `navigator.clipboard` доступен только в
 * secure context (https или localhost), а фронт могут открыть и по http.
 */
export async function copyToClipboard(text: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text)
    return
  }

  const textarea = document.createElement('textarea')
  textarea.value = text
  textarea.setAttribute('readonly', '')
  textarea.style.position = 'fixed'
  textarea.style.opacity = '0'
  document.body.appendChild(textarea)

  try {
    textarea.select()
    if (!document.execCommand('copy')) {
      throw new Error('execCommand("copy") вернул false')
    }
  } finally {
    document.body.removeChild(textarea)
  }
}
