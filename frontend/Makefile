GREEN  := $(shell tput -Txterm setaf 2)
YELLOW := $(shell tput -Txterm setaf 3)
RESET  := $(shell tput -Txterm sgr0)

.PHONY: help app build test test-watch test-coverage typecheck

.DEFAULT_GOAL := help


## Запустить приложение на 3000 порту.
app:
	npm run dev -- --port 8083

## Собрать приложение.
build:
	npm run build


## Запустить все тесты.
test:
	npm run test


## Запустить тесты в watch режиме.
test-watch:
	npm run test:watch


## Запустить тесты с отчетом о покрытии.
test-coverage:
	npm run test:coverage


## Проверить типы в коде и тестах.
typecheck:
	npm run typecheck && npm run typecheck:test


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
