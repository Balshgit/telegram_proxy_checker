import { useState } from 'react'

import ProxiesPage from './modules/proxies/ProxiesPage'
import SourcesPage from './modules/proxies-sources/SourcesPage'

import './App.css'

/**
 * Страниц всего две, поэтому обходимся без роутера: переключатель хранит
 * активную вкладку в состоянии и рендерит соответствующий модуль.
 */
type Page = 'proxies' | 'sources'

const PAGES: { value: Page; label: string; icon: string }[] = [
  { value: 'proxies', label: 'Прокси', icon: '🛰️' },
  { value: 'sources', label: 'Источники', icon: '⛁' },
]

function App() {
  const [page, setPage] = useState<Page>('proxies')

  const nav = (
    <nav className="app-nav" aria-label="Разделы">
      {PAGES.map((item) => (
        <button
          key={item.value}
          type="button"
          className={`app-nav__item${page === item.value ? ' is-active' : ''}`}
          onClick={() => setPage(item.value)}
          aria-current={page === item.value ? 'page' : undefined}
        >
          <span aria-hidden="true">{item.icon}</span>
          {item.label}
        </button>
      ))}
    </nav>
  )

  return page === 'proxies' ? <ProxiesPage nav={nav} /> : <SourcesPage nav={nav} />
}

export default App
