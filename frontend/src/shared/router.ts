import { useEffect, useSyncExternalStore } from 'react'

/**
 * Мини-роутер на History API.
 *
 * Страниц две, поэтому полноценный роутер избыточен: здесь нужно ровно то, чтобы
 * `/proxies` и `/proxies/sources` открывались по прямой ссылке, работали «назад/вперёд»
 * и адрес менялся при переключении вкладок.
 *
 * Кроме пути роутер отдаёт и query-строку: состояние списка (страница, фильтр,
 * сортировка) живёт в адресе, чтобы ссылку можно было скопировать, открыть в новой
 * вкладке и править прямо в адресной строке браузера.
 *
 * Прямой заход на вложенный путь требует SPA-fallback на раздаче статики:
 * в dev это делает сам Vite, в проде — `try_files $uri $uri/ /index.html` в nginx.
 */

/** Пути страниц. Адрес — часть публичного контракта, поэтому объявлен в одном месте. */
export const ROUTES = {
  proxies: '/proxies',
  sources: '/proxies/sources',
} as const

export type RouteName = keyof typeof ROUTES
export type RoutePath = (typeof ROUTES)[RouteName]

/** Куда уезжают корень и любой неизвестный путь. */
export const DEFAULT_ROUTE: RouteName = 'proxies'

/** Событие своей навигации: `history.pushState` ничего не эмитит, а подписчикам нужно узнать о смене адреса. */
const NAVIGATION_EVENT = 'tpc:navigation'

const ROUTE_BY_PATH = new Map<string, RouteName>(
  (Object.entries(ROUTES) as [RouteName, RoutePath][]).map(([name, path]) => [path, name]),
)

/** Отрезает query/hash и хвостовые слеши: `/proxies/sources/?a=1` и `/proxies/sources` — один путь. */
export function normalizePath(pathname: string): string {
  const [path = ''] = pathname.split(/[?#]/)
  const trimmed = path.replace(/\/+$/, '')
  return trimmed === '' ? '/' : trimmed
}

/**
 * Приводит query к тому же виду, в каком его отдаёт `window.location.search`:
 * пустая строка либо `?a=1`. Так строки можно сравнивать напрямую.
 */
export function normalizeSearch(search: string | URLSearchParams): string {
  const raw = typeof search === 'string' ? search : search.toString()
  const trimmed = raw.replace(/^\?/, '')
  return trimmed === '' ? '' : `?${trimmed}`
}

/** Имя страницы по пути или `null`, если такой страницы нет. */
export function matchRoute(pathname: string): RouteName | null {
  return ROUTE_BY_PATH.get(normalizePath(pathname)) ?? null
}

function currentPath(): string {
  return normalizePath(window.location.pathname)
}

function currentSearch(): string {
  return window.location.search
}

function emitNavigation(): void {
  window.dispatchEvent(new Event(NAVIGATION_EVENT))
}

/** Кладёт адрес в историю и оповещает подписчиков. */
function writeUrl(url: string, replace: boolean): void {
  if (replace) {
    window.history.replaceState({}, '', url)
  } else {
    window.history.pushState({}, '', url)
  }
  emitNavigation()
}

export interface NavigateOptions {
  /** Заменить текущую запись в истории вместо добавления новой. */
  replace?: boolean
  /** Query-строка целевой страницы. По умолчанию пустая: переход между вкладками сбрасывает фильтры. */
  search?: string | URLSearchParams
}

/**
 * Переход на страницу без перезагрузки.
 *
 * @param path путь целевой страницы (`ROUTES.proxies` / `ROUTES.sources`).
 */
export function navigate(path: RoutePath, { replace = false, search = '' }: NavigateOptions = {}): void {
  const nextSearch = normalizeSearch(search)
  if (path === currentPath() && nextSearch === currentSearch()) {
    return
  }
  writeUrl(`${path}${nextSearch}`, replace)
}

export interface SetSearchOptions {
  /**
   * Заменить текущую запись в истории вместо добавления новой.
   * Нужно для «причёсывания» адреса при заходе: приведение к канону — не то,
   * куда пользователь захочет вернуться кнопкой «назад».
   */
  replace?: boolean
}

/**
 * Меняет только query текущей страницы, путь остаётся прежним.
 *
 * По умолчанию добавляет запись в историю: смена страницы списка или фильтра —
 * осознанное действие пользователя, и «назад» должно его отменять.
 */
export function setSearch(search: string | URLSearchParams, { replace = false }: SetSearchOptions = {}): void {
  const nextSearch = normalizeSearch(search)
  if (nextSearch === currentSearch()) {
    return
  }
  writeUrl(`${window.location.pathname}${nextSearch}`, replace)
}

function subscribe(onStoreChange: () => void): () => void {
  // popstate — кнопки «назад/вперёд», NAVIGATION_EVENT — наши собственные переходы.
  window.addEventListener('popstate', onStoreChange)
  window.addEventListener(NAVIGATION_EVENT, onStoreChange)
  return () => {
    window.removeEventListener('popstate', onStoreChange)
    window.removeEventListener(NAVIGATION_EVENT, onStoreChange)
  }
}

/** Активная страница. Корень и неизвестные пути молча заменяются на `/proxies`. */
export function useRoute(): RouteName {
  const path = useSyncExternalStore(subscribe, currentPath, () => ROUTES[DEFAULT_ROUTE])
  const matched = matchRoute(path)

  useEffect(() => {
    if (matched === null) {
      // Именно replace: «назад» не должен возвращать пользователя на несуществующий адрес.
      navigate(ROUTES[DEFAULT_ROUTE], { replace: true })
    }
  }, [matched])

  return matched ?? DEFAULT_ROUTE
}

/**
 * Текущая query-строка (`''` или `'?a=1'`).
 *
 * Возвращается именно строка, а не `URLSearchParams`: снапшот для
 * `useSyncExternalStore` обязан быть сравнимым по `Object.is`.
 */
export function useSearch(): string {
  return useSyncExternalStore(subscribe, currentSearch, () => '')
}
