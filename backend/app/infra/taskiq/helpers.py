from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta
from enum import StrEnum
from typing import Any

from taskiq import AsyncBroker, InMemoryBroker, TaskiqResult
from taskiq.exceptions import UnknownTaskError

from app.core.proxies.tasks import (
    cron_update_proxies_in_database_task,
    save_proxies_to_database_task,
    update_proxies_in_database_task,
)


class TaskPeriodEnum(StrEnum):
    every_minute = "*/1 * * * *"
    every_two_minutes = "*/2 * * * *"
    every_five_minutes = "*/5 * * * *"
    every_hour = "0 */1 * * *"
    every_day = "0 */24 * * *"


@dataclass(frozen=True, kw_only=True, slots=True)
class TaskConfig:
    func: Callable[..., Any]
    cron: TaskPeriodEnum | None = None
    interval: timedelta | None = None
    labels: dict[str, Any] = field(default_factory=dict)
    kwargs: dict[str, Any] = field(default_factory=dict)


TASKS: list[TaskConfig] = [
    TaskConfig(func=save_proxies_to_database_task, labels={"timeout": 30, "retry_on_error": False, "max_retries": 0}),
    TaskConfig(func=update_proxies_in_database_task, labels={"timeout": 30, "retry_on_error": False, "max_retries": 0}),
    TaskConfig(
        func=cron_update_proxies_in_database_task,
        interval=timedelta(hours=4),
        labels={"timeout": 10, "retry_on_error": False, "max_retries": 0},
    ),
]

_TASK_NAMES: dict[Callable[..., Any], str] = {config.func: config.func.__name__ for config in TASKS}


def get_task_name(func: Callable[..., Any]) -> str:
    task_name = _TASK_NAMES.get(func)
    if task_name is None:
        raise UnknownTaskError(task_name=func.__name__)
    return task_name


def build_schedule(task: TaskConfig) -> list[dict[str, Any]]:
    if task.cron is None and task.interval is None:
        return []
    schedule: dict[str, Any] = {"kwargs": task.kwargs}
    if task.cron is not None:
        schedule["cron"] = task.cron
    if task.interval is not None:
        schedule["interval"] = task.interval
    return [schedule]


def register_tasks(broker: AsyncBroker) -> None:
    for task in TASKS:
        task_name = get_task_name(task.func)
        if broker.find_task(task_name):
            continue
        broker.register_task(
            func=task.func,
            task_name=task_name,
            schedule=build_schedule(task),
            **task.labels,
        )


async def run_task(
    broker: AsyncBroker, func: Callable[..., Any], params: dict[str, Any] | None = None
) -> TaskiqResult[Any]:
    if not params:
        params = {}
    task_name = get_task_name(func)
    task = broker.find_task(task_name)
    if not task:
        raise UnknownTaskError(task_name=task_name)
    async_task = await task.kiq(**params)
    result = await async_task.wait_result(with_logs=True)
    if isinstance(broker, InMemoryBroker):
        return result.raise_for_error()
    return result
