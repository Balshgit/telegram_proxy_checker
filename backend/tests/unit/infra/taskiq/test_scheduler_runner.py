import asyncio
from collections.abc import AsyncGenerator, Callable
from datetime import timedelta

import pytest
from taskiq import InMemoryBroker, TaskiqScheduler
from taskiq.schedule_sources import LabelScheduleSource

from app.infra.taskiq.scheduler_runner import (
    SCHEDULER_LOOP_INTERVAL,
    SCHEDULES_UPDATE_INTERVAL,
    TaskiqSchedulerRunner,
)

SCHEDULED_TASK_NAME = "test_interval_task"
TASK_INTERVAL = timedelta(seconds=1)

# Планировщик перед первым тиком досыпает до начала следующей секунды,
# поэтому запас на два срабатывания интервальной задачи — 1s + 1s + 1s.
EXECUTIONS_WAIT_TIMEOUT = 5.0
POLL_STEP = 0.05

EXPECTED_REPEATED_EXECUTIONS = 2


@pytest.fixture
def executions() -> list[None]:
    return []


@pytest.fixture
async def broker(executions: list[None]) -> AsyncGenerator[InMemoryBroker]:
    broker = InMemoryBroker()

    async def scheduled_task() -> None:
        executions.append(None)

    broker.register_task(
        func=scheduled_task,
        task_name=SCHEDULED_TASK_NAME,
        schedule=[{"kwargs": {}, "interval": TASK_INTERVAL}],
    )

    await broker.startup()
    yield broker
    await broker.shutdown()


@pytest.fixture
def scheduler(broker: InMemoryBroker) -> TaskiqScheduler:
    return TaskiqScheduler(broker=broker, sources=[LabelScheduleSource(broker=broker)])


@pytest.fixture
async def runner(scheduler: TaskiqScheduler) -> AsyncGenerator[TaskiqSchedulerRunner]:
    runner = TaskiqSchedulerRunner(scheduler=scheduler)
    yield runner
    await runner.stop()


async def _wait_for(predicate: Callable[[], bool], timeout: float = EXECUTIONS_WAIT_TIMEOUT) -> bool:
    """Ждёт выполнения условия, отдаёт False по таймауту (чтобы падал assert, а не TimeoutError)."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(POLL_STEP)
    return predicate()


def test_default_intervals_match_taskiq_cli_defaults() -> None:
    assert timedelta(seconds=60) == SCHEDULES_UPDATE_INTERVAL
    assert timedelta(seconds=1) == SCHEDULER_LOOP_INTERVAL


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


async def test_scheduled_task_runs_right_after_start(
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
