import type { ReactNode } from 'react'
import { useCallback, useEffect, useState } from 'react'

import { ApiRequestError } from '../../shared/api/client'
import { normalizeSearch, setSearch, useSearch } from '../../shared/router'
import { ConfirmDialog } from '../../shared/ui/Modal'
import { Toasts, useToasts } from '../../shared/ui/Toasts'
import { formatDate, truncate } from '../../shared/ui/format'

import { createProxySource, deleteProxySource, fetchProxiesSources, updateProxySource } from './api'
import type { ProxySource } from './api'
import { SourceFormModal } from './SourceFormModal'
import {
  changedFields,
  formValuesFrom,
  parseSourcesStatus,
  serializeSourcesQuery,
  sourceLabel,
  STATUS_FILTERS,
  STATUS_LABELS,
  VENDOR_LABELS,
} from './helpers'
import type { SourceFormValues } from './helpers'

import './SourcesPage.css'

interface SourcesPageProps {
  /** Переключатель страниц из App — рисуется в шапке. */
  nav?: ReactNode
}

/** Какая модалка сейчас открыта. */
type Dialog =
  | { kind: 'create' }
  | { kind: 'edit'; source: ProxySource }
  | { kind: 'delete'; source: ProxySource }
  | null

function SourcesPage({ nav }: SourcesPageProps) {
  const [sources, setSources] = useState<ProxySource[]>([])

  /*
   * Фильтр живёт в адресе (`/proxies/sources?source_status=enabled`), как и
   * параметры списка проксей: ссылку на нужную выборку можно скинуть, положить
   * в закладки и поправить прямо в адресной строке.
   */
  const search = useSearch()
  const statusFilter = parseSourcesStatus(search)

  /* Причёсываем адрес под канон: выкидываем дефолт и невалидные значения. */
  useEffect(() => {
    const canonical = normalizeSearch(serializeSourcesQuery(statusFilter))
    if (canonical !== search) {
      setSearch(canonical, { replace: true })
    }
  }, [search, statusFilter])

  const [isLoading, setIsLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [dialog, setDialog] = useState<Dialog>(null)
  const [isSaving, setIsSaving] = useState(false)
  /** ID источника, который сейчас удаляется — блокирует только его строку. */
  const [deletingId, setDeletingId] = useState<number | null>(null)

  const { toasts, pushToast } = useToasts()

  const loadSources = useCallback(
    async (signal?: AbortSignal) => {
      setIsLoading(true)
      setLoadError(null)
      try {
        const items = await fetchProxiesSources({
          status: statusFilter === 'all' ? null : statusFilter,
          signal,
        })
        if (signal?.aborted) {
          return
        }
        setSources(items)
      } catch (error) {
        if (signal?.aborted) {
          return
        }
        setSources([])
        setLoadError(
          error instanceof ApiRequestError ? error.message : 'Неизвестная ошибка при загрузке источников',
        )
      } finally {
        if (!signal?.aborted) {
          setIsLoading(false)
        }
      }
    },
    [statusFilter],
  )

  useEffect(() => {
    const controller = new AbortController()
    void loadSources(controller.signal)
    return () => controller.abort()
  }, [loadSources])

  /** POST /api/proxies/sources отвечает 201 без тела — свежий список дочитываем отдельно. */
  const handleCreate = useCallback(
    async (values: SourceFormValues) => {
      setIsSaving(true)
      try {
        await createProxySource(values)
        setDialog(null)
        pushToast('success', `Источник «${truncate(values.name, 32)}» добавлен`)
        await loadSources()
      } catch (error) {
        pushToast('error', error instanceof ApiRequestError ? error.message : 'Не удалось добавить источник')
      } finally {
        setIsSaving(false)
      }
    },
    [loadSources, pushToast],
  )

  /** PATCH принимает только изменённые поля; ответ 204 без тела — список перезагружаем. */
  const handleUpdate = useCallback(
    async (source: ProxySource, values: SourceFormValues) => {
      const changes = changedFields(source, values)

      if (Object.keys(changes).length === 0) {
        setDialog(null)
        pushToast('info', 'Менять нечего — источник остался прежним')
        return
      }

      setIsSaving(true)
      try {
        await updateProxySource(source.id, changes)
        setDialog(null)
        pushToast('success', `Источник ${sourceLabel(source)} обновлён`)
        await loadSources()
      } catch (error) {
        pushToast('error', error instanceof ApiRequestError ? error.message : 'Не удалось обновить источник')
      } finally {
        setIsSaving(false)
      }
    },
    [loadSources, pushToast],
  )

  const handleDelete = useCallback(
    async (source: ProxySource) => {
      setDialog(null)
      setDeletingId(source.id)
      try {
        await deleteProxySource(source.id)
        pushToast('success', `Источник ${sourceLabel(source)} удалён`)
        await loadSources()
      } catch (error) {
        pushToast('error', error instanceof ApiRequestError ? error.message : 'Не удалось удалить источник')
      } finally {
        setDeletingId(null)
      }
    },
    [loadSources, pushToast],
  )

  const totalProxies = sources.reduce((sum, source) => sum + source.proxies_count, 0)
  const activeProxies = sources.reduce((sum, source) => sum + source.active_proxies_count, 0)

  return (
    <div className="sources-page">
      <div className="sources-page__glow" aria-hidden="true" />

      <div className="sources-page__inner">
        {nav}

        <header className="sources-header">
          <div>
            <h1 className="sources-header__title">
              <span className="sources-header__icon">⛁</span>
              Источники прокси
            </h1>
            <p className="sources-header__subtitle">
              Адреса, из которых сервис забирает списки Telegram-прокси
            </p>
          </div>

          <div className="sources-stats">
            <div className="source-stat">
              <span className="source-stat__value">{sources.length}</span>
              <span className="source-stat__label">Источников</span>
            </div>
            <div className="source-stat source-stat--accent">
              <span className="source-stat__value">
                {activeProxies}
                <span className="source-stat__value-of"> / {totalProxies}</span>
              </span>
              <span className="source-stat__label">Активных прокси</span>
            </div>
          </div>
        </header>

        <div className="sources-toolbar">
          <button
            type="button"
            className="btn btn--blue"
            onClick={() => setDialog({ kind: 'create' })}
            title="Добавить источник"
          >
            <span className="btn__icon" aria-hidden="true">
              ＋
            </span>
            <span className="btn__text">
              Добавить<span className="btn__text-extra"> источник</span>
            </span>
          </button>

          <div className="segmented">
            {STATUS_FILTERS.map((filter) => (
              <button
                key={filter.value}
                type="button"
                className={`segmented__item${statusFilter === filter.value ? ' is-active' : ''}`}
                onClick={() => setSearch(serializeSourcesQuery(filter.value))}
              >
                {filter.label}
              </button>
            ))}
          </div>
        </div>

        <section className="sources-panel">
          {loadError && (
            <div className="state state--error">
              <span className="state__icon">⚠️</span>
              <div>
                <p className="state__title">Не удалось загрузить источники</p>
                <p className="state__text">{loadError}</p>
              </div>
              <button type="button" className="btn btn--ghost" onClick={() => void loadSources()}>
                Повторить
              </button>
            </div>
          )}

          {!loadError && isLoading && (
            <div className="skeleton-list">
              {Array.from({ length: 3 }).map((_, index) => (
                <div key={index} className="skeleton-row" />
              ))}
            </div>
          )}

          {!loadError && !isLoading && sources.length === 0 && (
            <div className="state state--empty">
              <span className="state__icon">🗂️</span>
              <div>
                <p className="state__title">Источники не найдены</p>
                <p className="state__text">
                  {statusFilter === 'all'
                    ? 'Нажмите «Добавить источник», чтобы сервису было откуда брать прокси.'
                    : 'Попробуйте изменить фильтр по статусу.'}
                </p>
              </div>
            </div>
          )}

          {!loadError && !isLoading && sources.length > 0 && (
            <ul className="sources-list">
              {sources.map((source) => {
                const isRowBusy = deletingId === source.id
                return (
                  <li key={source.id} className="source-card">
                    <div className="source-card__main">
                      <div className="source-card__heading">
                        <span className="source-card__name" title={source.name}>
                          {truncate(source.name, 64)}
                        </span>
                        <span className={`badge badge--${source.status}`}>
                          <span className="badge__dot" aria-hidden="true" />
                          {STATUS_LABELS[source.status]}
                        </span>
                        {/* Вендор и есть ссылка на файл источника: длинный сырой урл прячем
                            за подписью, полный адрес показываем в подсказке по наведению. */}
                        <a
                          className="badge badge--neutral badge--link"
                          href={source.url}
                          target="_blank"
                          rel="noreferrer"
                          title={source.url}
                        >
                          {VENDOR_LABELS[source.vendor]}
                        </a>
                      </div>

                      <div className="source-card__meta muted">
                        <span>
                          Прокси: <strong>{source.proxies_count}</strong> (активных{' '}
                          <strong>{source.active_proxies_count}</strong>)
                        </span>
                        <span>Создан: {formatDate(source.created_at)}</span>
                        <span>Обновлён: {formatDate(source.updated_at)}</span>
                      </div>
                    </div>

                    <div className="source-card__actions">
                      <button
                        type="button"
                        className="icon-btn icon-btn--edit"
                        onClick={() => setDialog({ kind: 'edit', source })}
                        disabled={isRowBusy}
                        title="Редактировать источник"
                        aria-label={`Редактировать источник #${source.id}`}
                      >
                        <span className="icon-btn__glyph" aria-hidden="true">
                          ✎
                        </span>
                      </button>
                      <button
                        type="button"
                        className={`icon-btn icon-btn--danger${isRowBusy ? ' is-loading' : ''}`}
                        onClick={() => setDialog({ kind: 'delete', source })}
                        disabled={isRowBusy}
                        title="Удалить источник"
                        aria-label={`Удалить источник #${source.id}`}
                      >
                        <span className="icon-btn__glyph" aria-hidden="true">
                          {isRowBusy ? <span className="btn__spinner" /> : '🗑'}
                        </span>
                      </button>
                    </div>
                  </li>
                )
              })}
            </ul>
          )}
        </section>
      </div>

      {dialog?.kind === 'create' && (
        <SourceFormModal
          title="Новый источник"
          submitLabel="Добавить"
          isSaving={isSaving}
          onSubmit={(values) => void handleCreate(values)}
          onCancel={() => setDialog(null)}
        />
      )}

      {dialog?.kind === 'edit' && (
        <SourceFormModal
          title={`Источник ${sourceLabel(dialog.source)}`}
          submitLabel="Сохранить"
          initialValues={formValuesFrom(dialog.source)}
          isSaving={isSaving}
          onSubmit={(values) => void handleUpdate(dialog.source, values)}
          onCancel={() => setDialog(null)}
        />
      )}

      {dialog?.kind === 'delete' && (
        <ConfirmDialog
          title={`Удалить источник ${sourceLabel(dialog.source)}?`}
          text="Прокси, собранные из этого источника, останутся в базе, но потеряют привязку к нему."
          confirmLabel="Удалить"
          onConfirm={() => void handleDelete(dialog.source)}
          onCancel={() => setDialog(null)}
        />
      )}

      <Toasts toasts={toasts} />
    </div>
  )
}

export default SourcesPage
