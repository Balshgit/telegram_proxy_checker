import { describe, expect, it } from 'vitest'

import { SOURCE_NAME_MAX_LENGTH } from './api'
import type { ProxySource } from './api'
import {
  changedFields,
  DEFAULT_SOURCES_STATUS,
  formValuesFrom,
  hasErrors,
  isHttpUrl,
  parseSourcesStatus,
  serializeSourcesQuery,
  sourceLabel,
  validateSourceForm,
} from './helpers'

const source: ProxySource = {
  id: 7,
  name: 'MTProto list',
  url: 'https://example.com/list.txt',
  status: 'enabled',
  vendor: 'GitHub',
  created_at: '2024-05-01T10:00:00Z',
  updated_at: null,
  proxies_count: 10,
  active_proxies_count: 3,
}

describe('фильтр в адресной строке', () => {
  it('читает статус из адреса', () => {
    expect(parseSourcesStatus('?source_status=enabled')).toBe('enabled')
    expect(parseSourcesStatus(new URLSearchParams('source_status=disabled'))).toBe('disabled')
  })

  it('пустой и мусорный адрес дают значение по умолчанию', () => {
    expect(parseSourcesStatus('')).toBe(DEFAULT_SOURCES_STATUS)
    expect(parseSourcesStatus('?source_status=broken')).toBe(DEFAULT_SOURCES_STATUS)
    expect(parseSourcesStatus('?utm_source=telegram')).toBe(DEFAULT_SOURCES_STATUS)
  })

  it('значение по умолчанию в адрес не пишется', () => {
    expect(serializeSourcesQuery(DEFAULT_SOURCES_STATUS)).toBe('')
    expect(serializeSourcesQuery('enabled')).toBe('source_status=enabled')
  })

  it('разбор и сборка обратны друг другу', () => {
    expect(serializeSourcesQuery(parseSourcesStatus('?source_status=disabled'))).toBe(
      'source_status=disabled',
    )
  })
})

describe('sourceLabel', () => {
  it('использует название, когда оно есть', () => {
    expect(sourceLabel(source)).toBe('«MTProto list»')
  })

  it('падает обратно на id, когда названия нет', () => {
    expect(sourceLabel({ ...source, name: '' })).toBe('#7')
  })
})

describe('isHttpUrl', () => {
  it('принимает http и https', () => {
    expect(isHttpUrl('http://example.com')).toBe(true)
    expect(isHttpUrl('https://example.com/a/b?c=1')).toBe(true)
  })

  it('отвергает другие схемы и мусор', () => {
    expect(isHttpUrl('ftp://example.com')).toBe(false)
    expect(isHttpUrl('example.com')).toBe(false)
    expect(isHttpUrl('')).toBe(false)
  })
})

describe('validateSourceForm', () => {
  const valid = { name: 'Источник', url: 'https://example.com', status: 'enabled', vendor: 'GitHub' } as const

  it('валидную форму пропускает', () => {
    const errors = validateSourceForm(valid)
    expect(hasErrors(errors)).toBe(false)
  })

  it('требует название и адрес', () => {
    const errors = validateSourceForm({ ...valid, name: '   ', url: '' })

    expect(errors.name).toBe('Укажите название источника')
    expect(errors.url).toBe('Укажите адрес источника')
  })

  it('ругается на слишком длинное название — как и бекенд', () => {
    const errors = validateSourceForm({ ...valid, name: 'x'.repeat(SOURCE_NAME_MAX_LENGTH + 1) })

    expect(errors.name).toContain(String(SOURCE_NAME_MAX_LENGTH))
  })

  it('ругается на адрес без http-схемы', () => {
    const errors = validateSourceForm({ ...valid, url: 'ftp://example.com' })

    expect(errors.url).toBe('Адрес должен начинаться с http:// или https://')
  })
})

describe('changedFields', () => {
  it('без изменений отдаёт пустой объект — PATCH слать незачем', () => {
    expect(changedFields(source, formValuesFrom(source))).toEqual({})
  })

  it('собирает только изменённые поля', () => {
    const changes = changedFields(source, { ...formValuesFrom(source), status: 'disabled', name: 'Новое' })

    expect(changes).toEqual({ status: 'disabled', name: 'Новое' })
  })

  it('не считает изменением лишние пробелы вокруг значений', () => {
    const changes = changedFields(source, {
      ...formValuesFrom(source),
      name: '  MTProto list  ',
      url: ' https://example.com/list.txt ',
    })

    expect(changes).toEqual({})
  })
})
