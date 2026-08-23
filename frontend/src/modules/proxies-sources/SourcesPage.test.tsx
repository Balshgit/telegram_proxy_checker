import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import SourcesPage from './SourcesPage'
import {
  ApiRequestError,
  createProxySource,
  deleteProxySource,
  fetchProxiesSources,
  updateProxySource,
} from './api'
import type { ProxySource } from './api'

vi.mock('./api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./api')>()
  return {
    ...actual,
    fetchProxiesSources: vi.fn(),
    createProxySource: vi.fn(),
    updateProxySource: vi.fn(),
    deleteProxySource: vi.fn(),
  }
})

const githubSource: ProxySource = {
  id: 1,
  name: 'MTProto list',
  url: 'https://raw.githubusercontent.com/owner/repo/main/list.txt',
  status: 'enabled',
  vendor: 'GitHub',
  created_at: '2024-05-01T10:00:00Z',
  updated_at: null,
  proxies_count: 120,
  active_proxies_count: 34,
}

const externalSource: ProxySource = {
  id: 2,
  name: 'Резервный список',
  url: 'https://example.com/proxies.txt',
  status: 'disabled',
  vendor: 'external',
  created_at: '2024-05-02T10:00:00Z',
  updated_at: '2024-05-03T10:00:00Z',
  proxies_count: 0,
  active_proxies_count: 0,
}

beforeEach(() => {
  vi.mocked(fetchProxiesSources).mockResolvedValue([githubSource, externalSource])
  vi.mocked(createProxySource).mockResolvedValue(undefined)
  vi.mocked(updateProxySource).mockResolvedValue(undefined)
  vi.mocked(deleteProxySource).mockResolvedValue(undefined)
})

async function renderLoadedPage() {
  const user = userEvent.setup()
  render(<SourcesPage />)
  await screen.findByText('MTProto list')
  return user
}

/** Заполняет поля формы в открытой модалке. */
async function fillForm(
  user: ReturnType<typeof userEvent.setup>,
  { name, url }: { name?: string; url?: string },
) {
  if (name !== undefined) {
    const field = screen.getByLabelText('Название')
    await user.clear(field)
    await user.type(field, name)
  }
  if (url !== undefined) {
    const field = screen.getByLabelText('Адрес')
    await user.clear(field)
    await user.type(field, url)
  }
}

describe('список источников', () => {
  it('показывает источники со статусом, вендором и счётчиками прокси', async () => {
    await renderLoadedPage()

    expect(screen.getByText('Резервный список')).toBeInTheDocument()
    expect(screen.getByText('Включён')).toBeInTheDocument()
    expect(screen.getByText('Выключен')).toBeInTheDocument()
    expect(screen.getByText('GitHub')).toBeInTheDocument()
    expect(screen.getByText('Внешний источник')).toBeInTheDocument()
    expect(screen.getByText('120')).toBeInTheDocument()
  })

  it('по умолчанию запрашивает все источники, фильтр сужает выборку', async () => {
    const user = await renderLoadedPage()

    expect(vi.mocked(fetchProxiesSources).mock.calls.at(-1)?.[0]).toMatchObject({ status: null })

    await user.click(screen.getByRole('button', { name: 'Выключенные' }))

    await waitFor(() =>
      expect(vi.mocked(fetchProxiesSources).mock.calls.at(-1)?.[0]).toMatchObject({
        status: 'disabled',
      }),
    )
  })

  it('показывает пустое состояние, когда источников нет', async () => {
    vi.mocked(fetchProxiesSources).mockResolvedValue([])

    render(<SourcesPage />)

    expect(await screen.findByText('Источники не найдены')).toBeInTheDocument()
  })

  it('показывает ошибку загрузки и повторяет запрос по кнопке', async () => {
    vi.mocked(fetchProxiesSources).mockRejectedValue(new ApiRequestError('Бекенд недоступен', 0))
    const user = userEvent.setup()

    render(<SourcesPage />)

    expect(await screen.findByText('Не удалось загрузить источники')).toBeInTheDocument()

    vi.mocked(fetchProxiesSources).mockResolvedValue([githubSource])
    await user.click(screen.getByRole('button', { name: 'Повторить' }))

    expect(await screen.findByText('MTProto list')).toBeInTheDocument()
  })
})

describe('добавление источника', () => {
  it('шлёт POST и перезагружает список', async () => {
    const user = await renderLoadedPage()
    const callsBefore = vi.mocked(fetchProxiesSources).mock.calls.length

    await user.click(screen.getByTitle('Добавить источник'))
    await fillForm(user, { name: 'Новый источник', url: 'https://example.com/new.txt' })
    await user.click(screen.getByRole('button', { name: 'Добавить' }))

    await waitFor(() =>
      expect(createProxySource).toHaveBeenCalledWith({
        name: 'Новый источник',
        url: 'https://example.com/new.txt',
        status: 'enabled',
        vendor: 'GitHub',
      }),
    )
    expect(await screen.findByText('Источник «Новый источник» добавлен')).toBeInTheDocument()
    await waitFor(() =>
      expect(vi.mocked(fetchProxiesSources).mock.calls.length).toBeGreaterThan(callsBefore),
    )
  })

  it('не отправляет форму с невалидным адресом', async () => {
    const user = await renderLoadedPage()

    await user.click(screen.getByTitle('Добавить источник'))
    await fillForm(user, { name: 'Источник', url: 'просто текст' })
    await user.click(screen.getByRole('button', { name: 'Добавить' }))

    expect(
      await screen.findByText('Адрес должен начинаться с http:// или https://'),
    ).toBeInTheDocument()
    expect(createProxySource).not.toHaveBeenCalled()
  })

  it('ошибку бекенда показывает тостом и модалку не закрывает', async () => {
    vi.mocked(createProxySource).mockRejectedValue(new ApiRequestError('Такой источник уже есть', 409))
    const user = await renderLoadedPage()

    await user.click(screen.getByTitle('Добавить источник'))
    await fillForm(user, { name: 'Источник', url: 'https://example.com/new.txt' })
    await user.click(screen.getByRole('button', { name: 'Добавить' }))

    expect(await screen.findByText('Такой источник уже есть')).toBeInTheDocument()
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })
})

describe('редактирование источника', () => {
  it('открывает модалку с текущими значениями и шлёт только изменённые поля', async () => {
    const user = await renderLoadedPage()

    await user.click(screen.getByLabelText('Редактировать источник #1'))

    expect(screen.getByLabelText('Название')).toHaveValue('MTProto list')
    expect(screen.getByLabelText('Адрес')).toHaveValue(githubSource.url)

    await user.selectOptions(screen.getByLabelText('Статус'), 'disabled')
    await user.click(screen.getByRole('button', { name: 'Сохранить' }))

    await waitFor(() => expect(updateProxySource).toHaveBeenCalledWith(1, { status: 'disabled' }))
    expect(await screen.findByText('Источник «MTProto list» обновлён')).toBeInTheDocument()
  })

  it('без изменений запрос не шлёт', async () => {
    const user = await renderLoadedPage()

    await user.click(screen.getByLabelText('Редактировать источник #1'))
    await user.click(screen.getByRole('button', { name: 'Сохранить' }))

    expect(await screen.findByText('Менять нечего — источник остался прежним')).toBeInTheDocument()
    expect(updateProxySource).not.toHaveBeenCalled()
  })

  it('отмена закрывает модалку без запроса', async () => {
    const user = await renderLoadedPage()

    await user.click(screen.getByLabelText('Редактировать источник #2'))
    await user.click(screen.getByRole('button', { name: 'Отмена' }))

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(updateProxySource).not.toHaveBeenCalled()
  })
})

describe('удаление источника', () => {
  it('требует подтверждения, шлёт DELETE и перезагружает список', async () => {
    const user = await renderLoadedPage()
    const callsBefore = vi.mocked(fetchProxiesSources).mock.calls.length

    await user.click(screen.getByLabelText('Удалить источник #1'))

    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(deleteProxySource).not.toHaveBeenCalled()

    await user.click(screen.getByRole('button', { name: 'Удалить' }))

    await waitFor(() => expect(deleteProxySource).toHaveBeenCalledWith(1))
    expect(await screen.findByText('Источник «MTProto list» удалён')).toBeInTheDocument()
    await waitFor(() =>
      expect(vi.mocked(fetchProxiesSources).mock.calls.length).toBeGreaterThan(callsBefore),
    )
  })

  it('отмена ничего не удаляет', async () => {
    const user = await renderLoadedPage()

    await user.click(screen.getByLabelText('Удалить источник #2'))
    await user.click(screen.getByRole('button', { name: 'Отмена' }))

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(deleteProxySource).not.toHaveBeenCalled()
  })

  it('ошибку удаления показывает тостом', async () => {
    vi.mocked(deleteProxySource).mockRejectedValue(new ApiRequestError('Источник не найден', 404))
    const user = await renderLoadedPage()

    await user.click(screen.getByLabelText('Удалить источник #1'))
    await user.click(screen.getByRole('button', { name: 'Удалить' }))

    expect(await screen.findByText('Источник не найден')).toBeInTheDocument()
  })
})
