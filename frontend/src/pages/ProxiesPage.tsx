import { useCallback, useEffect, useRef, useState } from 'react'

import {
  API_ERROR_CODES,
  ApiRequestError,
  createProxies,
  deleteAllProxies,
  fetchProxies,
  fetchRawProxies,
  updateAllProxies,
  updateProxy,
} from '../api/proxies'
import type { ProxyStatus, TelegramProxy } from '../api/proxies'

import {
  buildPageItems,
  copyToClipboard,
  COPY_SCOPE_EMPTY_TEXT,
  COPY_SCOPE_STATUS,
  filteredTotalFor,
  formatDate,
  latencyTone,
  NOTHING_TO_ADD_TOAST,
  PAGE_SIZE_OPTIONS,
  proxyLabel,
  STATUS_FILTERS,
  STATUS_LABELS,
  STATUS_OPTIONS,
  truncate,
} from './proxiesPage.helpers'
import type { CopyScope, StatusFilter } from './proxiesPage.helpers'

import './ProxiesPage.css'

type PendingAction = 'create' | 'delete' | 'refresh-all' | null
/** Что именно сейчас происходит с конкретной строкой таблицы. */
type RowAction = 'refresh' | 'status'

interface Toast {
  id: number
  kind: 'success' | 'error' | 'info'
  text: string
  /** Необязательная вторая строка — поясняет, что делать дальше. */
  hint?: string
}

const TOAST_ICONS: Record<Toast['kind'], string> = {
  success: '✓',
  error: '⚠',
  info: 'ℹ',
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
  const [copyingScope, setCopyingScope] = useState<CopyScope | null>(null)
  const [copiedScope, setCopiedScope] = useState<CopyScope | null>(null)
  const [rowPending, setRowPending] = useState<Record<number, RowAction>>({})
  const [toasts, setToasts] = useState<Toast[]>([])

  const toastSeq = useRef(0)

  const pushToast = useCallback((kind: Toast['kind'], text: string, hint?: string) => {
    toastSeq.current += 1
    const id = toastSeq.current
    setToasts((current) => [...current, { id, kind, text, hint }])
    window.setTimeout(
      () => {
        setToasts((current) => current.filter((toast) => toast.id !== id))
      },
      // Подсказку нужно успеть прочитать — держим такой тост чуть дольше.
      hint ? 6000 : 4000,
    )
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

      // Бекенд может ответить 200 с пустым списком — это тот же «нечего добавлять».
      if (created.length === 0) {
        pushToast('info', NOTHING_TO_ADD_TOAST.text, NOTHING_TO_ADD_TOAST.hint)
        return
      }

      pushToast('success', `Добавлено проксей: ${created.length}`)
      setOffset(0)
      await loadProxies()
    } catch (error) {
      // 400 NoProxiesAddedError — штатный исход, не показываем его как поломку.
      if (error instanceof ApiRequestError && error.code === API_ERROR_CODES.noProxiesAdded) {
        pushToast('info', NOTHING_TO_ADD_TOAST.text, NOTHING_TO_ADD_TOAST.hint)
        return
      }

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
        await copyToClipboard(proxy.url)
        setCopiedId(proxy.id)
        window.setTimeout(() => setCopiedId((current) => (current === proxy.id ? null : current)), 1500)
      } catch {
        pushToast('error', 'Не удалось скопировать ссылку')
      }
    },
    [pushToast],
  )

  /**
   * Клик по карточке-счётчику: тянет GET /api/proxies/raw (для «Активных» —
   * с фильтром `status=enabled`) и кладёт урлы в буфер обмена, каждый с новой строки.
   */
  const handleCopyRaw = useCallback(
    async (scope: CopyScope) => {
      if (copyingScope !== null) {
        return
      }

      setCopyingScope(scope)
      try {
        const urls = await fetchRawProxies({ status: COPY_SCOPE_STATUS[scope] })

        if (urls.length === 0) {
          pushToast('info', COPY_SCOPE_EMPTY_TEXT[scope], 'Копировать нечего.')
          return
        }

        await copyToClipboard(urls.join('\n'))

        setCopiedScope(scope)
        window.setTimeout(() => setCopiedScope((current) => (current === scope ? null : current)), 1500)

        pushToast('success', `Скопировано в буфер обмена, прокси: ${urls.length}`)
      } catch (error) {
        pushToast(
          'error',
          error instanceof ApiRequestError ? error.message : 'Не удалось скопировать список прокси',
        )
      } finally {
        setCopyingScope(null)
      }
    },
    [copyingScope, pushToast],
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
          pushToast('success', `Прокси ${proxyLabel(updated)}: статус — ${STATUS_LABELS[updated.status]}`)
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
            ? `Прокси ${proxyLabel(updated)} проверена: ${
                updated.latency == null ? 'нет ответа' : `${updated.latency} мс`
              }`
            : `Прокси ${proxyLabel(updated)}: статус — ${STATUS_LABELS[updated.status]}`,
        )
      } catch (error) {
        pushToast(
          'error',
          error instanceof ApiRequestError ? error.message : `Не удалось обновить прокси ${proxyLabel(proxy)}`,
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

  /**
   * Бекенд отдаёт счётчики по всей базе (total) и по активным (active),
   * без учёта фильтра — поэтому размер текущей выборки считаем сами.
   */
  const filteredTotal = filteredTotalFor(statusFilter, total, activeCount)

  const currentPage = Math.floor(offset / limit) + 1
  /**
   * Если счётчики разъехались с реальными данными (например, список изменился
   * в другой вкладке), доверяем next_page и не отрезаем существующую страницу.
   */
  const totalPages = Math.max(
    1,
    Math.ceil(filteredTotal / limit),
    hasNextPage ? currentPage + 1 : currentPage,
  )
  const pageItems = buildPageItems(currentPage, totalPages)

  const rangeFrom = proxies.length ? offset + 1 : 0
  const rangeTo = offset + proxies.length

  const goToPage = useCallback(
    (page: number) => {
      setOffset((current) => {
        const nextOffset = (page - 1) * limit
        return nextOffset === current ? current : Math.max(0, nextOffset)
      })
    },
    [limit],
  )

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
            <button
              type="button"
              className={`stat-card${copyingScope === 'all' ? ' is-busy' : ''}`}
              onClick={() => void handleCopyRaw('all')}
              disabled={copyingScope !== null}
              title="Скопировать все прокси в буфер обмена"
              aria-label="Скопировать все прокси в буфер обмена"
            >
              <span className="stat-card__value">{total}</span>
              <span className="stat-card__label">Всего</span>
              <span className="stat-card__copy" aria-hidden="true">
                {copyingScope === 'all' ? (
                  <span className="btn__spinner" />
                ) : (
                  <span className="stat-card__copy-glyph">{copiedScope === 'all' ? '✓' : '⧉'}</span>
                )}
              </span>
            </button>
            <button
              type="button"
              className={`stat-card stat-card--accent${copyingScope === 'active' ? ' is-busy' : ''}`}
              onClick={() => void handleCopyRaw('active')}
              disabled={copyingScope !== null}
              title="Скопировать активные прокси в буфер обмена"
              aria-label="Скопировать активные прокси в буфер обмена"
            >
              <span className="stat-card__value">{activeCount}</span>
              <span className="stat-card__label">Активных</span>
              <span className="stat-card__copy" aria-hidden="true">
                {copyingScope === 'active' ? (
                  <span className="btn__spinner" />
                ) : (
                  <span className="stat-card__copy-glyph">{copiedScope === 'active' ? '✓' : '⧉'}</span>
                )}
              </span>
            </button>
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
                    const rowAction = rowPending[proxy.id]
                    const isRowBusy = rowAction !== undefined
                    return (
                      <tr key={proxy.id}>
                        <td className="col-id" data-label="ID">
                          <span className="mono muted">#{proxy.id}</span>
                        </td>
                        <td className="col-proxy" data-label="Прокси">
                          <div className="proxy-cell">
                            <span
                              className={`proxy-cell__name${proxy.name ? '' : ' proxy-cell__name--empty'}`}
                              title={proxy.name || undefined}
                            >
                              {proxy.name ? truncate(proxy.name, 48) : 'Без имени'}
                            </span>
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
                Показано {rangeFrom}–{rangeTo} из {filteredTotal}
              </span>
              <nav className="pager" aria-label="Навигация по страницам">
                <button
                  type="button"
                  className="btn btn--ghost pager__edge"
                  onClick={() => goToPage(1)}
                  disabled={currentPage === 1 || isBusy}
                  title="Первая страница"
                  aria-label="Первая страница"
                >
                  «
                </button>
                <button
                  type="button"
                  className="btn btn--ghost pager__step"
                  onClick={() => setOffset((current) => Math.max(0, current - limit))}
                  disabled={currentPage === 1 || isBusy}
                  title="Предыдущая страница"
                  aria-label="Предыдущая страница"
                >
                  <span aria-hidden="true">←</span>
                  <span className="pager__step-text">Назад</span>
                </button>

                <span className="pager__label">Стр.</span>
                <ul className="pager__pages">
                  {pageItems.map((item) =>
                    typeof item === 'number' ? (
                      <li key={item}>
                        <button
                          type="button"
                          className={`pager__page${item === currentPage ? ' is-active' : ''}`}
                          onClick={() => goToPage(item)}
                          disabled={isBusy}
                          aria-current={item === currentPage ? 'page' : undefined}
                          aria-label={`Страница ${item}`}
                          title={`Страница ${item}`}
                        >
                          {item}
                        </button>
                      </li>
                    ) : (
                      <li key={item} className="pager__gap" aria-hidden="true">
                        …
                      </li>
                    ),
                  )}
                </ul>

                <button
                  type="button"
                  className="btn btn--ghost pager__step"
                  onClick={() => setOffset((current) => current + limit)}
                  disabled={(!hasNextPage && currentPage >= totalPages) || isBusy}
                  title="Следующая страница"
                  aria-label="Следующая страница"
                >
                  <span className="pager__step-text">Вперёд</span>
                  <span aria-hidden="true">→</span>
                </button>
                <button
                  type="button"
                  className="btn btn--ghost pager__edge"
                  onClick={() => goToPage(totalPages)}
                  disabled={currentPage === totalPages || isBusy}
                  title="Последняя страница"
                  aria-label="Последняя страница"
                >
                  »
                </button>
              </nav>
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
          <div key={toast.id} className={`toast toast--${toast.kind}`} role="status">
            <span className="toast__icon" aria-hidden="true">
              {TOAST_ICONS[toast.kind]}
            </span>
            <div className="toast__body">
              <span className="toast__text">{toast.text}</span>
              {toast.hint && <span className="toast__hint">{toast.hint}</span>}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

export default ProxiesPage
