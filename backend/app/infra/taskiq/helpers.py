from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import timedelta
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Self

from taskiq import AsyncBroker, InMemoryBroker, TaskiqResult
from taskiq.exceptions import UnknownTaskError

from app.core.proxies.tasks import (
    cron_add_new_proxies_to_database_task,
    cron_delete_stale_proxies_task,
    cron_update_proxies_in_database_task,
    save_proxies_to_database_task,
    update_proxies_in_database_task,
)


class TaskPeriodEnum(StrEnum):
    every_minute = "*/1 * * * *"
    every_two_minutes = "*/2 * * * *"
    every_five_minutes = "*/5 * * * *"
    every_hour = "0 */1 * * *"
    every_six_hours = "0 */6 * * *"
    every_day = "0 2 * * *"


@dataclass(frozen=True, kw_only=True, slots=True)
class TaskConfig:
    func: Callable[..., Any]
    cron: TaskPeriodEnum | None = None
    interval: timedelta | None = None
    labels: dict[str, Any] = field(default_factory=dict)
    kwargs: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, kw_only=True, slots=True)
class TaskiqTasks:

    TASKS: tuple[TaskConfig, ...]
    task_names: Mapping[Callable[..., Any], str]

    @classmethod
    def build(cls, *tasks: TaskConfig) -> Self:
        return cls(TASKS=tasks, task_names=MappingProxyType({task.func: task.func.__name__ for task in tasks}))

    def get_task_name(self, func: Callable[..., Any]) -> str:
        task_name = self.task_names.get(func)
        if task_name is None:
            raise UnknownTaskError(task_name=func.__name__)
        return task_name

    @staticmethod
    def build_schedule(task: TaskConfig) -> list[dict[str, Any]]:
        if task.cron is None and task.interval is None:
            return []
        schedule: dict[str, Any] = {"kwargs": task.kwargs}
        if task.cron is not None:
            schedule["cron"] = task.cron
        if task.interval is not None:
            schedule["interval"] = task.interval
        return [schedule]

    def register_tasks(self, broker: AsyncBroker) -> None:
        for task in self.TASKS:
            task_name = self.get_task_name(task.func)
            if broker.find_task(task_name):
                continue
            broker.register_task(
                func=task.func,
                task_name=task_name,
                schedule=self.build_schedule(task),
                **task.labels,
            )

    async def run_task(
        self, broker: AsyncBroker, func: Callable[..., Any], params: dict[str, Any] | None = None
    ) -> TaskiqResult[Any]:
        if not params:
            params = {}
        task_name = self.get_task_name(func)
        task = broker.find_task(task_name)
        if not task:
            raise UnknownTaskError(task_name=task_name)
        async_task = await task.kiq(**params)
        result = await async_task.wait_result(with_logs=True)
        if isinstance(broker, InMemoryBroker):
            return result.raise_for_error()
        return result


taskiq_tasks = TaskiqTasks.build(
    TaskConfig(
        func=save_proxies_to_database_task,
        labels={"timeout": 60, "retry_on_error": False, "max_retries": 0},
    ),
    TaskConfig(
        func=update_proxies_in_database_task,
        labels={"timeout": 60, "retry_on_error": False, "max_retries": 0},
    ),
    TaskConfig(
        func=cron_update_proxies_in_database_task,
        interval=timedelta(hours=1),
        labels={"timeout": 60, "retry_on_error": False, "max_retries": 0},
    ),
    TaskConfig(
        func=cron_delete_stale_proxies_task,
        cron=TaskPeriodEnum.every_day,
        labels={"timeout": 60, "retry_on_error": False, "max_retries": 0},
    ),
    TaskConfig(
        func=cron_add_new_proxies_to_database_task,
        cron=TaskPeriodEnum.every_six_hours,
        labels={"timeout": 30, "retry_on_error": True, "max_retries": 2},
    ),
)
