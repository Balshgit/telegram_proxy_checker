import { afterEach, describe, expect, it, vi } from 'vitest'

import { copyToClipboard, formatDate, truncate } from './format'

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

describe('truncate', () => {
  it('короткую строку не трогает', () => {
    expect(truncate('abc', 5)).toBe('abc')
    expect(truncate('abcde', 5)).toBe('abcde')
  })

  it('длинную обрезает и добавляет многоточие', () => {
    expect(truncate('abcdef', 5)).toBe('abcde…')
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
