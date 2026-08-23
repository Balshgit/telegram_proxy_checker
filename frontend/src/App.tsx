import type { MouseEvent } from 'react'

import ProxiesPage from './modules/proxies/ProxiesPage'
import SourcesPage from './modules/proxies-sources/SourcesPage'
import { navigate, ROUTES, useRoute } from './shared/router'
import type { RouteName } from './shared/router'

import './App.css'

/**
 * Страниц всего две, поэтому обходимся своим мини-роутером (`shared/router`):
 * активная страница определяется адресом — `/proxies` и `/proxies/sources`.
 */
const PAGES: { value: RouteName; label: string; icon: string }[] = [
  { value: 'proxies', label: 'Прокси', icon: '🛰️' },
  { value: 'sources', label: 'Источники', icon: '⛁' },
]

/** Клик с модификатором или не левой кнопкой — это «открыть в новой вкладке», перехватывать его нельзя. */
function isPlainLeftClick(event: MouseEvent<HTMLAnchorElement>): boolean {
  return event.button === 0 && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey
}

function App() {
  const page = useRoute()

  const nav = (
    <nav className="app-nav" aria-label="Разделы">
      {PAGES.map((item) => (
        // Именно ссылка, а не кнопка: адрес страницы должен быть виден, копируем и открываем в новой вкладке.
        <a
          key={item.value}
          href={ROUTES[item.value]}
          className={`app-nav__item${page === item.value ? ' is-active' : ''}`}
          onClick={(event) => {
            if (!isPlainLeftClick(event)) {
              return
            }
            event.preventDefault()
            navigate(ROUTES[item.value])
          }}
          aria-current={page === item.value ? 'page' : undefined}
        >
          <span aria-hidden="true">{item.icon}</span>
          {item.label}
        </a>
      ))}
    </nav>
  )

  return page === 'proxies' ? <ProxiesPage nav={nav} /> : <SourcesPage nav={nav} />
}

export default App
