import { useState } from 'react'

import { Modal } from '../../shared/ui/Modal'
import { SOURCE_NAME_MAX_LENGTH } from './api'
import type { ProxySourceStatus, ProxySourceVendor } from './api'
import {
  EMPTY_FORM,
  hasErrors,
  STATUS_LABELS,
  STATUS_OPTIONS,
  validateSourceForm,
  VENDOR_LABELS,
  VENDOR_OPTIONS,
} from './helpers'
import type { SourceFormErrors, SourceFormValues } from './helpers'

interface SourceFormModalProps {
  title: string
  submitLabel: string
  /** Начальные значения: пусто — форма добавления, значения источника — форма редактирования. */
  initialValues?: SourceFormValues
  isSaving: boolean
  onSubmit: (values: SourceFormValues) => void
  onCancel: () => void
}

/**
 * Одна форма на добавление и редактирование источника: поля и правила
 * валидации совпадают, различаются только заголовок, подпись кнопки
 * и начальные значения.
 */
export function SourceFormModal({
  title,
  submitLabel,
  initialValues = EMPTY_FORM,
  isSaving,
  onSubmit,
  onCancel,
}: SourceFormModalProps) {
  const [values, setValues] = useState<SourceFormValues>(initialValues)
  /** Ошибки показываем только после попытки отправки — не ругаемся на пустую форму заранее. */
  const [errors, setErrors] = useState<SourceFormErrors>({})

  const setField = <TField extends keyof SourceFormValues>(
    field: TField,
    value: SourceFormValues[TField],
  ) => {
    setValues((current) => ({ ...current, [field]: value }))
    setErrors((current) => ({ ...current, [field]: undefined }))
  }

  const handleSubmit = () => {
    const nextErrors = validateSourceForm(values)
    setErrors(nextErrors)
    if (hasErrors(nextErrors)) {
      return
    }
    onSubmit({ ...values, name: values.name.trim(), url: values.url.trim() })
  }

  return (
    <Modal
      title={title}
      onClose={onCancel}
      wide
      actions={
        <>
          <button type="button" className="btn btn--ghost" onClick={onCancel} disabled={isSaving}>
            Отмена
          </button>
          <button type="button" className="btn btn--blue" onClick={handleSubmit} disabled={isSaving}>
            {isSaving && <span className="btn__spinner" />}
            {submitLabel}
          </button>
        </>
      }
    >
      <form
        className="form"
        noValidate
        onSubmit={(event) => {
          event.preventDefault()
          handleSubmit()
        }}
      >
        {/*
          Подписи связаны с полями через htmlFor: подсказки и тексты ошибок лежат
          рядом с контролом, а не внутри label, поэтому не попадают в его название.
        */}
        <div className={`field${errors.name ? ' field--invalid' : ''}`}>
          <label className="field__label" htmlFor="source-name">
            Название
          </label>
          <input
            id="source-name"
            className="field__control"
            value={values.name}
            onChange={(event) => setField('name', event.target.value)}
            maxLength={SOURCE_NAME_MAX_LENGTH}
            placeholder="Например, MTProto list"
            disabled={isSaving}
            autoFocus
          />
          {errors.name && <span className="field__error">{errors.name}</span>}
        </div>

        <div className={`field${errors.url ? ' field--invalid' : ''}`}>
          <label className="field__label" htmlFor="source-url">
            Адрес
          </label>
          <input
            id="source-url"
            className="field__control"
            value={values.url}
            onChange={(event) => setField('url', event.target.value)}
            placeholder="https://raw.githubusercontent.com/..."
            inputMode="url"
            disabled={isSaving}
          />
          {errors.url ? (
            <span className="field__error">{errors.url}</span>
          ) : (
            <span className="field__hint">Откуда бекенд будет забирать список прокси.</span>
          )}
        </div>

        <div className="field">
          <label className="field__label" htmlFor="source-vendor">
            Вендор
          </label>
          <select
            id="source-vendor"
            className="field__control"
            value={values.vendor}
            onChange={(event) => setField('vendor', event.target.value as ProxySourceVendor)}
            disabled={isSaving}
          >
            {VENDOR_OPTIONS.map((vendor) => (
              <option key={vendor} value={vendor}>
                {VENDOR_LABELS[vendor]}
              </option>
            ))}
          </select>
          <span className="field__hint">Определяет, как бекенд разбирает ответ источника.</span>
        </div>

        <div className="field">
          <label className="field__label" htmlFor="source-status">
            Статус
          </label>
          <select
            id="source-status"
            className="field__control"
            value={values.status}
            onChange={(event) => setField('status', event.target.value as ProxySourceStatus)}
            disabled={isSaving}
          >
            {STATUS_OPTIONS.map((status) => (
              <option key={status} value={status}>
                {STATUS_LABELS[status]}
              </option>
            ))}
          </select>
          <span className="field__hint">Выключенные источники не опрашиваются при сборе прокси.</span>
        </div>
      </form>
    </Modal>
  )
}
