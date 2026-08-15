from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta
from enum import StrEnum
from typing import Any

from taskiq import AsyncBroker, InMemoryBroker, TaskiqResult
from taskiq.exceptions import UnknownTaskError

from app.core.proxies.tasks import save_proxies_to_database_task


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
    labels: dict[str, Any] = field(default_factory=dict)
    kwargs: dict[str, Any] = field(default_factory=dict)


def register_tasks(broker: AsyncBroker) -> None:
    tasks: list[TaskConfig] = [
        TaskConfig(
            func=save_proxies_to_database_task, labels={"timeout": 30, "retry_on_error": False, "max_retries": 0}
        )
    ]

    for task in tasks:
        broker.register_task(
            func=task.func,
            task_name=task.func.__name__,
            schedule=[{"cron": task.cron, "kwargs": task.kwargs}] if task.cron else [],
            **task.labels,
        )


_TASKS_LATENCY_THRESHOLDS: dict[str, timedelta] = {}


_DEFAULT_THRESHOLD = timedelta(seconds=1)


async def run_task(
    broker: AsyncBroker, func: Callable[..., Any], params: dict[str, Any] | None = None
) -> TaskiqResult[Any]:
    if not params:
        params = {}
    task = broker.find_task(func.__name__)
    if not task:
        # task is not found in broker known tasks, mb you forgot to register it, check register_tasks()
        raise UnknownTaskError(task_name=func.__name__)
    async_task = await task.kiq(**params)
    result = await async_task.wait_result(with_logs=True)
    if isinstance(broker, InMemoryBroker):
        return result.raise_for_error()
    return result
