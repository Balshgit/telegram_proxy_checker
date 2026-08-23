import { beforeEach, describe, expect, it, vi } from 'vitest'

import { matchRoute, navigate, normalizePath, ROUTES } from './router'

describe('normalizePath', () => {
  it.each([
    ['/proxies', '/proxies'],
    ['/proxies/', '/proxies'],
    ['/proxies/sources///', '/proxies/sources'],
    ['/proxies/sources?status=enabled', '/proxies/sources'],
    ['/proxies#top', '/proxies'],
    ['/', '/'],
    ['', '/'],
  ])('приводит %s к %s', (raw, expected) => {
    expect(normalizePath(raw)).toBe(expected)
  })
})

describe('matchRoute', () => {
  it('узнаёт страницу проксей', () => {
    expect(matchRoute('/proxies')).toBe('proxies')
  })

  it('узнаёт страницу источников', () => {
    expect(matchRoute('/proxies/sources')).toBe('sources')
  })

  it('не путает источники с прокси по id', () => {
    expect(matchRoute('/proxies/42')).toBeNull()
  })

  it('отдаёт null для корня и неизвестных путей', () => {
    expect(matchRoute('/')).toBeNull()
    expect(matchRoute('/unknown')).toBeNull()
  })
})

describe('navigate', () => {
  beforeEach(() => {
    window.history.replaceState({}, '', ROUTES.proxies)
  })

  it('меняет адрес и оповещает подписчиков', () => {
    const listener = vi.fn()
    window.addEventListener('tpc:navigation', listener)

    navigate(ROUTES.sources)

    expect(window.location.pathname).toBe('/proxies/sources')
    expect(listener).toHaveBeenCalledTimes(1)

    window.removeEventListener('tpc:navigation', listener)
  })

  it('ничего не делает, если уже на этом пути', () => {
    const listener = vi.fn()
    window.addEventListener('tpc:navigation', listener)

    navigate(ROUTES.proxies)

    expect(listener).not.toHaveBeenCalled()

    window.removeEventListener('tpc:navigation', listener)
  })

  it('с replace не добавляет запись в историю', () => {
    const replaceState = vi.spyOn(window.history, 'replaceState')
    const pushState = vi.spyOn(window.history, 'pushState')

    navigate(ROUTES.sources, { replace: true })

    expect(replaceState).toHaveBeenCalledTimes(1)
    expect(pushState).not.toHaveBeenCalled()

    replaceState.mockRestore()
    pushState.mockRestore()
  })
})
