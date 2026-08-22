import asyncio
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from taskiq import InMemoryBroker, TaskiqScheduler
from taskiq.cli.scheduler.run import SchedulerLoop
from taskiq.schedule_sources import LabelScheduleSource
from taskiq.scheduler.scheduled_task import ScheduledTask

from app.core.proxies.tasks import cron_update_proxies_in_database_task
from app.infra.taskiq.helpers import get_task_name, register_tasks
from app.infra.taskiq.scheduler_runner import TaskiqSchedulerRunner
from settings.config import AppTestSettings
from tests.unit.infra.helpers import (
    CRON_TASK_INTERVAL,
    SCHEDULED_TASK_NAME,
    SCHEDULER_LOOP_INTERVAL_FOR_TESTS,
    SCHEDULES_UPDATE_INTERVAL_FOR_TESTS,
    TASK_INTERVAL,
    UNREACHABLE_TASK_INTERVAL,
)

# Планировщик перед первым тиком досыпает до начала следующей секунды, первый запуск отложен
# на интервал, поэтому запас на два срабатывания интервальной задачи — 1s + 1s + 1s + 1s.
EXECUTIONS_WAIT_TIMEOUT = 6.0
POLL_STEP = 0.05

# Досып до начала секунды (<1s) плюс два полноценных тика цикла: если бы первый запуск не был
# отложен, таска успела бы уйти на выполнение задолго до конца этого окна.
FIRST_TICKS_WAIT = 2.5

EXPECTED_REPEATED_EXECUTIONS = 2


async def _wait_for(predicate: Callable[[], bool], timeout: float = EXECUTIONS_WAIT_TIMEOUT) -> bool:
    """Ждёт выполнения условия, отдаёт False по таймауту (чтобы падал assert, а не TimeoutError)."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(POLL_STEP)
    return predicate()


def test_default_intervals_match_taskiq_cli_defaults(test_settings: AppTestSettings) -> None:
    assert timedelta(seconds=3600) == test_settings.TASKIQ_SCHEDULES_UPDATE_INTERVAL
    assert timedelta(seconds=300) == test_settings.TASKIQ_SCHEDULER_LOOP_INTERVAL


def test_runner_takes_intervals_from_overridden_settings(runner: TaskiqSchedulerRunner) -> None:
    """Фиксирует, что ужатые интервалы действительно доехали из настроек в раннер через контейнер."""
    assert runner._update_interval == SCHEDULES_UPDATE_INTERVAL_FOR_TESTS
    assert runner._loop_interval == SCHEDULER_LOOP_INTERVAL_FOR_TESTS


async def test_start_launches_scheduler_loop(runner: TaskiqSchedulerRunner) -> None:
    await runner.start()

    assert runner._loop_task is not None
    assert not runner._loop_task.done()
    assert runner._loop_task.get_name() == "taskiq-scheduler-loop"


async def test_start_boots_schedule_sources(runner: TaskiqSchedulerRunner, scheduler: TaskiqScheduler) -> None:
    source = scheduler.sources[0]

    assert await source.get_schedules() == []

    await runner.start()

    schedules = await source.get_schedules()

    assert [schedule.task_name for schedule in schedules] == [SCHEDULED_TASK_NAME]


async def test_start_is_idempotent(runner: TaskiqSchedulerRunner) -> None:
    await runner.start()
    loop_task = runner._loop_task

    await runner.start()

    assert runner._loop_task is loop_task


async def test_stop_cancels_scheduler_loop(runner: TaskiqSchedulerRunner) -> None:
    await runner.start()
    loop_task = runner._loop_task

    await runner.stop()

    assert loop_task.cancelled()
    assert runner._loop_task is None


async def test_stop_without_start_does_nothing(runner: TaskiqSchedulerRunner) -> None:
    await runner.stop()

    assert runner._loop_task is None


async def test_scheduler_can_be_restarted(runner: TaskiqSchedulerRunner) -> None:
    await runner.start()
    first_loop_task = runner._loop_task
    await runner.stop()

    await runner.start()

    assert runner._loop_task is not None
    assert runner._loop_task is not first_loop_task
    assert not runner._loop_task.done()


async def test_scheduled_task_runs_after_first_interval(
    runner: TaskiqSchedulerRunner,
    executions: list[None],
) -> None:
    await runner.start()

    assert await _wait_for(lambda: len(executions) >= 1)


async def test_scheduled_task_runs_repeatedly_by_interval(
    runner: TaskiqSchedulerRunner,
    executions: list[None],
) -> None:
    await runner.start()

    assert await _wait_for(lambda: len(executions) >= EXPECTED_REPEATED_EXECUTIONS)


@pytest.mark.parametrize("task_interval", [UNREACHABLE_TASK_INTERVAL])
async def test_scheduled_task_does_not_run_on_start(
    runner: TaskiqSchedulerRunner,
    executions: list[None],
) -> None:
    """
    Главный регресс: интервальная (кроновая) задача не должна улетать на выполнение при старте.

    `skip_first_run=True` в taskiq гасит только cron-расписания, а `is_interval_task_now`
    при `last_run is None` отдаёт True, поэтому без явной пометки в `interval_tasks_last_run`
    таска с интервалом в 4 часа отрабатывала прямо в lifespan приложения.
    """
    await runner.start()

    await asyncio.sleep(FIRST_TICKS_WAIT)

    assert executions == []


@pytest.mark.parametrize("task_interval", [UNREACHABLE_TASK_INTERVAL])
async def test_restart_does_not_run_scheduled_task_on_start(
    runner: TaskiqSchedulerRunner,
    executions: list[None],
) -> None:
    """Перезапуск раннера создаёт новый `SchedulerLoop`, поэтому пометку нужно ставить заново."""
    await runner.start()
    await runner.stop()

    await runner.start()
    await asyncio.sleep(FIRST_TICKS_WAIT)

    assert executions == []


async def test_start_marks_every_interval_schedule_as_already_run(
    runner: TaskiqSchedulerRunner,
    scheduler: TaskiqScheduler,
) -> None:
    source = scheduler.sources[0]
    await source.startup()
    scheduler_loop = SchedulerLoop(scheduler)

    await runner._skip_first_interval_run(scheduler_loop)

    interval_schedule_ids = {
        schedule.schedule_id for schedule in await source.get_schedules() if schedule.interval is not None
    }

    assert interval_schedule_ids
    assert set(scheduler_loop.interval_tasks_last_run) == interval_schedule_ids


class TestRealCronTaskFirstRun:
    """
    Проверяет боевую `cron_update_proxies_in_database_task` из реестра `TASKS`.

    Без ожиданий: спрашиваем сам taskiq, считает ли он задачу готовой к отправке —
    сразу после старта и когда её интервал уже истёк.
    """

    @staticmethod
    async def _build_primed_loop(runner: TaskiqSchedulerRunner, scheduler: TaskiqScheduler) -> SchedulerLoop:
        scheduler_loop = SchedulerLoop(scheduler)
        scheduler_loop.scheduled_tasks = [(source, await source.get_schedules()) for source in scheduler.sources]
        await runner._skip_first_interval_run(scheduler_loop)
        return scheduler_loop

    @pytest.fixture
    async def scheduler(self) -> TaskiqScheduler:
        broker = InMemoryBroker()
        register_tasks(broker)
        source = LabelScheduleSource(broker=broker)
        await source.startup()
        return TaskiqScheduler(broker=broker, sources=[source])

    @pytest.fixture
    def runner(self, scheduler: TaskiqScheduler) -> TaskiqSchedulerRunner:
        return TaskiqSchedulerRunner(
            scheduler=scheduler,
            update_interval=SCHEDULES_UPDATE_INTERVAL_FOR_TESTS,
            loop_interval=SCHEDULER_LOOP_INTERVAL_FOR_TESTS,
        )

    @staticmethod
    def _find_cron_schedule(scheduler_loop: SchedulerLoop) -> ScheduledTask:
        task_name = get_task_name(cron_update_proxies_in_database_task)
        schedules = [
            schedule
            for _, task_list in scheduler_loop.scheduled_tasks
            for schedule in task_list
            if schedule.task_name == task_name
        ]

        assert len(schedules) == 1
        return schedules[0]

    async def test_is_not_ready_to_send_right_after_start(
        self,
        runner: TaskiqSchedulerRunner,
        scheduler: TaskiqScheduler,
    ) -> None:
        scheduler_loop = await self._build_primed_loop(runner=runner, scheduler=scheduler)
        cron_schedule = self._find_cron_schedule(scheduler_loop)

        assert not scheduler_loop._is_schedule_ready_to_send(task=cron_schedule, now=datetime.now(tz=UTC))

    async def test_is_ready_to_send_when_interval_elapsed(
        self,
        runner: TaskiqSchedulerRunner,
        scheduler: TaskiqScheduler,
    ) -> None:
        scheduler_loop = await self._build_primed_loop(runner=runner, scheduler=scheduler)
        cron_schedule = self._find_cron_schedule(scheduler_loop)

        now = datetime.now(tz=UTC) + CRON_TASK_INTERVAL

        assert scheduler_loop._is_schedule_ready_to_send(task=cron_schedule, now=now)


async def test_scheduled_task_stops_after_runner_is_stopped(
    runner: TaskiqSchedulerRunner,
    executions: list[None],
) -> None:
    await runner.start()
    await _wait_for(lambda: len(executions) >= 1)

    await runner.stop()
    executions_on_stop = len(executions)

    await asyncio.sleep(TASK_INTERVAL.total_seconds() * 1.5)

    assert len(executions) == executions_on_stop
