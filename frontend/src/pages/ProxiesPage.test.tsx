import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ProxiesPage from './ProxiesPage'
import {
  API_ERROR_CODES,
  ApiRequestError,
  createProxies,
  deleteAllProxies,
  deleteProxy,
  fetchProxies,
  fetchRawProxies,
  updateAllProxies,
  updateProxy,
} from '../api/proxies'
import type { ProxiesPageResult, TelegramProxy } from '../api/proxies'

/**
 * Сетевой слой мокаем целиком, но настоящие ApiRequestError и API_ERROR_CODES
 * оставляем: компонент различает ошибки именно по ним.
 */
vi.mock('../api/proxies', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/proxies')>()
  return {
    ...actual,
    fetchProxies: vi.fn(),
    fetchRawProxies: vi.fn(),
    createProxies: vi.fn(),
    updateAllProxies: vi.fn(),
    deleteAllProxies: vi.fn(),
    deleteProxy: vi.fn(),
    updateProxy: vi.fn(),
  }
})

const proxyOne: TelegramProxy = {
  id: 1,
  name: 'Первая прокси',
  url: 'https://t.me/proxy?server=1',
  created_at: '2024-05-01T10:00:00Z',
  updated_at: null,
  status: 'enabled',
  latency: 120,
}

const proxyTwo: TelegramProxy = {
  id: 2,
  name: 'Вторая прокси',
  url: 'https://t.me/proxy?server=2',
  created_at: '2024-05-02T10:00:00Z',
  updated_at: '2024-05-03T10:00:00Z',
  status: 'enabled',
  latency: null,
}

function pageResult(over: Partial<ProxiesPageResult> = {}): ProxiesPageResult {
  return {
    items: [proxyOne, proxyTwo],
    pagination: { next_page: '/api/proxies?limit=10&offset=10', previous_page: null },
    counters: { total: 42, active: 30 },
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

  vi.mocked(fetchProxies).mockResolvedValue(pageResult())
  vi.mocked(fetchRawProxies).mockResolvedValue(['https://t.me/a', 'https://t.me/b'])
  vi.mocked(createProxies).mockResolvedValue([])
  vi.mocked(updateAllProxies).mockResolvedValue(undefined)
  vi.mocked(deleteAllProxies).mockResolvedValue(undefined)
  vi.mocked(deleteProxy).mockResolvedValue(undefined)
  vi.mocked(updateProxy).mockResolvedValue(proxyOne)
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
  it('успешное добавление показывает тост и перезагружает список', async () => {
    vi.mocked(createProxies).mockResolvedValue([proxyOne, proxyTwo])
    const user = await renderLoadedPage()
    const callsBefore = vi.mocked(fetchProxies).mock.calls.length

    await user.click(screen.getByTitle('Добавить прокси'))

    expect(await screen.findByText('Добавлено проксей: 2')).toBeInTheDocument()
    await waitFor(() =>
      expect(vi.mocked(fetchProxies).mock.calls.length).toBeGreaterThan(callsBefore),
    )
  })

  it('пустой ответ трактуется как «нечего добавлять», а не как ошибка', async () => {
    vi.mocked(createProxies).mockResolvedValue([])
    const user = await renderLoadedPage()

    await user.click(screen.getByTitle('Добавить прокси'))

    expect(await screen.findByText('Новых прокси не нашлось')).toBeInTheDocument()
  })

  it('ошибка NoProxiesAddedError показывается спокойным info-тостом', async () => {
    vi.mocked(createProxies).mockRejectedValue(
      new ApiRequestError('No proxies added', 400, API_ERROR_CODES.noProxiesAdded),
    )
    const user = await renderLoadedPage()

    await user.click(screen.getByTitle('Добавить прокси'))

    expect(await screen.findByText('Новых прокси не нашлось')).toBeInTheDocument()
  })

  it('прочие ошибки показываются как ошибка', async () => {
    vi.mocked(createProxies).mockRejectedValue(new ApiRequestError('Источник недоступен', 502))
    const user = await renderLoadedPage()

    await user.click(screen.getByTitle('Добавить прокси'))

    expect(await screen.findByText('Источник недоступен')).toBeInTheDocument()
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

  it('«Обновить прокси» дёргает POST /api/proxies/status', async () => {
    const user = await renderLoadedPage()

    await user.click(screen.getByTitle('Перепроверить все прокси'))

    await waitFor(() => expect(updateAllProxies).toHaveBeenCalledTimes(1))
    expect(await screen.findByText('Прокси обновлены')).toBeInTheDocument()
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
})

describe('действия над строкой', () => {
  it('кнопка обновления просит бекенд перепинговать прокси', async () => {
    vi.mocked(updateProxy).mockResolvedValue({ ...proxyOne, latency: 90 })
    const user = await renderLoadedPage()

    await user.click(screen.getByLabelText('Перепроверить прокси #1'))

    await waitFor(() => expect(updateProxy).toHaveBeenCalledWith(1, { isLatencyUpdate: true }))
    expect(await screen.findByText('Прокси «Первая прокси» проверена: 90 мс')).toBeInTheDocument()
    expect(screen.getByText('90 мс')).toBeInTheDocument()
  })

  it('смена статуса шлёт PATCH и перезагружает список, если строка выпала из фильтра', async () => {
    vi.mocked(updateProxy).mockResolvedValue({ ...proxyOne, status: 'disabled' })
    const user = await renderLoadedPage()
    const callsBefore = vi.mocked(fetchProxies).mock.calls.length

    await user.selectOptions(screen.getByLabelText('Статус прокси #1'), 'disabled')

    await waitFor(() => expect(updateProxy).toHaveBeenCalledWith(1, { status: 'disabled' }))
    expect(await screen.findByText('Прокси «Первая прокси»: статус — Неактивен')).toBeInTheDocument()
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
