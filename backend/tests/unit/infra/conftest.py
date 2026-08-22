from collections.abc import AsyncGenerator
from datetime import timedelta

import pytest
from taskiq import AsyncBroker, TaskiqScheduler

from app.di.dependency_injector import Container
from app.infra.taskiq.scheduler_runner import TaskiqSchedulerRunner
from settings.config import AppTestSettings
from tests.support.helpers import override_settings
from tests.unit.infra.helpers import (
    CONTROL_TASK_NAME,
    SCHEDULED_TASK_NAME,
    SCHEDULER_LOOP_INTERVAL_FOR_TESTS,
    SCHEDULES_UPDATE_INTERVAL_FOR_TESTS,
    TASK_INTERVAL,
)


@pytest.fixture
def executions() -> list[None]:
    return []


@pytest.fixture
def task_interval() -> timedelta:
    """Интервал тестовой таски. Тест может подменить его через `parametrize`."""
    return TASK_INTERVAL


@pytest.fixture
async def taskiq_container(
    container: Container,
    test_settings: AppTestSettings,
) -> AsyncGenerator[Container]:
    """
    Контейнер с ужатыми интервалами планировщика.

    `override_settings` дёргает `reset_singletons`, поэтому брокер, планировщик и раннер
    пересобираются и на входе, и на выходе: тестовая таска не утекает в соседние тесты.
    """
    scheduler_test_settings = test_settings.model_copy(
        update={
            "TASKIQ_SCHEDULES_UPDATE_INTERVAL": SCHEDULES_UPDATE_INTERVAL_FOR_TESTS,
            "TASKIQ_SCHEDULER_LOOP_INTERVAL": SCHEDULER_LOOP_INTERVAL_FOR_TESTS,
        }
    )
    async with override_settings(
        test_settings=test_settings, new_settings=scheduler_test_settings, container=container
    ):
        yield container


@pytest.fixture
async def broker(
    taskiq_container: Container,
    executions: list[None],
    task_interval: timedelta,
) -> AsyncGenerator[AsyncBroker]:
    broker = taskiq_container.infra.taskiq_broker()

    async def scheduled_task() -> None:
        executions.append(None)

    # В брокере из контейнера уже зарегистрированы боевые таски, в том числе кроновая с интервалом
    # в 4 часа. Планировщику здесь нужна только быстрая тестовая таска, иначе первый же тик отправит
    # на выполнение боевую.
    broker.local_task_registry.clear()
    broker.register_task(
        func=scheduled_task,
        task_name=SCHEDULED_TASK_NAME,
        schedule=[{"kwargs": {}, "interval": task_interval}],
    )

    await broker.startup()
    yield broker
    await broker.shutdown()


@pytest.fixture
def control_executions() -> list[None]:
    return []


@pytest.fixture
def control_task(broker: AsyncBroker, control_executions: list[None]) -> None:
    """
    Таска-маячок с минимальным интервалом.

    Её срабатывание — надёжный признак того, что цикл планировщика сделал тик и успел
    оценить все расписания. Негативным тестам это позволяет не спать «с запасом»:
    дождались маячка — значит незапрошенный первый запуск уже был бы виден.

    Регистрируется после фикстуры `broker`, но до `runner.start()`, который заново
    поднимает источник расписаний и подхватывает таску.
    """

    async def control_task() -> None:
        control_executions.append(None)

    broker.register_task(
        func=control_task,
        task_name=CONTROL_TASK_NAME,
        schedule=[{"kwargs": {}, "interval": TASK_INTERVAL}],
    )


@pytest.fixture
def scheduler(taskiq_container: Container, broker: AsyncBroker) -> TaskiqScheduler:
    """Зависит от `broker`, чтобы тестовая таска была зарегистрирована до чтения расписаний."""
    return taskiq_container.infra.taskiq_scheduler()


@pytest.fixture
async def runner(taskiq_container: Container, scheduler: TaskiqScheduler) -> AsyncGenerator[TaskiqSchedulerRunner]:
    runner = taskiq_container.infra.taskiq_scheduler_runner()
    yield runner
    await runner.stop()
