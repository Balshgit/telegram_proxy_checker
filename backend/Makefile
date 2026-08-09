GREEN  := $(shell tput -Txterm setaf 2)
YELLOW := $(shell tput -Txterm setaf 3)
RESET  := $(shell tput -Txterm sgr0)

.PHONY: help format lint lint-style lint-typing lint-imports lint-complexity lint-vulnerabilities app
.DEFAULT_GOAL := help

PYTHON_TARGETS = app tests settings

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
