/**
 * Чистые (не завязанные на React) хелперы страницы со списком прокси.
 *
 * Вынесены из `ProxiesPage.tsx` отдельным модулем, чтобы их можно было
 * покрыть unit-тестами без рендера всего компонента.
 */

import { truncate } from '../../shared/ui/format'
import type { ProxyOrderBy, ProxyStatus, TelegramProxy } from './api'

export const PAGE_SIZE_OPTIONS = [10, 25, 50, 100]

/** Колонки таблицы, по которым бекенд умеет сортировать (GET /api/proxies, `order_by`). */
export type SortField = 'latency' | 'created_at'
export type SortDirection = 'asc' | 'desc'

export interface SortState {
  field: SortField
  direction: SortDirection
}

/** Сортировка по умолчанию — то же, что бекенд подставляет сам: латенси по возрастанию. */
export const DEFAULT_SORT: SortState = { field: 'latency', direction: 'asc' }

/** Собирает значение `order_by` из состояния сортировки: `asc` — без суффикса, `desc` — с `_desc`. */
export function toOrderBy({ field, direction }: SortState): ProxyOrderBy {
  return (direction === 'desc' ? `${field}_desc` : field) as ProxyOrderBy
}

/**
 * Клик по заголовку: та же колонка — переворачиваем направление,
 * новая — начинаем с возрастания (быстрые/старые сверху).
 */
export function nextSortState(current: SortState, field: SortField): SortState {
  if (current.field !== field) {
    return { field, direction: 'asc' }
  }
  return { field, direction: current.direction === 'asc' ? 'desc' : 'asc' }
}

/** Стрелка в заголовке: у активной колонки — направление, у остальных — нейтральный знак. */
export function sortGlyph(current: SortState, field: SortField): string {
  if (current.field !== field) {
    return '↕'
  }
  return current.direction === 'asc' ? '↑' : '↓'
}

/** Значение `aria-sort` для `<th>`. */
export function ariaSortFor(current: SortState, field: SortField): 'ascending' | 'descending' | 'none' {
  if (current.field !== field) {
    return 'none'
  }
  return current.direction === 'asc' ? 'ascending' : 'descending'
}

export const SORT_FIELD_LABELS: Record<SortField, string> = {
  latency: 'пингу',
  created_at: 'дате создания',
}

/** Разбирает `order_by` обратно в состояние сортировки (обратная операция к `toOrderBy`). */
export function fromOrderBy(value: ProxyOrderBy): SortState {
  const suffix = '_desc'
  return value.endsWith(suffix)
    ? { field: value.slice(0, -suffix.length) as SortField, direction: 'desc' }
    : { field: value as SortField, direction: 'asc' }
}

/*
 * На узких экранах шапка таблицы скрыта (список превращается в карточки),
 * поэтому кликнуть по заголовку для сортировки нельзя — тот же набор
 * вариантов дублируется выпадающим списком в тулбаре.
 */
export const SORT_OPTIONS: { value: ProxyOrderBy; label: string }[] = [
  { value: 'latency', label: 'Пинг ↑' },
  { value: 'latency_desc', label: 'Пинг ↓' },
  { value: 'created_at', label: 'Создан ↑' },
  { value: 'created_at_desc', label: 'Создан ↓' },
]

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

/* ------------------------------------------------------------------ *
 * Состояние списка в адресной строке
 * ------------------------------------------------------------------ */

/**
 * Что из состояния страницы живёт в query-строке адреса.
 *
 * Смысл — в переносимости: такую ссылку можно скинуть, положить в закладки,
 * открыть в новой вкладке и поправить прямо в адресной строке браузера.
 */
export interface ProxiesQuery {
  limit: number
  offset: number
  status: StatusFilter
  sort: SortState
}

/**
 * Имена параметров намеренно совпадают с query GET /api/proxies:
 * адрес страницы читается как запрос к API, и запомнить нужно один набор имён,
 * а не два. Отсюда `proxy_status`, а не просто `status`.
 */
export const PROXIES_QUERY_KEYS = {
  limit: 'limit',
  offset: 'offset',
  status: 'proxy_status',
  orderBy: 'order_by',
} as const

/** Состояние при заходе на голый `/proxies`. Эти значения в адрес не пишутся. */
export const DEFAULT_PROXIES_QUERY: ProxiesQuery = {
  limit: PAGE_SIZE_OPTIONS[0],
  offset: 0,
  status: 'enabled',
  sort: DEFAULT_SORT,
}

function toParams(search: string | URLSearchParams): URLSearchParams {
  return typeof search === 'string' ? new URLSearchParams(search) : search
}

/** Размер страницы — только из списка вариантов: произвольное число бекенд отдаст, а выпадашка показать не сможет. */
function parseLimit(raw: string | null): number {
  const value = Number(raw)
  return PAGE_SIZE_OPTIONS.includes(value) ? value : DEFAULT_PROXIES_QUERY.limit
}

/**
 * Смещение округляем вниз до кратного `limit`: пагинация оперирует номерами
 * страниц, и «половинчатый» offset из адреса разъехался бы с подсветкой страницы.
 */
function parseOffset(raw: string | null, limit: number): number {
  const value = Number(raw)
  if (!Number.isFinite(value) || value <= 0) {
    return 0
  }
  const offset = Math.floor(value)
  return offset - (offset % limit)
}

function parseStatus(raw: string | null): StatusFilter {
  return STATUS_FILTERS.some((filter) => filter.value === raw)
    ? (raw as StatusFilter)
    : DEFAULT_PROXIES_QUERY.status
}

function parseSort(raw: string | null): SortState {
  return SORT_OPTIONS.some((option) => option.value === raw)
    ? fromOrderBy(raw as ProxyOrderBy)
    : DEFAULT_PROXIES_QUERY.sort
}

/** Разбирает адрес в состояние страницы. Мусор и опечатки молча заменяются значениями по умолчанию. */
export function parseProxiesQuery(search: string | URLSearchParams): ProxiesQuery {
  const params = toParams(search)
  const limit = parseLimit(params.get(PROXIES_QUERY_KEYS.limit))

  return {
    limit,
    offset: parseOffset(params.get(PROXIES_QUERY_KEYS.offset), limit),
    status: parseStatus(params.get(PROXIES_QUERY_KEYS.status)),
    sort: parseSort(params.get(PROXIES_QUERY_KEYS.orderBy)),
  }
}

/**
 * Собирает query-строку из состояния.
 *
 * Значения по умолчанию опускаем: на первой странице с обычными настройками
 * адрес остаётся коротким `/proxies`, а в строке видно ровно то, что пользователь
 * поменял руками.
 */
export function serializeProxiesQuery(query: ProxiesQuery): string {
  const params = new URLSearchParams()

  if (query.limit !== DEFAULT_PROXIES_QUERY.limit) {
    params.set(PROXIES_QUERY_KEYS.limit, String(query.limit))
  }
  if (query.offset !== DEFAULT_PROXIES_QUERY.offset) {
    params.set(PROXIES_QUERY_KEYS.offset, String(query.offset))
  }
  if (query.status !== DEFAULT_PROXIES_QUERY.status) {
    params.set(PROXIES_QUERY_KEYS.status, query.status)
  }

  const orderBy = toOrderBy(query.sort)
  if (orderBy !== toOrderBy(DEFAULT_PROXIES_QUERY.sort)) {
    params.set(PROXIES_QUERY_KEYS.orderBy, orderBy)
  }

  return params.toString()
}

/**
 * Штатный ответ бекенда «нечего добавлять»: в источниках не нашлось ни одной
 * прокси, которой ещё нет в базе. Это не ошибка, поэтому показываем спокойный
 * info-тост, а не красный «что-то сломалось».
 */
export const NOTHING_TO_ADD_TOAST = {
  text: 'Новых прокси не нашлось',
  hint: 'Источники не отдали ничего, чего ещё нет в списке. Загляните позже — список пополняется.',
} as const

/** Подпись под именем прокси: из какого источника она приехала. */
export const UNKNOWN_SOURCE_LABEL = 'Источник неизвестен'

/** Тексты выпадашки выбора источников у кнопки «Добавить прокси». */
export const SOURCE_PICKER = {
  title: 'Собрать из источников',
  /** Пустой выбор = «обойти все включённые источники», как и трактует пустой `source_ids` бекенд. */
  hint: 'Ничего не выбрано — прокси соберутся из всех включённых источников',
  empty: 'Включённых источников нет. Добавьте их на странице «Источники».',
  loadError: 'Не удалось загрузить источники',
} as const

/** Добавляет/убирает id в выборе источников, сохраняя порядок отметки. */
export function toggleSourceId(selected: number[], sourceId: number): number[] {
  return selected.includes(sourceId)
    ? selected.filter((id) => id !== sourceId)
    : [...selected, sourceId]
}

/** Подпись кнопки в выпадашке: явно говорит, сколько источников будет опрошено. */
export function addFromSourcesLabel(selectedCount: number): string {
  return selectedCount === 0 ? 'Добавить из всех' : `Добавить из выбранных (${selectedCount})`
}

/**
 * Отсекает из выбора источники, которых больше нет в списке.
 *
 * Список источников перечитывается при каждом открытии выпадашки, и за это время
 * источник могли удалить или выключить — отправлять его id на бекенд бессмысленно.
 */
export function keepExistingSourceIds(selected: number[], availableIds: number[]): number[] {
  const available = new Set(availableIds)
  return selected.filter((id) => available.has(id))
}

export function sourceLabel(proxy: TelegramProxy): string {
  return proxy.source_name ? truncate(proxy.source_name, 48) : UNKNOWN_SOURCE_LABEL
}

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
