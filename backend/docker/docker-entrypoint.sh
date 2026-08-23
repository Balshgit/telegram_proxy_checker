#!/bin/bash
set -e

migrate() {
    alembic upgrade "${ALEMBIC_REVISION:-head}"
}

server() {
    export HOST=${APP_HOST:-0.0.0.0}
    export PORT=${APP_PORT:-8000}
    # Схема БД не создаётся приложением: перед стартом накатываем миграции.
    if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
        migrate
    fi
    exec uvicorn --factory app.main:create_app --host ${HOST} --port ${PORT} --no-use-colors --no-access-log
}

taskiq_scheduler() {
  python -m taskiq scheduler app.taskiq.main:scheduler
}

taskiq_worker() {
  export TASKIQ_WORKERS=${TASKIQ_WORKERS:-1}
  python -m taskiq worker --ack-type when_executed app.taskiq.main:broker -w ${TASKIQ_WORKERS}
}


help() {
  export APP_NAME=${APP_NAME:-prc}

  echo "${APP_NAME} Docker."
  echo ""
  echo "Usage:"
  echo ""
  echo "migrate -- apply alembic migrations (ALEMBIC_REVISION, default: head)"
  echo "server -- start ${APP_NAME} backend"
  echo "taskiq_scheduler -- start ${APP_NAME} taskiq scheduler"
  echo "taskiq_worker -- start ${APP_NAME} taskiq worker"
  echo ""
}

case "${1:-help}" in
  migrate)
    shift
    migrate
    ;;
  server)
    shift
    server
    ;;
  taskiq_scheduler)
    shift
    taskiq_scheduler
    ;;
  taskiq_worker)
    shift
    taskiq_worker
    ;;
  *)
    help
    ;;
esac