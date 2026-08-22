import asyncio
import contextlib
from datetime import timedelta

from loguru import logger
from taskiq import TaskiqScheduler
from taskiq.cli.scheduler.run import SchedulerLoop


class TaskiqSchedulerRunner:
    """
    Запускает taskiq-планировщик внутри процесса приложения.

    Аналог `python -m taskiq scheduler`, но живёт в lifespan FastAPI,
    поэтому все кроновые/интервальные задачи стартуют вместе с приложением.

    Жизненным циклом брокера управляет приложение, поэтому здесь
    поднимаются только источники расписаний и сам цикл планировщика.

    Интервалы приходят из настроек (`TASKIQ_SCHEDULES_UPDATE_INTERVAL`, `TASKIQ_SCHEDULER_LOOP_INTERVAL`),
    дефолтов тут специально нет: значения по умолчанию связывались бы на этапе определения функции,
    и подменить их в тестах было бы нечем.
    """

    def __init__(
        self,
        scheduler: TaskiqScheduler,
        *,
        update_interval: timedelta,
        loop_interval: timedelta,
    ) -> None:
        self._scheduler = scheduler
        self._update_interval = update_interval
        self._loop_interval = loop_interval
        self._loop_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._loop_task is not None:
            return

        for source in self._scheduler.sources:
            await source.startup()

        scheduler_loop = SchedulerLoop(self._scheduler)
        self._loop_task = asyncio.create_task(
            scheduler_loop.run(
                update_interval=self._update_interval,
                loop_interval=self._loop_interval,
                skip_first_run=True,
            ),
            name="taskiq-scheduler-loop",
        )
        all_tasks = self._scheduler.broker.get_all_tasks()
        scheduled_tasks = []
        for task_name, task in all_tasks.items():
            if scheduled_labels := task.labels["schedule"]:
                scheduled_tasks.append({task_name: scheduled_labels})
        logger.info("taskiq scheduler started", scheduled_tasks=scheduled_tasks)

    async def stop(self) -> None:
        if self._loop_task is None:
            return

        self._loop_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._loop_task
        self._loop_task = None

        for source in self._scheduler.sources:
            await source.shutdown()
        logger.info("taskiq scheduler stopped")
