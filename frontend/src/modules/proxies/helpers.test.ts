import { describe, expect, it } from 'vitest'

import type { TelegramProxy } from './api'
import {
  addFromSourcesLabel,
  ariaSortFor,
  buildPageItems,
  DEFAULT_PROXIES_QUERY,
  DEFAULT_SORT,
  emptyProxiesHint,
  filteredTotalFor,
  fromOrderBy,
  keepExistingSourceIds,
  latencyTone,
  nextSortState,
  parseProxiesQuery,
  proxyLabel,
  serializeProxiesQuery,
  sortGlyph,
  SORT_FIELD_LABELS,
  SORT_OPTIONS,
  sourceLabel,
  toggleSourceId,
  toOrderBy,
  UNKNOWN_SOURCE_LABEL,
} from './helpers'

const base: TelegramProxy = {
  id: 42,
  name: '',
  url: 'https://t.me/proxy',
  source_name: null,
  created_at: '2024-05-01T10:00:00Z',
  updated_at: null,
  last_active_at: null,
  status: 'enabled',
  latency: null,
}

describe('сортировка', () => {
  it('toOrderBy добавляет суффикс _desc только для убывания', () => {
    expect(toOrderBy({ field: 'latency', direction: 'asc' })).toBe('latency')
    expect(toOrderBy({ field: 'latency', direction: 'desc' })).toBe('latency_desc')
    expect(toOrderBy({ field: 'created_at', direction: 'asc' })).toBe('created_at')
    expect(toOrderBy({ field: 'created_at', direction: 'desc' })).toBe('created_at_desc')
    expect(toOrderBy({ field: 'last_active_at', direction: 'asc' })).toBe('last_active_at')
    expect(toOrderBy({ field: 'last_active_at', direction: 'desc' })).toBe('last_active_at_desc')
  })

  it('order_by по последней активности разбирается обратно в состояние сортировки', () => {
    expect(fromOrderBy('last_active_at')).toEqual({ field: 'last_active_at', direction: 'asc' })
    expect(fromOrderBy('last_active_at_desc')).toEqual({ field: 'last_active_at', direction: 'desc' })
  })

  it('обе сортировки по последней активности предлагаются в выпадашке тулбара', () => {
    // На узких экранах шапки таблицы нет, и выпадашка — единственный способ переключить колонку.
    expect(SORT_OPTIONS.map((option) => option.value)).toContain('last_active_at')
    expect(SORT_OPTIONS.map((option) => option.value)).toContain('last_active_at_desc')
  })

  it('у каждой сортируемой колонки есть подпись для заголовка таблицы', () => {
    expect(SORT_FIELD_LABELS.last_active_at).toBe('последней активности')
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

describe('proxyLabel', () => {
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

describe('sourceLabel', () => {
  it('показывает название источника из ответа бекенда', () => {
    expect(sourceLabel({ ...base, source_name: 'MTProto list' })).toBe('MTProto list')
  })

  it('без источника подставляет понятную заглушку', () => {
    expect(sourceLabel(base)).toBe(UNKNOWN_SOURCE_LABEL)
  })

  it('обрезает слишком длинное название', () => {
    expect(sourceLabel({ ...base, source_name: 'и'.repeat(60) })).toBe(`${'и'.repeat(48)}…`)
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

  it('при поиске по имени размер выборки неизвестен', () => {
    // Счётчики бекенда считаются по всей базе, под подстроку из них не подобраться.
    expect(filteredTotalFor('all', 100, 30, 'alpha')).toBeNull()
    expect(filteredTotalFor('enabled', 100, 30, 'alpha')).toBeNull()
  })

  it('пустой поиск на счётчики не влияет', () => {
    expect(filteredTotalFor('all', 100, 30, '')).toBe(100)
  })
})

describe('emptyProxiesHint', () => {
  it('про поиск по имени говорит в первую очередь', () => {
    expect(emptyProxiesHint({ status: 'enabled', name: 'alpha' })).toContain('«alpha»')
  })

  it('слишком длинный запрос в подсказке обрезает', () => {
    expect(emptyProxiesHint({ status: 'all', name: 'я'.repeat(40) })).toContain(`«${'я'.repeat(32)}…»`)
  })

  it('без поиска подсказывает про фильтр по статусу', () => {
    expect(emptyProxiesHint({ status: 'disabled', name: '' })).toBe('Попробуйте изменить фильтр по статусу.')
  })

  it('без поиска и без фильтра предлагает добавить прокси', () => {
    expect(emptyProxiesHint({ status: 'all', name: '' })).toContain('Добавить прокси')
  })
})

describe('выбор источников', () => {
  it('toggleSourceId добавляет id в конец и убирает повторный', () => {
    expect(toggleSourceId([], 3)).toEqual([3])
    expect(toggleSourceId([1, 2], 3)).toEqual([1, 2, 3])
    expect(toggleSourceId([1, 2, 3], 2)).toEqual([1, 3])
  })

  it('toggleSourceId не мутирует исходный список', () => {
    const selected = [1, 2]

    toggleSourceId(selected, 3)

    expect(selected).toEqual([1, 2])
  })

  it('addFromSourcesLabel различает пустой выбор и отмеченные источники', () => {
    expect(addFromSourcesLabel(0)).toBe('Добавить из всех')
    expect(addFromSourcesLabel(2)).toBe('Добавить из выбранных (2)')
  })

  it('keepExistingSourceIds выкидывает пропавшие источники', () => {
    expect(keepExistingSourceIds([1, 2, 3], [2, 3, 4])).toEqual([2, 3])
    expect(keepExistingSourceIds([1, 2], [])).toEqual([])
  })
})

describe('parseProxiesQuery', () => {
  it('читает полный набор параметров из адреса', () => {
    expect(parseProxiesQuery('?limit=25&offset=50&status=disabled&order_by=created_at_desc')).toEqual({
      limit: 25,
      offset: 50,
      status: 'disabled',
      name: '',
      sort: { field: 'created_at', direction: 'desc' },
    })
  })

  it('пустой адрес даёт состояние по умолчанию', () => {
    expect(parseProxiesQuery('')).toEqual(DEFAULT_PROXIES_QUERY)
  })

  it('принимает и строку, и готовые URLSearchParams', () => {
    expect(parseProxiesQuery(new URLSearchParams('offset=20'))).toEqual(
      parseProxiesQuery('?offset=20'),
    )
  })

  it('размер страницы берёт только из списка вариантов', () => {
    expect(parseProxiesQuery('?limit=25').limit).toBe(25)
    expect(parseProxiesQuery('?limit=7').limit).toBe(DEFAULT_PROXIES_QUERY.limit)
    expect(parseProxiesQuery('?limit=много').limit).toBe(DEFAULT_PROXIES_QUERY.limit)
  })

  it('отрицательный и нечисловой offset считает нулевым', () => {
    expect(parseProxiesQuery('?offset=-10').offset).toBe(0)
    expect(parseProxiesQuery('?offset=abc').offset).toBe(0)
  })

  it('округляет offset вниз до кратного размеру страницы', () => {
    // Иначе подсветка номера страницы разъехалась бы с реальной выборкой.
    expect(parseProxiesQuery('?offset=25').offset).toBe(20)
    expect(parseProxiesQuery('?limit=25&offset=60').offset).toBe(50)
  })

  it('неизвестные статус и сортировку заменяет значениями по умолчанию', () => {
    expect(parseProxiesQuery('?status=broken').status).toBe(DEFAULT_PROXIES_QUERY.status)
    expect(parseProxiesQuery('?order_by=name').sort).toEqual(DEFAULT_SORT)
  })

  it('поиск по имени читает как есть, обрезая только пробелы по краям', () => {
    // Регистр и середину строки не трогаем: бекенд ищет подстроку без учёта регистра.
    expect(parseProxiesQuery('?name=Alpha+Proxy').name).toBe('Alpha Proxy')
    expect(parseProxiesQuery('?name=++alpha++').name).toBe('alpha')
  })

  it('отсутствующий и пустой поиск дают одно и то же', () => {
    expect(parseProxiesQuery('').name).toBe('')
    expect(parseProxiesQuery('?name=').name).toBe('')
    expect(parseProxiesQuery('?name=+++').name).toBe('')
  })

  it('слишком длинный поиск обрезает', () => {
    // В базе имя прокси — varchar(200), искать по более длинной строке бессмысленно.
    expect(parseProxiesQuery(`?name=${'я'.repeat(250)}`).name).toBe('я'.repeat(200))
  })

  it('не спотыкается о чужие параметры в адресе', () => {
    expect(parseProxiesQuery('?utm_source=telegram&offset=10')).toEqual({
      ...DEFAULT_PROXIES_QUERY,
      offset: 10,
    })
  })
})

describe('serializeProxiesQuery', () => {
  it('на состоянии по умолчанию оставляет адрес чистым', () => {
    expect(serializeProxiesQuery(DEFAULT_PROXIES_QUERY)).toBe('')
  })

  it('пишет только то, что отличается от умолчания', () => {
    expect(serializeProxiesQuery({ ...DEFAULT_PROXIES_QUERY, offset: 20 })).toBe('offset=20')
  })

  it('собирает параметры в том же порядке, что и запрос к API', () => {
    expect(
      serializeProxiesQuery({
        limit: 25,
        offset: 50,
        status: 'disabled',
        name: '',
        sort: { field: 'created_at', direction: 'desc' },
      }),
    ).toBe('limit=25&offset=50&status=disabled&order_by=created_at_desc')
  })

  it('поиск по имени пишет в адрес только когда он задан', () => {
    expect(serializeProxiesQuery({ ...DEFAULT_PROXIES_QUERY, name: 'alpha' })).toBe('name=alpha')
    expect(serializeProxiesQuery({ ...DEFAULT_PROXIES_QUERY, name: '' })).toBe('')
  })

  it('разбор и сборка обратны друг другу', () => {
    const search = 'limit=50&offset=100&status=all&name=alpha&order_by=latency_desc'

    expect(serializeProxiesQuery(parseProxiesQuery(search))).toBe(search)
  })
})
