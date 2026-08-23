GREEN  := $(shell tput -Txterm setaf 2)
YELLOW := $(shell tput -Txterm setaf 3)
RESET  := $(shell tput -Txterm sgr0)

.PHONY: help backend frontend database up-docker-app down-docker-app build-backend build-frontend push-backend push-frontend push-images \
        test test-backend test-frontend migrate migration
.DEFAULT_GOAL := help

## Запустить backend.
backend:
	cd backend && make app && cd -

## Накатить миграции БД.
migrate:
	cd backend && make migrate && cd -

## Создать миграцию. Пример: make migration M="add proxy latency"
migration:
	cd backend && make migration M="$(M)" && cd -

## Запустить frontend.
frontend:
	cd frontend && make app && cd -

## Запустить тесты бекенда.
test-backend:
	cd backend && make test && cd -

## Запустить тесты фронтенда.
test-frontend:
	cd frontend && make test && cd -

## Запустить тесты бекенда и фронтенда.
test: test-backend test-frontend

## Запустить базу данных
up-database:
	docker compose --profile "db" up -d

## Запуск приложения в докере.
up-docker-app:
	docker compose --profile "app" up -d

## Отключить локальное окружение для приложения.
down-docker-app:
	docker compose --profile "*" down -v

## Сбилдить бекенд
build-backend:
	echo "building backend docker image..."
	cd backend && docker build --platform linux/amd64 -f docker/Dockerfile -t tpc_backend:latest . && cd -

## Сбилдить фронтенд
build-frontend:
	echo "building frontend docker image..."
	cd frontend && docker build --platform linux/amd64 -f docker/Dockerfile -t tpc_frontend:latest . && cd -

## Сборка приложения.
build-images: build-backend build-frontend

## Сохранения образа бекенда в репозиторий.
push-backend:
	echo "pushing backend docker image..."
	docker login && docker push tpc_backend:latest

## Сохранения образа фронтэнда в репозиторий.
push-frontend:
	echo "pushing frontend docker image..."
	docker login && docker push tpc_frontend:latest

## Сохранения образов в репозиторий.
push-images: push-backend push-frontend


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
