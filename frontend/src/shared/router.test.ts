import { beforeEach, describe, expect, it, vi } from 'vitest'

import { matchRoute, navigate, normalizePath, normalizeSearch, ROUTES, setSearch } from './router'

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

  it('переносит на страницу переданную query-строку', () => {
    navigate(ROUTES.sources, { search: 'source_status=enabled' })

    expect(window.location.pathname).toBe('/proxies/sources')
    expect(window.location.search).toBe('?source_status=enabled')
  })

  it('без search сбрасывает параметры прежней страницы', () => {
    window.history.replaceState({}, '', '/proxies?offset=20')

    navigate(ROUTES.sources)

    expect(window.location.search).toBe('')
  })

  it('переход на тот же путь с другим query всё-таки меняет адрес', () => {
    navigate(ROUTES.proxies, { search: 'offset=20' })

    expect(window.location.search).toBe('?offset=20')
  })
})

describe('normalizeSearch', () => {
  it.each([
    ['', ''],
    ['?', ''],
    ['offset=20', '?offset=20'],
    ['?offset=20', '?offset=20'],
  ])('приводит %s к %s', (raw, expected) => {
    expect(normalizeSearch(raw)).toBe(expected)
  })

  it('принимает URLSearchParams', () => {
    expect(normalizeSearch(new URLSearchParams({ offset: '20' }))).toBe('?offset=20')
    expect(normalizeSearch(new URLSearchParams())).toBe('')
  })
})

describe('setSearch', () => {
  beforeEach(() => {
    window.history.replaceState({}, '', ROUTES.proxies)
  })

  it('меняет query, не трогая путь, и оповещает подписчиков', () => {
    const listener = vi.fn()
    window.addEventListener('tpc:navigation', listener)

    setSearch('limit=25&offset=50')

    expect(window.location.pathname).toBe('/proxies')
    expect(window.location.search).toBe('?limit=25&offset=50')
    expect(listener).toHaveBeenCalledTimes(1)

    window.removeEventListener('tpc:navigation', listener)
  })

  it('ничего не делает, если query уже такой', () => {
    window.history.replaceState({}, '', '/proxies?offset=20')
    const listener = vi.fn()
    window.addEventListener('tpc:navigation', listener)

    setSearch('offset=20')

    expect(listener).not.toHaveBeenCalled()

    window.removeEventListener('tpc:navigation', listener)
  })

  it('пустая строка убирает query из адреса', () => {
    window.history.replaceState({}, '', '/proxies?offset=20')

    setSearch('')

    expect(window.location.search).toBe('')
    expect(window.location.pathname).toBe('/proxies')
  })

  it('по умолчанию добавляет запись в историю, с replace — заменяет', () => {
    const pushState = vi.spyOn(window.history, 'pushState')
    const replaceState = vi.spyOn(window.history, 'replaceState')

    setSearch('offset=20')
    expect(pushState).toHaveBeenCalledTimes(1)

    setSearch('offset=40', { replace: true })
    expect(replaceState).toHaveBeenCalledTimes(1)
    expect(pushState).toHaveBeenCalledTimes(1)

    pushState.mockRestore()
    replaceState.mockRestore()
  })
})
