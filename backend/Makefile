GREEN  := $(shell tput -Txterm setaf 2)
YELLOW := $(shell tput -Txterm setaf 3)
RESET  := $(shell tput -Txterm sgr0)

.PHONY: help format lint lint-style lint-typing lint-imports lint-complexity lint-vulnerabilities app test \
        migrate migration migration-empty downgrade migration-history migration-current migration-sql

.DEFAULT_GOAL := help

PYTHON_TARGETS = app tests settings
# Миграции (app/infra/migrations) исключены из mypy — см. `exclude` в pyproject.toml.
MYPY_TARGETS = app tests settings

APP_FACTORY = app.main:create_app

TESTS_PATH = tests
PYTEST_ARGS ?= --verbose --cov=app --cov=branch -p no:repeat -p no:sugar -p no:metadata -p no:order

# Ревизия alembic по умолчанию для migrate/migration-sql.
REV ?= head


## Отформатировать код и исправить простые ошибки.
format:
	uv run black $(PYTHON_TARGETS) && uv run ruff check --fix $(PYTHON_TARGETS)

## Проверить стиль кода и найти возможные ошибки.
lint-style:
	uv run ruff check $(PYTHON_TARGETS) && uv run black --check $(PYTHON_TARGETS)

## Проверить подсказки типов в коде.
lint-type-hints:
	uv run mypy $(MYPY_TARGETS)

## Проверить структуру кода по контрактам импортов.
lint-imports:
	uv run lint-imports --show-timings

## Проверить сложность кода, а также найти возможные ошибки.
lint-complexity:
	uv run flake8 $(PYTHON_TARGETS)

## Проверить код.
lint: lint-style lint-type-hints lint-imports lint-complexity

## Запустить все тесты.
test:
	RYUK_CONTAINER_IMAGE=testcontainers/ryuk:0.8.1; STAGE=local.runtests uv run pytest $(TESTS_PATH) $(PYTEST_ARGS)

## Запустить приложение.
app:
	uvicorn --factory $(APP_FACTORY) --reload


## Накатить миграции до последней (REV=head по умолчанию).
migrate:
	uv run alembic upgrade $(REV)

## Создать миграцию из различий моделей и БД. Пример: make migration M="add proxy latency"
migration:
	@test -n "$(M)" || (echo "укажите сообщение: make migration M=\"описание\"" && exit 1)
	uv run alembic revision --autogenerate -m "$(M)"

## Создать пустую миграцию. Пример: make migration-empty M="backfill statuses"
migration-empty:
	@test -n "$(M)" || (echo "укажите сообщение: make migration-empty M=\"описание\"" && exit 1)
	uv run alembic revision -m "$(M)"

## Откатить миграции. Пример: make downgrade TO=-1
downgrade:
	@test -n "$(TO)" || (echo "укажите ревизию: make downgrade TO=-1" && exit 1)
	uv run alembic downgrade $(TO)

## История миграций.
migration-history:
	uv run alembic history --indicate-current --verbose

## Текущая ревизия в БД.
migration-current:
	uv run alembic current --verbose

## Показать SQL миграций без применения (REV=head по умолчанию).
migration-sql:
	uv run alembic upgrade $(REV) --sql


help:
	@awk '/^[a-zA-Z\-_0-9]+:/ { \
		helpMessage = match(lastLine, /^## (.*)/); \
		if (helpMessage) { \
			helpCommand = $$1; sub(/:$$/, "", helpCommand); \
			helpMessage = substr(lastLine, RSTART + 3, RLENGTH); \
			printf "  ${YELLOW}make %-$(TARGET_MAX_CHAR_NUM)25s${RESET} ${GREEN}%s${RESET}\n", helpCommand, helpMessage; \
		} \
	} \
	{ lastLine = $$0 }' $(MAKEFILE_LIST)
