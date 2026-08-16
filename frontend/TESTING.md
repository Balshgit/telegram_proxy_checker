# Тесты фронтенда

Стек: [Vitest](https://vitest.dev) + [React Testing Library](https://testing-library.com/react)
+ `jsdom` в качестве браузерного окружения.

## Как запустить

```bash
cd frontend
npm install          # один раз — подтянет vitest, RTL, jsdom
npm test             # прогон всех тестов один раз
npm run test:watch   # watch-режим, перезапуск при изменении файлов
npm run test:coverage # отчёт о покрытии (текстом + html в frontend/coverage)
```

Точечный запуск:

```bash
npm test -- src/api/proxies.test.ts        # один файл
npm test -- -t "пагинация"                 # только тесты, чей заголовок содержит строку
```

Бекенд поднимать не нужно: `fetch` и модуль `src/api/proxies.ts` мокаются.

Проверка типов:

```bash
npm run typecheck        # прод-код (то же, что делает npm run build)
npm run typecheck:test   # прод-код + тесты
```

## Что где лежит

| Файл | Что покрывает |
| --- | --- |
| `src/api/proxies.test.ts` | HTTP-клиент: сборка URL и тел запросов, распаковка конверта `{status, error, payload}`, приоритет текстов ошибок, `ApiRequestError`, коды вроде `NoProxiesAddedError` |
| `src/pages/proxiesPage.helpers.test.ts` | Чистые функции: `buildPageItems` (окно страниц с многоточиями), `formatDate`, `latencyTone`, `truncate`, `proxyLabel`, `filteredTotalFor`, `copyToClipboard` (включая fallback на `execCommand`) |
| `src/pages/ProxiesPage.test.tsx` | Компонент целиком: загрузка и рендер таблицы, фильтры и размер страницы, состояния «пусто»/«ошибка», добавление/удаление/массовое обновление прокси, копирование в буфер, действия над строкой, пагинация |

Конфигурация:

- `settings/vite.config.ts` — секция `test` (окружение jsdom, setup-файл, coverage).
- `src/test/setup.ts` — подключение `@testing-library/jest-dom` и авто-очистка после каждого теста.
- `settings/tsconfig.test.json` — отдельный tsconfig, чтобы тесты не попадали в прод-сборку.

## Как устроены моки

- **API-клиент** (`proxies.test.ts`) — подменяется глобальный `fetch` через `vi.stubGlobal`.
  Заглушка `Response` реализует только `ok`, `status` и `text()` — больше клиенту не нужно.
- **Компонент** (`ProxiesPage.test.tsx`) — мокается весь модуль `../api/proxies`,
  но `ApiRequestError` и `API_ERROR_CODES` берутся настоящие через `importOriginal()`:
  компонент различает штатные и нештатные ошибки именно по ним.
- **Буфер обмена** — `navigator.clipboard.writeText` подменяется через `Object.defineProperty`,
  так как jsdom Clipboard API не реализует.

## Добавляем новый тест

Файл должен называться `*.test.ts` / `*.test.tsx` и лежать внутри `src/`.
Запросы к элементам пишите через доступные имена (`getByRole`, `getByLabelText`, `getByTitle`),
а не через классы — так тесты не ломаются от правок вёрстки.
