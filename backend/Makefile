GREEN  := $(shell tput -Txterm setaf 2)
YELLOW := $(shell tput -Txterm setaf 3)
RESET  := $(shell tput -Txterm sgr0)

.PHONY: help format lint lint-style lint-typing lint-imports lint-complexity lint-vulnerabilities app up-app-dependencies down-app-dependencies
.DEFAULT_GOAL := help

PYTHON_TARGETS = app tests settings scripts

APP_FACTORY = app.main:create_app


## Отформатировать код и исправить простые ошибки.
format:
	uv run black $(PYTHON_TARGETS) && uv run ruff check --fix $(PYTHON_TARGETS)


## Проверить стиль кода и найти возможные ошибки.
lint-style:
	uv run ruff check $(PYTHON_TARGETS) && uv run black --check $(PYTHON_TARGETS)


## Проверить подсказки типов в коде.
lint-type-hints:
	uv run mypy $(PYTHON_TARGETS)


## Проверить структуру кода по контрактам импортов.
lint-imports:
	uv run lint-imports --show-timings


## Проверить сложность кода, а также найти возможные ошибки.
lint-complexity:
	uv run flake8 $(PYTHON_TARGETS)


## Проверить код.
lint: lint-style lint-type-hints lint-imports lint-complexity


## Запустить приложение.
app:
	uvicorn --factory $(APP_FACTORY) --reload


## Запустить локальное окружение для приложения.
up-app-dependencies:
	docker compose up -d


## Отключить локальное окружение для приложения.
down-app-dependencies:
	docker compose --profile "*" down -v

## Запуск приложения в докере.
up-docker-app:
	docker compose --profile "app" up -d

## Сборка приложения.
build-image:
	docker build --platform linux/amd64 -t docker-prc-dev.x5.ru/prc_backend:latest .

## Сохранения образа в репозиторий.
push-image:
	docker login docker-prc-dev.x5.ru && docker push docker-prc-dev.x5.ru/prc_backend:latest


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
