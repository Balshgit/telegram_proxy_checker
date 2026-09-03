import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ProxiesPage from './ProxiesPage'
import {
  ApiRequestError,
  createProxies,
  deleteAllProxies,
  deleteProxy,
  fetchProxies,
  fetchProxy,
  fetchRawProxies,
  updateAllProxies,
  updateProxy,
} from './api'
import type { ProxiesPageResult, TelegramProxy } from './api'
import { fetchProxiesSources } from '../proxies-sources/api'
import type { ProxySource } from '../proxies-sources/api'
import { SHARE_PAGE, UNKNOWN_SOURCE_LABEL } from './helpers'

/**
 * Сетевой слой мокаем целиком, но настоящий ApiRequestError оставляем:
 * компонент отличает ошибки бекенда именно по нему.
 */
vi.mock('./api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./api')>()
  return {
    ...actual,
    fetchProxies: vi.fn(),
    fetchProxy: vi.fn(),
    fetchRawProxies: vi.fn(),
    createProxies: vi.fn(),
    updateAllProxies: vi.fn(),
    deleteAllProxies: vi.fn(),
    deleteProxy: vi.fn(),
    updateProxy: vi.fn(),
  }
})

/** Выпадашка выбора источников в тулбаре тянет их из соседнего модуля. */
vi.mock('../proxies-sources/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../proxies-sources/api')>()
  return { ...actual, fetchProxiesSources: vi.fn() }
})

const githubSource: ProxySource = {
  id: 7,
  // Имя намеренно отличается от `source_name` проксей в таблице,
  // иначе поиск по тексту не различал бы строку списка и пункт выпадашки.
  name: 'Источник GitHub',
  url: 'https://raw.githubusercontent.com/owner/repo/main/list.txt',
  status: 'enabled',
  vendor: 'GitHub',
  created_at: '2024-05-01T10:00:00Z',
  updated_at: null,
  proxies_count: 120,
  active_proxies_count: 34,
}

const backupSource: ProxySource = {
  id: 9,
  name: 'Резервный список',
  url: 'https://example.com/proxies.txt',
  status: 'enabled',
  vendor: 'external',
  created_at: '2024-05-02T10:00:00Z',
  updated_at: null,
  proxies_count: 5,
  active_proxies_count: 1,
}

const proxyOne: TelegramProxy = {
  id: 1,
  name: 'Первая прокси',
  url: 'https://t.me/proxy?server=1',
  source_name: 'MTProto list',
  created_at: '2024-05-01T10:00:00Z',
  updated_at: null,
  status: 'enabled',
  latency: 120,
}

const proxyTwo: TelegramProxy = {
  id: 2,
  name: 'Вторая прокси',
  url: 'https://t.me/proxy?server=2',
  source_name: null,
  created_at: '2024-05-02T10:00:00Z',
  updated_at: '2024-05-03T10:00:00Z',
  status: 'enabled',
  latency: null,
}

/** Готовая строка «поделиться» из ответа бекенда — ровно прокси текущей страницы. */
const SHARE_TEXT = `${proxyOne.url}\n${proxyTwo.url}`

function pageResult(over: Partial<ProxiesPageResult> = {}): ProxiesPageResult {
  return {
    items: [proxyOne, proxyTwo],
    pagination: { next_page: '/api/proxies?limit=10&offset=10', previous_page: null },
    counters: { total: 42, active: 30 },
    share: SHARE_TEXT,
    ...over,
  }
}

const writeText = vi.fn(async (_text: string) => {})

/**
 * jsdom не реализует Clipboard API, поэтому подменяем его сами.
 *
 * Важно: `userEvent.setup()` тоже ставит свою заглушку на `navigator.clipboard`,
 * поэтому наш стаб нужно ставить строго ПОСЛЕ setup, иначе спай затрётся.
 */
function stubClipboard() {
  Object.defineProperty(navigator, 'clipboard', {
    value: { writeText },
    configurable: true,
    writable: true,
  })
}

/** userEvent.setup() + наша заглушка буфера обмена поверх его собственной. */
function setupUser() {
  const user = userEvent.setup()
  stubClipboard()
  return user
}

beforeEach(() => {
  stubClipboard()
  // Состояние списка живёт в адресе, поэтому каждый тест начинает с чистого `/proxies`.
  window.history.replaceState({}, '', '/proxies')

  vi.mocked(fetchProxies).mockResolvedValue(pageResult())
  vi.mocked(fetchProxy).mockResolvedValue(proxyOne)
  vi.mocked(fetchRawProxies).mockResolvedValue(['https://t.me/a', 'https://t.me/b'])
  vi.mocked(createProxies).mockResolvedValue('created')
  vi.mocked(updateAllProxies).mockResolvedValue(undefined)
  vi.mocked(deleteAllProxies).mockResolvedValue(undefined)
  vi.mocked(deleteProxy).mockResolvedValue(undefined)
  vi.mocked(updateProxy).mockResolvedValue(undefined)
  vi.mocked(fetchProxiesSources).mockResolvedValue([githubSource, backupSource])
})

/** Рендерит страницу и дожидается, пока прогрузится первая порция данных. */
async function renderLoadedPage() {
  const user = setupUser()
  render(<ProxiesPage />)
  await screen.findByText('Первая прокси')
  return user
}

/** Аргументы последнего вызова fetchProxies. */
function lastFetchArgs() {
  return vi.mocked(fetchProxies).mock.calls.at(-1)?.[0]
}

/**
 * «Удалить все прокси» спрятано в меню «⋯»: сначала открываем меню,
 * потом возвращаем пункт из него.
 */
async function openMoreMenu(user: ReturnType<typeof setupUser>) {
  await user.click(screen.getByLabelText('Ещё действия'))
  return within(screen.getByRole('menu')).getByRole('menuitem', { name: /Удалить все прокси/u })
}

describe('загрузка списка', () => {
  it('показывает строки таблицы и счётчики', async () => {
    await renderLoadedPage()

    expect(screen.getByText('Вторая прокси')).toBeInTheDocument()
    expect(screen.getByText('120 мс')).toBeInTheDocument()

    const allCard = screen.getByLabelText('Скопировать все прокси в буфер обмена')
    const activeCard = screen.getByLabelText('Скопировать активные прокси в буфер обмена')
    expect(within(allCard).getByText('42')).toBeInTheDocument()
    expect(within(activeCard).getByText('30')).toBeInTheDocument()
  })

  it('под именем прокси показывает источник, из которого она получена', async () => {
    await renderLoadedPage()

    expect(screen.getByText('MTProto list')).toBeInTheDocument()
    // У второй прокси источника нет — вместо пустоты понятная заглушка.
    expect(screen.getByText(UNKNOWN_SOURCE_LABEL)).toBeInTheDocument()
  })

  it('по умолчанию запрашивает только активные прокси', async () => {
    await renderLoadedPage()

    expect(lastFetchArgs()).toMatchObject({ limit: 10, offset: 0, status: 'enabled' })
  })

  it('фильтр «Все» снимает ограничение по статусу', async () => {
    const user = await renderLoadedPage()

    await user.click(screen.getByRole('button', { name: 'Все' }))

    await waitFor(() => expect(lastFetchArgs()).toMatchObject({ status: null, offset: 0 }))
  })

  it('смена размера страницы сбрасывает offset', async () => {
    const user = await renderLoadedPage()

    await user.selectOptions(screen.getByLabelText('Элементов на странице'), '25')

    await waitFor(() => expect(lastFetchArgs()).toMatchObject({ limit: 25, offset: 0 }))
  })

  it('показывает пустое состояние, когда прокси нет', async () => {
    vi.mocked(fetchProxies).mockResolvedValue(
      pageResult({
        items: [],
        pagination: { next_page: null, previous_page: null },
        counters: { total: 0, active: 0 },
      }),
    )

    render(<ProxiesPage />)

    expect(await screen.findByText('Прокси не найдены')).toBeInTheDocument()
  })

  it('показывает ошибку загрузки и повторяет запрос по кнопке', async () => {
    vi.mocked(fetchProxies).mockRejectedValue(new ApiRequestError('Бекенд недоступен', 0))
    const user = setupUser()

    render(<ProxiesPage />)

    expect(await screen.findByText('Не удалось загрузить список')).toBeInTheDocument()
    expect(screen.getByText('Бекенд недоступен')).toBeInTheDocument()

    vi.mocked(fetchProxies).mockResolvedValue(pageResult())
    await user.click(screen.getByRole('button', { name: 'Повторить' }))

    expect(await screen.findByText('Первая прокси')).toBeInTheDocument()
  })
})

describe('добавление прокси', () => {
  it('успешное добавление показывает тост и перезагружает список (ответ 201 приходит без тела)', async () => {
    vi.mocked(createProxies).mockResolvedValue('created')
    const user = await renderLoadedPage()
    const callsBefore = vi.mocked(fetchProxies).mock.calls.length

    await user.click(screen.getByTitle('Добавить прокси'))

    expect(await screen.findByText('Прокси добавлены')).toBeInTheDocument()
    await waitFor(() =>
      expect(vi.mocked(fetchProxies).mock.calls.length).toBeGreaterThan(callsBefore),
    )
  })

  it('исход «нечего добавлять» показывается спокойным info-тостом и список не трогает', async () => {
    vi.mocked(createProxies).mockResolvedValue('nothing-to-add')
    const user = await renderLoadedPage()
    const callsBefore = vi.mocked(fetchProxies).mock.calls.length

    await user.click(screen.getByTitle('Добавить прокси'))

    expect(await screen.findByText('Новых прокси не нашлось')).toBeInTheDocument()
    expect(vi.mocked(fetchProxies).mock.calls.length).toBe(callsBefore)
  })

  it('прочие ошибки показываются как ошибка', async () => {
    vi.mocked(createProxies).mockRejectedValue(new ApiRequestError('Источник недоступен', 502))
    const user = await renderLoadedPage()

    await user.click(screen.getByTitle('Добавить прокси'))

    expect(await screen.findByText('Источник недоступен')).toBeInTheDocument()
  })

  it('обычный клик собирает прокси из всех включённых источников', async () => {
    const user = await renderLoadedPage()

    await user.click(screen.getByTitle('Добавить прокси'))

    await waitFor(() => expect(createProxies).toHaveBeenCalledWith({ sourceIds: [] }))
    // Список источников для этого не нужен — лишнего запроса быть не должно.
    expect(fetchProxiesSources).not.toHaveBeenCalled()
  })
})

describe('выбор источников для добавления', () => {
  /** Открывает выпадашку у кнопки «Добавить прокси» и дожидается списка источников. */
  async function openSourcePicker(user: ReturnType<typeof setupUser>) {
    await user.click(screen.getByLabelText('Выбрать источники'))
    const picker = await screen.findByRole('dialog', { name: 'Собрать из источников' })
    await within(picker).findByText('Источник GitHub')
    return picker
  }

  it('выпадашка закрыта по умолчанию и открывается кнопкой «▾»', async () => {
    const user = await renderLoadedPage()

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()

    const picker = await openSourcePicker(user)

    // Показываем только включённые источники: выключенные бекенд всё равно не опрашивает.
    expect(fetchProxiesSources).toHaveBeenCalledWith({ status: 'enabled' })
    expect(within(picker).getByText('Резервный список')).toBeInTheDocument()
  })

  it('шлёт id только отмеченных источников', async () => {
    const user = await renderLoadedPage()
    const picker = await openSourcePicker(user)

    await user.click(within(picker).getByRole('checkbox', { name: /Резервный список/u }))
    await user.click(within(picker).getByRole('button', { name: 'Добавить из выбранных (1)' }))

    await waitFor(() => expect(createProxies).toHaveBeenCalledWith({ sourceIds: [backupSource.id] }))
    expect(await screen.findByText('Прокси добавлены')).toBeInTheDocument()
    // После добавления выпадашка закрывается.
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('без отметок кнопка добавляет из всех источников', async () => {
    const user = await renderLoadedPage()
    const picker = await openSourcePicker(user)

    expect(
      within(picker).getByText('Ничего не выбрано — прокси соберутся из всех включённых источников'),
    ).toBeInTheDocument()

    await user.click(within(picker).getByRole('button', { name: 'Добавить из всех' }))

    await waitFor(() => expect(createProxies).toHaveBeenCalledWith({ sourceIds: [] }))
  })

  it('повторный клик по чекбоксу снимает отметку', async () => {
    const user = await renderLoadedPage()
    const picker = await openSourcePicker(user)

    const checkbox = within(picker).getByRole('checkbox', { name: /Источник GitHub/u })
    await user.click(checkbox)
    expect(checkbox).toBeChecked()

    await user.click(checkbox)
    expect(checkbox).not.toBeChecked()
    expect(within(picker).getByRole('button', { name: 'Добавить из всех' })).toBeInTheDocument()
  })

  it('ошибку загрузки источников показывает прямо в выпадашке', async () => {
    vi.mocked(fetchProxiesSources).mockRejectedValue(new ApiRequestError('Бекенд недоступен', 503))
    const user = await renderLoadedPage()

    await user.click(screen.getByLabelText('Выбрать источники'))

    expect(await screen.findByText('Бекенд недоступен')).toBeInTheDocument()
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
  })

  it('когда включённых источников нет — подсказывает, где их завести', async () => {
    vi.mocked(fetchProxiesSources).mockResolvedValue([])
    const user = await renderLoadedPage()

    await user.click(screen.getByLabelText('Выбрать источники'))

    expect(
      await screen.findByText('Включённых источников нет. Добавьте их на странице «Источники».'),
    ).toBeInTheDocument()
  })

  it('закрывается по Escape', async () => {
    const user = await renderLoadedPage()
    await openSourcePicker(user)

    await user.keyboard('{Escape}')

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })
})

describe('массовые действия', () => {
  it('«Удалить все прокси» не висит в тулбаре, а лежит в меню «⋯»', async () => {
    const user = await renderLoadedPage()

    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
    expect(screen.queryByText('Удалить все прокси')).not.toBeInTheDocument()

    await openMoreMenu(user)

    expect(screen.getByRole('menu')).toBeInTheDocument()
  })

  it('удаление всех прокси требует подтверждения', async () => {
    const user = await renderLoadedPage()

    await user.click(await openMoreMenu(user))
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(deleteAllProxies).not.toHaveBeenCalled()

    await user.click(screen.getByRole('button', { name: 'Удалить всё' }))

    await waitFor(() => expect(deleteAllProxies).toHaveBeenCalledTimes(1))
    expect(await screen.findByText('Все прокси удалены')).toBeInTheDocument()
  })

  it('отмена в модалке ничего не удаляет', async () => {
    const user = await renderLoadedPage()

    await user.click(await openMoreMenu(user))
    await user.click(screen.getByRole('button', { name: 'Отмена' }))

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(deleteAllProxies).not.toHaveBeenCalled()
  })

  it('«Обновить прокси» дёргает POST /api/proxies/status и перезагружает список', async () => {
    const user = await renderLoadedPage()
    const callsBefore = vi.mocked(fetchProxies).mock.calls.length

    await user.click(screen.getByTitle('Перепроверить все прокси'))

    await waitFor(() => expect(updateAllProxies).toHaveBeenCalledTimes(1))
    expect(await screen.findByText('Прокси обновлены')).toBeInTheDocument()
    await waitFor(() =>
      expect(vi.mocked(fetchProxies).mock.calls.length).toBeGreaterThan(callsBefore),
    )
  })
})

describe('копирование в буфер обмена', () => {
  it('карточка «Всего» копирует все прокси', async () => {
    const user = await renderLoadedPage()

    await user.click(screen.getByLabelText('Скопировать все прокси в буфер обмена'))

    await waitFor(() => expect(fetchRawProxies).toHaveBeenCalledWith({ status: null }))
    expect(writeText).toHaveBeenCalledWith('https://t.me/a\nhttps://t.me/b')
    expect(await screen.findByText('Скопировано в буфер обмена, прокси: 2')).toBeInTheDocument()
  })

  it('карточка «Активных» копирует только enabled', async () => {
    const user = await renderLoadedPage()

    await user.click(screen.getByLabelText('Скопировать активные прокси в буфер обмена'))

    await waitFor(() => expect(fetchRawProxies).toHaveBeenCalledWith({ status: 'enabled' }))
  })

  it('на пустой выборке показывает info-тост и ничего не копирует', async () => {
    vi.mocked(fetchRawProxies).mockResolvedValue([])
    const user = await renderLoadedPage()

    await user.click(screen.getByLabelText('Скопировать активные прокси в буфер обмена'))

    expect(await screen.findByText('Активных прокси нет')).toBeInTheDocument()
    expect(writeText).not.toHaveBeenCalled()
  })

  it('копирует ссылку отдельной прокси', async () => {
    const user = await renderLoadedPage()

    await user.click(screen.getByLabelText('Скопировать ссылку прокси #1'))

    await waitFor(() => expect(writeText).toHaveBeenCalledWith(proxyOne.url))
  })

  it('«Поделиться страницей» копирует proxies_share и не ходит в сеть', async () => {
    const user = await renderLoadedPage()

    await user.click(screen.getByLabelText(SHARE_PAGE.title))

    await waitFor(() => expect(writeText).toHaveBeenCalledWith(SHARE_TEXT))
    expect(fetchRawProxies).not.toHaveBeenCalled()
    expect(await screen.findByText(SHARE_PAGE.success)).toBeInTheDocument()
  })

  it('без proxies_share кнопка «Поделиться страницей» выключена', async () => {
    vi.mocked(fetchProxies).mockResolvedValue(pageResult({ share: '' }))
    await renderLoadedPage()

    expect(screen.getByLabelText(SHARE_PAGE.title)).toBeDisabled()
  })
})

describe('действия над строкой', () => {
  it('после PATCH строка дочитывается через GET /api/proxies/{id}, а не весь список', async () => {
    vi.mocked(fetchProxy).mockResolvedValue({ ...proxyOne, latency: 90 })
    const user = await renderLoadedPage()
    const callsBefore = vi.mocked(fetchProxies).mock.calls.length

    await user.click(screen.getByLabelText('Перепроверить прокси #1'))

    await waitFor(() => expect(updateProxy).toHaveBeenCalledWith(1, { isLatencyUpdate: true }))
    await waitFor(() => expect(fetchProxy).toHaveBeenCalledWith(1))
    expect(await screen.findByText('Прокси «Первая прокси» проверена: 90 мс')).toBeInTheDocument()
    expect(screen.getByText('90 мс')).toBeInTheDocument()
    // Список целиком не перезагружали — обновили только строку.
    expect(vi.mocked(fetchProxies).mock.calls.length).toBe(callsBefore)
  })

  it('смена статуса шлёт PATCH и перезагружает список, если строка выпала из фильтра', async () => {
    vi.mocked(fetchProxy).mockResolvedValue({ ...proxyOne, status: 'disabled' })
    const user = await renderLoadedPage()
    const callsBefore = vi.mocked(fetchProxies).mock.calls.length

    await user.selectOptions(screen.getByLabelText('Статус прокси #1'), 'disabled')

    await waitFor(() => expect(updateProxy).toHaveBeenCalledWith(1, { status: 'disabled' }))
    expect(await screen.findByText('Прокси «Первая прокси»: статус — Неактивен')).toBeInTheDocument()
    await waitFor(() =>
      expect(vi.mocked(fetchProxies).mock.calls.length).toBeGreaterThan(callsBefore),
    )
  })

  it('если прокси после обновления не нашлась, перезагружает список целиком', async () => {
    vi.mocked(fetchProxy).mockResolvedValue(null)
    const user = await renderLoadedPage()
    const callsBefore = vi.mocked(fetchProxies).mock.calls.length

    await user.click(screen.getByLabelText('Перепроверить прокси #1'))

    await waitFor(() =>
      expect(vi.mocked(fetchProxies).mock.calls.length).toBeGreaterThan(callsBefore),
    )
  })

  it('ошибка обновления строки показывается тостом', async () => {
    vi.mocked(updateProxy).mockRejectedValue(new ApiRequestError('Прокси не найдена', 404))
    const user = await renderLoadedPage()

    await user.click(screen.getByLabelText('Перепроверить прокси #1'))

    expect(await screen.findByText('Прокси не найдена')).toBeInTheDocument()
  })

  it('удаление одной прокси требует подтверждения и шлёт DELETE', async () => {
    const user = await renderLoadedPage()
    const callsBefore = vi.mocked(fetchProxies).mock.calls.length

    await user.click(screen.getByLabelText('Удалить прокси #1'))

    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(deleteProxy).not.toHaveBeenCalled()

    await user.click(screen.getByRole('button', { name: 'Удалить' }))

    await waitFor(() => expect(deleteProxy).toHaveBeenCalledWith(1))
    expect(await screen.findByText('Прокси «Первая прокси» удалена')).toBeInTheDocument()
    await waitFor(() =>
      expect(vi.mocked(fetchProxies).mock.calls.length).toBeGreaterThan(callsBefore),
    )
  })

  it('отмена в модалке не удаляет прокси', async () => {
    const user = await renderLoadedPage()

    await user.click(screen.getByLabelText('Удалить прокси #2'))
    await user.click(screen.getByRole('button', { name: 'Отмена' }))

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(deleteProxy).not.toHaveBeenCalled()
  })

  it('ошибка удаления показывается тостом', async () => {
    vi.mocked(deleteProxy).mockRejectedValue(new ApiRequestError('Прокси не найдена', 404))
    const user = await renderLoadedPage()

    await user.click(screen.getByLabelText('Удалить прокси #1'))
    await user.click(screen.getByRole('button', { name: 'Удалить' }))

    expect(await screen.findByText('Прокси не найдена')).toBeInTheDocument()
  })
})

describe('сортировка', () => {
  it('по умолчанию просит бекенд сортировать по латенси по возрастанию', async () => {
    await renderLoadedPage()

    expect(lastFetchArgs()).toMatchObject({ orderBy: 'latency' })
  })

  it('клик по «Пинг» переворачивает направление', async () => {
    const user = await renderLoadedPage()

    await user.click(screen.getByRole('button', { name: /Пинг/u }))

    await waitFor(() => expect(lastFetchArgs()).toMatchObject({ orderBy: 'latency_desc', offset: 0 }))
  })

  it('клик по «Создан» переключает колонку и начинает с возрастания', async () => {
    const user = await renderLoadedPage()

    await user.click(screen.getByRole('button', { name: /Создан/u }))

    await waitFor(() => expect(lastFetchArgs()).toMatchObject({ orderBy: 'created_at' }))

    await user.click(screen.getByRole('button', { name: /Создан/u }))

    await waitFor(() => expect(lastFetchArgs()).toMatchObject({ orderBy: 'created_at_desc' }))
  })

  it('смена сортировки сбрасывает страницу на первую', async () => {
    const user = await renderLoadedPage()

    await user.click(screen.getByLabelText('Следующая страница'))
    await waitFor(() => expect(lastFetchArgs()).toMatchObject({ offset: 10 }))

    await user.click(screen.getByRole('button', { name: /Пинг/u }))

    await waitFor(() => expect(lastFetchArgs()).toMatchObject({ offset: 0, orderBy: 'latency_desc' }))
  })
})

describe('состояние в адресной строке', () => {
  /** Открывает страницу по конкретному адресу и дожидается первой порции данных. */
  async function renderAt(url: string) {
    window.history.replaceState({}, '', url)
    return renderLoadedPage()
  }

  it('на первой странице с настройками по умолчанию адрес остаётся чистым', async () => {
    await renderLoadedPage()

    expect(window.location.search).toBe('')
  })

  it('переход по страницам пишет offset в адрес', async () => {
    const user = await renderLoadedPage()

    await user.click(screen.getByLabelText('Страница 3'))

    await waitFor(() => expect(window.location.search).toBe('?offset=20'))
  })

  it('фильтр, размер страницы и сортировка складываются в один адрес', async () => {
    const user = await renderLoadedPage()

    await user.selectOptions(screen.getByLabelText('Элементов на странице'), '25')
    await user.click(screen.getByRole('button', { name: 'Все' }))
    await user.selectOptions(screen.getByLabelText('Сортировка списка'), 'created_at_desc')

    await waitFor(() =>
      expect(window.location.search).toBe('?limit=25&proxy_status=all&order_by=created_at_desc'),
    )
  })

  it('прямая ссылка с параметрами сразу уходит в запрос к бекенду', async () => {
    await renderAt('/proxies?limit=25&offset=50&proxy_status=disabled&order_by=created_at_desc')

    expect(lastFetchArgs()).toMatchObject({
      limit: 25,
      offset: 50,
      status: 'disabled',
      orderBy: 'created_at_desc',
    })
    // Адрес валидный — переписывать его не за чем.
    expect(window.location.search).toBe(
      '?limit=25&offset=50&proxy_status=disabled&order_by=created_at_desc',
    )
  })

  it('прямая ссылка подсвечивает нужную страницу пагинации', async () => {
    await renderAt('/proxies?offset=20')

    expect(screen.getByLabelText('Страница 3')).toHaveAttribute('aria-current', 'page')
  })

  it('мусор и значения по умолчанию из адреса вычищаются', async () => {
    await renderAt('/proxies?limit=7&offset=abc&proxy_status=broken&utm_source=telegram')

    await waitFor(() => expect(window.location.search).toBe(''))
    expect(lastFetchArgs()).toMatchObject({ limit: 10, offset: 0, status: 'enabled' })
  })

  it('кнопка «назад» возвращает предыдущую страницу списка', async () => {
    const user = await renderLoadedPage()

    await user.click(screen.getByLabelText('Следующая страница'))
    await waitFor(() => expect(window.location.search).toBe('?offset=10'))

    window.history.back()

    await waitFor(() => expect(window.location.search).toBe(''))
    await waitFor(() => expect(lastFetchArgs()).toMatchObject({ offset: 0 }))
  })
})

describe('пагинация', () => {
  it('кнопка «Вперёд» увеличивает offset на размер страницы', async () => {
    const user = await renderLoadedPage()

    await user.click(screen.getByLabelText('Следующая страница'))

    await waitFor(() => expect(lastFetchArgs()).toMatchObject({ offset: 10, limit: 10 }))
  })

  it('переход по номеру страницы считает offset от номера', async () => {
    const user = await renderLoadedPage()

    await user.click(screen.getByLabelText('Страница 3'))

    await waitFor(() => expect(lastFetchArgs()).toMatchObject({ offset: 20 }))
  })

  it('на первой странице кнопки «назад» недоступны', async () => {
    await renderLoadedPage()

    expect(screen.getByLabelText('Первая страница')).toBeDisabled()
    expect(screen.getByLabelText('Предыдущая страница')).toBeDisabled()
  })

  it('показывает диапазон видимых записей', async () => {
    await renderLoadedPage()

    expect(screen.getByText(/Показано 1–2 из 30/u)).toBeInTheDocument()
  })
})
