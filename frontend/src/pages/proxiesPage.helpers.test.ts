import { afterEach, describe, expect, it, vi } from 'vitest'

import type { TelegramProxy } from '../api/proxies'
import {
  ariaSortFor,
  buildPageItems,
  copyToClipboard,
  DEFAULT_SORT,
  filteredTotalFor,
  formatDate,
  latencyTone,
  nextSortState,
  proxyLabel,
  sortGlyph,
  toOrderBy,
  truncate,
} from './proxiesPage.helpers'

describe('сортировка', () => {
  it('toOrderBy добавляет суффикс _desc только для убывания', () => {
    expect(toOrderBy({ field: 'latency', direction: 'asc' })).toBe('latency')
    expect(toOrderBy({ field: 'latency', direction: 'desc' })).toBe('latency_desc')
    expect(toOrderBy({ field: 'created_at', direction: 'asc' })).toBe('created_at')
    expect(toOrderBy({ field: 'created_at', direction: 'desc' })).toBe('created_at_desc')
  })

  it('по умолчанию сортируем по латенси по возрастанию — как и бекенд', () => {
    expect(toOrderBy(DEFAULT_SORT)).toBe('latency')
  })

  it('nextSortState переворачивает ту же колонку и сбрасывает направление на новой', () => {
    const latencyAsc = { field: 'latency', direction: 'asc' } as const

    expect(nextSortState(latencyAsc, 'latency')).toEqual({ field: 'latency', direction: 'desc' })
    expect(nextSortState({ field: 'latency', direction: 'desc' }, 'latency')).toEqual(latencyAsc)
    expect(nextSortState({ field: 'latency', direction: 'desc' }, 'created_at')).toEqual({
      field: 'created_at',
      direction: 'asc',
    })
  })

  it('sortGlyph и ariaSortFor отмечают только активную колонку', () => {
    const state = { field: 'latency', direction: 'desc' } as const

    expect(sortGlyph(state, 'latency')).toBe('↓')
    expect(sortGlyph(state, 'created_at')).toBe('↕')
    expect(ariaSortFor(state, 'latency')).toBe('descending')
    expect(ariaSortFor({ field: 'latency', direction: 'asc' }, 'latency')).toBe('ascending')
    expect(ariaSortFor(state, 'created_at')).toBe('none')
  })
})

describe('buildPageItems', () => {
  it('до 7 страниц выводит список целиком, без многоточий', () => {
    expect(buildPageItems(1, 1)).toEqual([1])
    expect(buildPageItems(3, 7)).toEqual([1, 2, 3, 4, 5, 6, 7])
  })

  it('в начале списка ставит многоточие только справа', () => {
    expect(buildPageItems(1, 20)).toEqual([1, 2, 3, 'gap-end', 20])
  })

  it('в середине списка ставит многоточия с обеих сторон', () => {
    expect(buildPageItems(10, 20)).toEqual([1, 'gap-start', 8, 9, 10, 11, 12, 'gap-end', 20])
  })

  it('в конце списка ставит многоточие только слева', () => {
    expect(buildPageItems(20, 20)).toEqual([1, 'gap-start', 18, 19, 20])
  })

  it('никогда не дублирует первую и последнюю страницу', () => {
    for (let page = 1; page <= 20; page += 1) {
      const items = buildPageItems(page, 20)
      const numbers = items.filter((item): item is number => typeof item === 'number')
      expect(new Set(numbers).size).toBe(numbers.length)
      expect(numbers[0]).toBe(1)
      expect(numbers.at(-1)).toBe(20)
    }
  })
})

describe('formatDate', () => {
  it('пустое значение показывает прочерком', () => {
    expect(formatDate(null)).toBe('—')
    expect(formatDate('')).toBe('—')
  })

  it('нераспознанную дату возвращает как есть', () => {
    expect(formatDate('не дата')).toBe('не дата')
  })

  it('валидную дату форматирует в ru-RU', () => {
    const formatted = formatDate('2024-05-01T10:30:00Z')
    expect(formatted).toMatch(/^\d{2}\.\d{2}\.2024,?\s\d{2}:\d{2}$/u)
  })
})

describe('latencyTone', () => {
  const cases: [number | null, string][] = [
    [null, 'none'],
    [0, 'good'],
    [299, 'good'],
    [300, 'medium'],
    [999, 'medium'],
    [1000, 'bad'],
    [5000, 'bad'],
  ]

  it.each(cases)('%s мс -> %s', (latency, expected) => {
    expect(latencyTone(latency)).toBe(expected)
  })
})

describe('truncate', () => {
  it('короткую строку не трогает', () => {
    expect(truncate('abc', 5)).toBe('abc')
    expect(truncate('abcde', 5)).toBe('abcde')
  })

  it('длинную обрезает и добавляет многоточие', () => {
    expect(truncate('abcdef', 5)).toBe('abcde…')
  })
})

describe('proxyLabel', () => {
  const base: TelegramProxy = {
    id: 42,
    name: '',
    url: 'https://t.me/proxy',
    created_at: '2024-05-01T10:00:00Z',
    updated_at: null,
    status: 'enabled',
    latency: null,
  }

  it('использует имя, когда оно есть', () => {
    expect(proxyLabel({ ...base, name: 'Ленинград' })).toBe('«Ленинград»')
  })

  it('падает обратно на id, когда имени нет', () => {
    expect(proxyLabel(base)).toBe('#42')
  })

  it('обрезает слишком длинное имя', () => {
    const label = proxyLabel({ ...base, name: 'я'.repeat(40) })
    expect(label).toBe(`«${'я'.repeat(32)}…»`)
  })
})

describe('filteredTotalFor', () => {
  it('для фильтра «Активные» берёт счётчик активных', () => {
    expect(filteredTotalFor('enabled', 100, 30)).toBe(30)
  })

  it('для фильтра «Неактивные» считает разницу и не уходит в минус', () => {
    expect(filteredTotalFor('disabled', 100, 30)).toBe(70)
    expect(filteredTotalFor('disabled', 10, 30)).toBe(0)
  })

  it('для «Все» берёт общий счётчик', () => {
    expect(filteredTotalFor('all', 100, 30)).toBe(100)
  })
})

describe('copyToClipboard', () => {
  afterEach(() => {
    Reflect.deleteProperty(navigator, 'clipboard')
    Reflect.deleteProperty(document, 'execCommand')
  })

  function stubClipboard(writeText: ((text: string) => Promise<void>) | undefined) {
    Object.defineProperty(navigator, 'clipboard', {
      value: writeText ? { writeText } : undefined,
      configurable: true,
      writable: true,
    })
  }

  it('использует navigator.clipboard, когда он доступен', async () => {
    const writeText = vi.fn(async () => {})
    stubClipboard(writeText)

    await copyToClipboard('https://t.me/proxy')

    expect(writeText).toHaveBeenCalledWith('https://t.me/proxy')
    expect(document.querySelector('textarea')).toBeNull()
  })

  it('без Clipboard API падает обратно на execCommand и убирает за собой textarea', async () => {
    stubClipboard(undefined)
    const execCommand = vi.fn(() => true)
    Object.defineProperty(document, 'execCommand', { value: execCommand, configurable: true, writable: true })

    await copyToClipboard('текст')

    expect(execCommand).toHaveBeenCalledWith('copy')
    expect(document.querySelector('textarea')).toBeNull()
  })

  it('бросает ошибку, если execCommand не сработал, и всё равно чистит DOM', async () => {
    stubClipboard(undefined)
    Object.defineProperty(document, 'execCommand', {
      value: vi.fn(() => false),
      configurable: true,
      writable: true,
    })

    await expect(copyToClipboard('текст')).rejects.toThrow('execCommand("copy") вернул false')
    expect(document.querySelector('textarea')).toBeNull()
  })
})
