from collections.abc import Callable
from typing import Any

from loguru import logger
from taskiq import AsyncBroker, AsyncTaskiqTask, TaskiqResult
from taskiq.exceptions import UnknownTaskError

from app.infra.taskiq.helpers import get_task_name


class TaskiqTasksExecutor:
    def __init__(self, broker: AsyncBroker) -> None:
        self.broker = broker

    async def run(
        self, func: Callable[..., Any], params: dict[str, Any], execution_options: dict[str, Any] | None = None
    ) -> AsyncTaskiqTask[Any]:
        task_name = get_task_name(func)
        logger.info("creating taskiq task", task_name=task_name, params=params)
        task = self.broker.find_task(task_name)
        if not task:
            # task is not found in broker known tasks, mb you forgot to register it, check register_tasks()
            raise UnknownTaskError(task_name=task_name)
        if execution_options is None:
            execution_options = {}
        async_task = await task.kicker().with_labels(**execution_options).kiq(**params)
        logger.info("taskiq task created", task_name=task_name, task_id=async_task.task_id)
        return async_task

    async def get_result_by_task_id(self, task_id: str) -> TaskiqResult[Any]:
        return await self.broker.result_backend.get_result(task_id)

    async def get_last_result(self) -> TaskiqResult[Any]:
        """Used only in tests"""
        last_task_id = next(reversed(self.broker.result_backend.results))  # type: ignore[attr-defined]
        return await self.get_result_by_task_id(last_task_id)
