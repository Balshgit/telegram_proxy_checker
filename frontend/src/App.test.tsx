import type { ReactNode } from 'react'

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import App from './App'

/**
 * Сами страницы подменяем заглушками: тест про роутинг, а не про их содержимое,
 * и настоящие страницы полезли бы в сеть за данными.
 */
vi.mock('./modules/proxies/ProxiesPage', () => ({
  default: ({ nav }: { nav?: ReactNode }) => (
    <div>
      {nav}
      <h1>Прокси-страница</h1>
    </div>
  ),
}))

vi.mock('./modules/proxies-sources/SourcesPage', () => ({
  default: ({ nav }: { nav?: ReactNode }) => (
    <div>
      {nav}
      <h1>Страница источников</h1>
    </div>
  ),
}))

function goTo(path: string) {
  window.history.replaceState({}, '', path)
}

describe('App routing', () => {
  beforeEach(() => {
    goTo('/proxies')
  })

  it('открывает прокси по /proxies', () => {
    render(<App />)

    expect(screen.getByRole('heading', { name: 'Прокси-страница' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Прокси/ })).toHaveAttribute('aria-current', 'page')
  })

  it('открывает источники по прямой ссылке /proxies/sources', () => {
    goTo('/proxies/sources')

    render(<App />)

    expect(screen.getByRole('heading', { name: 'Страница источников' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Источники/ })).toHaveAttribute('aria-current', 'page')
  })

  it('открывает источники и с хвостовым слешем', () => {
    goTo('/proxies/sources/')

    render(<App />)

    expect(screen.getByRole('heading', { name: 'Страница источников' })).toBeInTheDocument()
  })

  it.each(['/', '/unknown'])('заменяет %s на /proxies', async (path) => {
    goTo(path)

    render(<App />)

    await waitFor(() => expect(window.location.pathname).toBe('/proxies'))
    expect(screen.getByRole('heading', { name: 'Прокси-страница' })).toBeInTheDocument()
  })

  it('ссылки в навигации ведут на реальные адреса страниц', () => {
    render(<App />)

    expect(screen.getByRole('link', { name: /Прокси/ })).toHaveAttribute('href', '/proxies')
    expect(screen.getByRole('link', { name: /Источники/ })).toHaveAttribute('href', '/proxies/sources')
  })

  it('переключает страницу по клику и меняет адрес', async () => {
    const user = userEvent.setup()

    render(<App />)

    await user.click(screen.getByRole('link', { name: /Источники/ }))

    expect(window.location.pathname).toBe('/proxies/sources')
    expect(screen.getByRole('heading', { name: 'Страница источников' })).toBeInTheDocument()
  })

  it('возвращается назад по кнопке браузера', async () => {
    const user = userEvent.setup()

    render(<App />)

    await user.click(screen.getByRole('link', { name: /Источники/ }))
    expect(screen.getByRole('heading', { name: 'Страница источников' })).toBeInTheDocument()

    window.history.back()

    await waitFor(() => expect(window.location.pathname).toBe('/proxies'))
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Прокси-страница' })).toBeInTheDocument())
  })
})
