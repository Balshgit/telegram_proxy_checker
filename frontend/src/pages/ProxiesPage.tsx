import { useCallback, useEffect, useRef, useState } from 'react'

import {
  ApiRequestError,
  createProxies,
  deleteAllProxies,
  fetchProxies,
  updateAllProxies,
  updateProxy,
} from '../api/proxies'
import type { ProxyStatus, TelegramProxy } from '../api/proxies'

import './ProxiesPage.css'

const PAGE_SIZE_OPTIONS = [10, 25, 50, 100]

type StatusFilter = ProxyStatus | 'all'
type PendingAction = 'create' | 'delete' | 'refresh-all' | null
/** Что именно сейчас происходит с конкретной строкой таблицы. */
type RowAction = 'refresh' | 'status'

interface Toast {
  id: number
  kind: 'success' | 'error'
  text: string
}

const STATUS_LABELS: Record<ProxyStatus, string> = {
  enabled: 'Активен',
  disabled: 'Неактивен',
}

const STATUS_OPTIONS: ProxyStatus[] = ['enabled', 'disabled']

const STATUS_FILTERS: { value: StatusFilter; label: string }[] = [
  { value: 'all', label: 'Все' },
  { value: 'enabled', label: 'Активные' },
  { value: 'disabled', label: 'Неактивные' },
]

function parseProxyUrl(url: string): { server: string | null; port: string | null; secret: string | null } {
  const queryIndex = url.indexOf('?')
  if (queryIndex === -1) {
    return { server: null, port: null, secret: null }
  }
  const params = new URLSearchParams(url.slice(queryIndex + 1))
  return {
    server: params.get('server'),
    port: params.get('port'),
    secret: params.get('secret'),
  }
}

function formatDate(value: string | null): string {
  if (!value) {
    return '—'
  }
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }
  return new Intl.DateTimeFormat('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

function latencyTone(latency: number | null): string {
  if (latency == null) {
    return 'none'
  }
  if (latency < 300) {
    return 'good'
  }
  if (latency < 1000) {
    return 'medium'
  }
  return 'bad'
}

function truncate(value: string, max: number): string {
  return value.length > max ? `${value.slice(0, max)}…` : value
}

function ProxiesPage() {
  const [proxies, setProxies] = useState<TelegramProxy[]>([])
  const [total, setTotal] = useState(0)
  const [activeCount, setActiveCount] = useState(0)
  const [hasNextPage, setHasNextPage] = useState(false)

  const [limit, setLimit] = useState(PAGE_SIZE_OPTIONS[0])
  const [offset, setOffset] = useState(0)
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('enabled')

  const [isLoading, setIsLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [pendingAction, setPendingAction] = useState<PendingAction>(null)
  const [isConfirmOpen, setIsConfirmOpen] = useState(false)
  const [copiedId, setCopiedId] = useState<number | null>(null)
  const [rowPending, setRowPending] = useState<Record<number, RowAction>>({})
  const [toasts, setToasts] = useState<Toast[]>([])

  const toastSeq = useRef(0)

  const pushToast = useCallback((kind: Toast['kind'], text: string) => {
    toastSeq.current += 1
    const id = toastSeq.current
    setToasts((current) => [...current, { id, kind, text }])
    window.setTimeout(() => {
      setToasts((current) => current.filter((toast) => toast.id !== id))
    }, 4000)
  }, [])

  const loadProxies = useCallback(
    async (signal?: AbortSignal) => {
      setIsLoading(true)
      setLoadError(null)
      try {
        const page = await fetchProxies({
          limit,
          offset,
          status: statusFilter === 'all' ? null : statusFilter,
          signal,
        })
        if (signal?.aborted) {
          return
        }
        setProxies(page.items)
        setTotal(page.counters.total)
        setActiveCount(page.counters.active)
        setHasNextPage(Boolean(page.pagination.next_page))
      } catch (error) {
        if (signal?.aborted) {
          return
        }
        setProxies([])
        setLoadError(error instanceof ApiRequestError ? error.message : 'Неизвестная ошибка при загрузке проксей')
      } finally {
        if (!signal?.aborted) {
          setIsLoading(false)
        }
      }
    },
    [limit, offset, statusFilter],
  )

  useEffect(() => {
    const controller = new AbortController()
    void loadProxies(controller.signal)
    return () => controller.abort()
  }, [loadProxies])

  const handleAddProxies = useCallback(async () => {
    setPendingAction('create')
    try {
      const created = await createProxies()
      pushToast('success', `Добавлено проксей: ${created.length}`)
      setOffset(0)
      await loadProxies()
    } catch (error) {
      pushToast('error', error instanceof ApiRequestError ? error.message : 'Не удалось добавить прокси')
    } finally {
      setPendingAction(null)
    }
  }, [loadProxies, pushToast])

  /**
   * POST /api/proxies/status — бекенд перепроверяет все прокси,
   * после чего перезагружаем список через GET /api/proxies.
   */
  const handleRefreshAllProxies = useCallback(async () => {
    setPendingAction('refresh-all')
    try {
      await updateAllProxies()
      pushToast('success', 'Прокси обновлены')
      await loadProxies()
    } catch (error) {
      pushToast('error', error instanceof ApiRequestError ? error.message : 'Не удалось обновить прокси')
    } finally {
      setPendingAction(null)
    }
  }, [loadProxies, pushToast])

  const handleDeleteAll = useCallback(async () => {
    setIsConfirmOpen(false)
    setPendingAction('delete')
    try {
      await deleteAllProxies()
      pushToast('success', 'Все прокси удалены')
      setOffset(0)
      await loadProxies()
    } catch (error) {
      pushToast('error', error instanceof ApiRequestError ? error.message : 'Не удалось удалить прокси')
    } finally {
      setPendingAction(null)
    }
  }, [loadProxies, pushToast])

  const handleCopy = useCallback(
    async (proxy: TelegramProxy) => {
      try {
        await navigator.clipboard.writeText(proxy.url)
        setCopiedId(proxy.id)
        window.setTimeout(() => setCopiedId((current) => (current === proxy.id ? null : current)), 1500)
      } catch {
        pushToast('error', 'Не удалось скопировать ссылку')
      }
    },
    [pushToast],
  )

  /**
   * PATCH /api/proxies/{id}: точечно обновляет строку без перезагрузки всей таблицы.
   * Если после обновления прокси перестала подходить под активный фильтр — перезагружаем список.
   */
  const patchProxy = useCallback(
    async (proxy: TelegramProxy, action: RowAction, params: { status?: ProxyStatus; isLatencyUpdate?: boolean }) => {
      setRowPending((current) => ({ ...current, [proxy.id]: action }))
      try {
        const updated = await updateProxy(proxy.id, params)

        if (!updated) {
          await loadProxies()
          return
        }

        if (statusFilter !== 'all' && updated.status !== statusFilter) {
          pushToast('success', `Прокси #${proxy.id}: статус — ${STATUS_LABELS[updated.status]}`)
          await loadProxies()
          return
        }

        setProxies((current) => current.map((item) => (item.id === updated.id ? updated : item)))

        // Строку обновляем точечно, поэтому счётчик активных подправляем вручную.
        if (updated.status !== proxy.status) {
          setActiveCount((current) =>
            updated.status === 'enabled' ? current + 1 : Math.max(0, current - 1),
          )
        }

        pushToast(
          'success',
          action === 'refresh'
            ? `Прокси #${proxy.id} проверена: ${updated.latency == null ? 'нет ответа' : `${updated.latency} мс`}`
            : `Прокси #${proxy.id}: статус — ${STATUS_LABELS[updated.status]}`,
        )
      } catch (error) {
        pushToast(
          'error',
          error instanceof ApiRequestError ? error.message : `Не удалось обновить прокси #${proxy.id}`,
        )
      } finally {
        setRowPending((current) => {
          const next = { ...current }
          delete next[proxy.id]
          return next
        })
      }
    },
    [loadProxies, pushToast, statusFilter],
  )

  /** Кнопка «обновить»: бекенд заново пингует прокси и сам выставляет статус по результату. */
  const handleRefreshProxy = useCallback(
    (proxy: TelegramProxy) => patchProxy(proxy, 'refresh', { isLatencyUpdate: true }),
    [patchProxy],
  )

  const handleStatusChange = useCallback(
    (proxy: TelegramProxy, status: ProxyStatus) => {
      if (status === proxy.status) {
        return
      }
      return patchProxy(proxy, 'status', { status })
    },
    [patchProxy],
  )

  const isBusy = pendingAction !== null
  const currentPage = Math.floor(offset / limit) + 1
  const rangeFrom = proxies.length ? offset + 1 : 0
  const rangeTo = offset + proxies.length

  return (
    <div className="proxies-page">
      <div className="proxies-page__glow" aria-hidden="true" />

      <div className="proxies-page__inner">
        <header className="proxies-header">
          <div>
            <h1 className="proxies-header__title">
              <span className="proxies-header__icon">🛰️</span>
              Список прокси
            </h1>
            <p className="proxies-header__subtitle">
              Telegram-прокси, собранные и проверенные сервисом
            </p>
          </div>

          <div className="proxies-stats">
            <div className="stat-card">
              <span className="stat-card__value">{total}</span>
              <span className="stat-card__label">Всего</span>
            </div>
            <div className="stat-card stat-card--accent">
              <span className="stat-card__value">{activeCount}</span>
              <span className="stat-card__label">Активных</span>
            </div>
          </div>
        </header>

        <div className="proxies-toolbar">
          <div className="proxies-toolbar__actions">
            <button
              type="button"
              className="btn btn--red"
              onClick={() => setIsConfirmOpen(true)}
              disabled={isBusy || (total === 0 && !isLoading)}
              title="Удалить все прокси"
            >
              {pendingAction === 'delete' ? (
                <span className="btn__spinner" />
              ) : (
                <span className="btn__icon" aria-hidden="true">
                  🗑
                </span>
              )}
              <span className="btn__text">
                Удалить<span className="btn__text-extra"> все прокси</span>
              </span>
            </button>

            <button
              type="button"
              className="btn btn--blue"
              onClick={handleAddProxies}
              disabled={isBusy}
              title="Добавить прокси"
            >
              {pendingAction === 'create' ? (
                <span className="btn__spinner" />
              ) : (
                <span className="btn__icon" aria-hidden="true">
                  ＋
                </span>
              )}
              <span className="btn__text">
                Добавить<span className="btn__text-extra"> прокси</span>
              </span>
            </button>

            <button
              type="button"
              className="btn btn--green"
              onClick={() => void handleRefreshAllProxies()}
              disabled={isBusy || (total === 0 && !isLoading)}
              title="Перепроверить все прокси"
            >
              {pendingAction === 'refresh-all' ? (
                <span className="btn__spinner" />
              ) : (
                <span className="btn__icon" aria-hidden="true">
                  ⟳
                </span>
              )}
              <span className="btn__text">
                Обновить<span className="btn__text-extra"> прокси</span>
              </span>
            </button>
          </div>

          <div className="proxies-toolbar__filters">
            <div className="segmented">
              {STATUS_FILTERS.map((filter) => (
                <button
                  key={filter.value}
                  type="button"
                  className={`segmented__item${statusFilter === filter.value ? ' is-active' : ''}`}
                  onClick={() => {
                    setStatusFilter(filter.value)
                    setOffset(0)
                  }}
                  disabled={isBusy}
                >
                  {filter.label}
                </button>
              ))}
            </div>

            <label className="page-size">
              <span className="page-size__label">На странице</span>
              <select
                value={limit}
                onChange={(event) => {
                  setLimit(Number(event.target.value))
                  setOffset(0)
                }}
                disabled={isBusy}
                aria-label="Элементов на странице"
                title="Элементов на странице"
              >
                {PAGE_SIZE_OPTIONS.map((size) => (
                  <option key={size} value={size}>
                    {size}
                  </option>
                ))}
              </select>
            </label>

            <button
              type="button"
              className={`icon-btn icon-btn--reload${isLoading ? ' is-loading' : ''}`}
              onClick={() => void loadProxies()}
              disabled={isBusy || isLoading}
              title="Перезагрузить список"
              aria-label="Перезагрузить список"
            >
              <span className="icon-btn__glyph" aria-hidden="true">
                ↻
              </span>
            </button>
          </div>
        </div>

        <section className="proxies-panel">
          {loadError && (
            <div className="state state--error">
              <span className="state__icon">⚠️</span>
              <div>
                <p className="state__title">Не удалось загрузить список</p>
                <p className="state__text">{loadError}</p>
              </div>
              <button type="button" className="btn btn--ghost" onClick={() => void loadProxies()}>
                Повторить
              </button>
            </div>
          )}

          {!loadError && isLoading && (
            <div className="skeleton-list">
              {Array.from({ length: Math.min(limit, 6) }).map((_, index) => (
                <div key={index} className="skeleton-row" />
              ))}
            </div>
          )}

          {!loadError && !isLoading && proxies.length === 0 && (
            <div className="state state--empty">
              <span className="state__icon">📭</span>
              <div>
                <p className="state__title">Прокси не найдены</p>
                <p className="state__text">
                  {statusFilter === 'all'
                    ? 'Нажмите «Добавить прокси», чтобы загрузить и проверить свежий список.'
                    : 'Попробуйте изменить фильтр по статусу.'}
                </p>
              </div>
            </div>
          )}

          {!loadError && !isLoading && proxies.length > 0 && (
            <div className="table-wrapper">
              <table className="proxies-table">
                <thead>
                  <tr>
                    <th className="col-id">ID</th>
                    <th className="col-proxy">Прокси</th>
                    <th className="col-status">Статус</th>
                    <th className="col-ping">Пинг</th>
                    <th className="col-date">Создан</th>
                    <th className="col-date">Обновлён</th>
                    <th className="col-actions">Действия</th>
                  </tr>
                </thead>
                <tbody>
                  {proxies.map((proxy) => {
                    const { server, port, secret } = parseProxyUrl(proxy.url)
                    const rowAction = rowPending[proxy.id]
                    const isRowBusy = rowAction !== undefined
                    return (
                      <tr key={proxy.id}>
                        <td className="col-id" data-label="ID">
                          <span className="mono muted">#{proxy.id}</span>
                        </td>
                        <td className="col-proxy" data-label="Прокси">
                          <div className="proxy-cell">
                            <span className="proxy-cell__host mono" title={proxy.url}>
                              {server ? `${server}${port ? `:${port}` : ''}` : truncate(proxy.url, 48)}
                            </span>
                            {secret && (
                              <span className="proxy-cell__secret mono">secret: {truncate(secret, 28)}</span>
                            )}
                          </div>
                        </td>
                        <td className="col-status" data-label="Статус">
                          <div
                            className={`status-select status-select--${proxy.status}${
                              rowAction === 'status' ? ' is-busy' : ''
                            }`}
                          >
                            <span className="status-select__dot" aria-hidden="true" />
                            <span className="status-select__label">
                              {STATUS_LABELS[proxy.status] ?? proxy.status}
                            </span>
                            <span className="status-select__caret" aria-hidden="true">
                              {rowAction === 'status' ? <span className="btn__spinner" /> : '▾'}
                            </span>
                            <select
                              className="status-select__field"
                              value={proxy.status}
                              onChange={(event) => {
                                void handleStatusChange(proxy, event.target.value as ProxyStatus)
                              }}
                              disabled={isBusy || isRowBusy}
                              aria-label={`Статус прокси #${proxy.id}`}
                              title="Изменить статус прокси"
                            >
                              {STATUS_OPTIONS.map((status) => (
                                <option key={status} value={status}>
                                  {STATUS_LABELS[status]}
                                </option>
                              ))}
                            </select>
                          </div>
                        </td>
                        <td className="col-ping" data-label="Пинг">
                          <span className={`ping ping--${latencyTone(proxy.latency)}`}>
                            {proxy.latency == null ? '—' : `${proxy.latency} мс`}
                          </span>
                        </td>
                        <td className="col-date muted" data-label="Создан">
                          {formatDate(proxy.created_at)}
                        </td>
                        <td className="col-date muted" data-label="Обновлён">
                          {formatDate(proxy.updated_at)}
                        </td>
                        <td className="col-actions">
                          <div className="row-actions">
                            <a
                              className="btn btn--green btn--sm"
                              href={proxy.url}
                              title="Открыть в Telegram"
                            >
                              <span>⚡</span>
                              Подключиться
                            </a>
                            <button
                              type="button"
                              className={`icon-btn icon-btn--refresh${
                                rowAction === 'refresh' ? ' is-loading' : ''
                              }`}
                              onClick={() => void handleRefreshProxy(proxy)}
                              disabled={isBusy || isRowBusy}
                              title="Перепроверить прокси"
                              aria-label={`Перепроверить прокси #${proxy.id}`}
                            >
                              <span className="icon-btn__glyph" aria-hidden="true">
                                ⟳
                              </span>
                            </button>
                            <button
                              type="button"
                              className="icon-btn"
                              onClick={() => void handleCopy(proxy)}
                              disabled={isRowBusy}
                              title="Скопировать ссылку"
                              aria-label={`Скопировать ссылку прокси #${proxy.id}`}
                            >
                              <span className="icon-btn__glyph" aria-hidden="true">
                                {copiedId === proxy.id ? '✓' : '⧉'}
                              </span>
                            </button>
                          </div>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}

          {!loadError && !isLoading && proxies.length > 0 && (
            <footer className="proxies-footer">
              <span className="muted">
                Показано {rangeFrom}–{rangeTo} из {total}
              </span>
              <div className="pager">
                <button
                  type="button"
                  className="btn btn--ghost"
                  onClick={() => setOffset((current) => Math.max(0, current - limit))}
                  disabled={offset === 0 || isBusy}
                >
                  ← Назад
                </button>
                <span className="pager__page">Стр. {currentPage}</span>
                <button
                  type="button"
                  className="btn btn--ghost"
                  onClick={() => setOffset((current) => current + limit)}
                  disabled={!hasNextPage || isBusy}
                >
                  Вперёд →
                </button>
              </div>
            </footer>
          )}
        </section>
      </div>

      {isConfirmOpen && (
        <div className="modal-backdrop" onClick={() => setIsConfirmOpen(false)}>
          <div className="modal" role="dialog" aria-modal="true" onClick={(event) => event.stopPropagation()}>
            <h2 className="modal__title">Удалить все прокси?</h2>
            <p className="modal__text">
              Будут удалены все записи из базы{total > 0 ? ` (сейчас: ${total})` : ''}. Действие необратимо.
            </p>
            <div className="modal__actions">
              <button type="button" className="btn btn--ghost" onClick={() => setIsConfirmOpen(false)}>
                Отмена
              </button>
              <button type="button" className="btn btn--red" onClick={() => void handleDeleteAll()}>
                Удалить всё
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="toasts">
        {toasts.map((toast) => (
          <div key={toast.id} className={`toast toast--${toast.kind}`}>
            <span>{toast.kind === 'success' ? '✓' : '⚠'}</span>
            {toast.text}
          </div>
        ))}
      </div>
    </div>
  )
}

export default ProxiesPage
