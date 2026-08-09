from collections.abc import Callable
from typing import Any

from taskiq import (
    TaskiqEvents,
    TaskiqState,
)

from app.di.dependency_injector import Container
from app.infra.logging import configure_logging
from app.infra.taskiq.helpers import register_tasks, run_task
from settings.config import AppSettings


class TaskiqApplication:
    def __init__(self, settings: AppSettings, container: Container):
        self.broker = container.infra.taskiq_broker()
        self.scheduler = container.infra.taskiq_scheduler()
        self.add_event_handlers()
        register_tasks(self.broker)
        configure_logging(
            level=settings.LOG_LEVEL,
            enable_json_logs=settings.is_json_logs_enabled,
        )
        self.broker.state.container = container

    def add_event_handlers(self) -> None:
        self.broker.add_event_handler(TaskiqEvents.WORKER_STARTUP, startup)
        self.broker.add_event_handler(TaskiqEvents.WORKER_SHUTDOWN, shutdown)


async def startup(state: TaskiqState) -> None:  # pragma: no cover
    start_coro = state.container.init_resources()
    if start_coro:
        await start_coro


async def shutdown(state: TaskiqState) -> None:  # pragma: no cover
    shutdown_coro = state.container.shutdown_resources()
    if shutdown_coro:
        await shutdown_coro


async def run_standalone_task(func: Callable[..., Any]) -> None:
    settings = AppSettings()
    app = create_taskiq_application(settings=settings)
    broker = app.broker
    await broker.startup()
    await run_task(broker, func)
    await broker.shutdown()


def create_taskiq_application(
    settings: AppSettings | None = None,
    di_container: Container | None = None,
) -> TaskiqApplication:
    settings = settings or AppSettings()
    di_container = di_container or Container()
    di_container.config.from_pydantic(settings)
    return TaskiqApplication(settings=settings, container=di_container)
