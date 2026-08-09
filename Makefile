GREEN  := $(shell tput -Txterm setaf 2)
YELLOW := $(shell tput -Txterm setaf 3)
RESET  := $(shell tput -Txterm sgr0)

.PHONY: help format lint lint-style lint-typing lint-imports lint-complexity lint-vulnerabilities app up-app-dependencies down-app-dependencies
.DEFAULT_GOAL := help

## Запустить backend.
backend:
	cd backend && \
	make app
	cd -

## Запустить frontend.
frontend:
	cd frontend && \
	make app
	cd -


## Запуск приложения в докере.
up-docker-app:
	docker compose --profile "app" up -d

## Отключить локальное окружение для приложения.
down-docker-app:
	docker compose --profile "*" down -v


## Сборка приложения.
build-images:
	docker build --platform linux/amd64 -f backend/docker/Dockerfile -t tpc_backend:latest . && \
	docker build --platform linux/amd64 -f frontend/docker/Dockerfile -t tpc_frontend:latest .

## Сохранения образа в репозиторий.
push-images:
	docker login && docker push tpc_backend:latest && docker push tpc_frontend:latest


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
