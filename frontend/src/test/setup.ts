/**
 * Глобальная подготовка тестового окружения (подключается через `test.setupFiles`).
 */

import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach, vi } from 'vitest'

afterEach(() => {
  // Размонтируем компоненты и чистим статистику вызовов моков,
  // но НЕ сбрасываем сами реализации — их ставит beforeEach в тестах.
  cleanup()
  vi.clearAllMocks()
})
