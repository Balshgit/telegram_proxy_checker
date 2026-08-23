import { useEffect, useSyncExternalStore } from 'react'

/**
 * Мини-роутер на History API.
 *
 * Страниц две, поэтому полноценный роутер избыточен: здесь нужно ровно то, чтобы
 * `/proxies` и `/proxies/sources` открывались по прямой ссылке, работали «назад/вперёд»
 * и адрес менялся при переключении вкладок.
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

/** Событие своей навигации: `history.pushState` ничего не эмитит, а подписчикам нужно узнать о смене пути. */
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

/** Имя страницы по пути или `null`, если такой страницы нет. */
export function matchRoute(pathname: string): RouteName | null {
  return ROUTE_BY_PATH.get(normalizePath(pathname)) ?? null
}

function currentPath(): string {
  return normalizePath(window.location.pathname)
}

/**
 * Переход на страницу без перезагрузки.
 *
 * @param path путь целевой страницы (`ROUTES.proxies` / `ROUTES.sources`).
 * @param replace заменить текущую запись в истории вместо добавления новой.
 */
export function navigate(path: RoutePath, { replace = false }: { replace?: boolean } = {}): void {
  if (path === currentPath()) {
    return
  }
  if (replace) {
    window.history.replaceState({}, '', path)
  } else {
    window.history.pushState({}, '', path)
  }
  window.dispatchEvent(new Event(NAVIGATION_EVENT))
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
