from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from taskiq import InMemoryBroker
from taskiq.exceptions import UnknownTaskError
from taskiq.schedule_sources import LabelScheduleSource

from app.core.proxies.tasks import (
    cron_update_proxies_in_database_task,
    save_proxies_to_database_task,
    update_proxies_in_database_task,
)
from app.infra.taskiq.helpers import (
    TASKS,
    TaskConfig,
    TaskPeriodEnum,
    build_schedule,
    get_task_name,
    register_tasks,
)
from tests.unit.infra.helpers import CRON_TASK_INTERVAL

UNSCHEDULED_TASKS: list[Callable[..., Any]] = [save_proxies_to_database_task, update_proxies_in_database_task]


@pytest.fixture
def broker() -> InMemoryBroker:
    broker = InMemoryBroker()
    register_tasks(broker)
    return broker


def test_cron_task_is_registered_in_broker(broker: InMemoryBroker) -> None:
    assert broker.find_task(get_task_name(cron_update_proxies_in_database_task)) is not None


def test_cron_task_is_scheduled_every_four_hours(broker: InMemoryBroker) -> None:
    task = broker.find_task(get_task_name(cron_update_proxies_in_database_task))

    assert task.labels["schedule"] == [{"kwargs": {}, "interval": CRON_TASK_INTERVAL}]


@pytest.mark.parametrize("task_func", UNSCHEDULED_TASKS)
def test_task_without_schedule_has_empty_schedule_label(
    broker: InMemoryBroker,
    task_func: Callable[..., Any],
) -> None:
    task = broker.find_task(get_task_name(task_func))

    assert task.labels["schedule"] == []


def test_every_task_from_registry_is_registered(broker: InMemoryBroker) -> None:
    registered = set(broker.get_all_tasks())

    assert {get_task_name(config.func) for config in TASKS} <= registered


def test_register_tasks_is_idempotent(broker: InMemoryBroker) -> None:
    before = dict(broker.get_all_tasks())

    register_tasks(broker)

    assert broker.get_all_tasks() == before


def test_get_task_name_raises_on_unregistered_task() -> None:
    async def not_registered_task() -> None: ...

    with pytest.raises(UnknownTaskError):
        get_task_name(not_registered_task)


async def test_label_schedule_source_picks_up_cron_task(broker: InMemoryBroker) -> None:
    source = LabelScheduleSource(broker=broker)

    await source.startup()
    schedules = await source.get_schedules()

    cron_schedules = [
        schedule for schedule in schedules if schedule.task_name == get_task_name(cron_update_proxies_in_database_task)
    ]

    assert len(cron_schedules) == 1
    assert cron_schedules[0].interval == CRON_TASK_INTERVAL
    assert cron_schedules[0].cron is None


async def test_label_schedule_source_ignores_tasks_without_schedule(broker: InMemoryBroker) -> None:
    source = LabelScheduleSource(broker=broker)

    await source.startup()
    scheduled_names = {schedule.task_name for schedule in await source.get_schedules()}

    assert scheduled_names.isdisjoint({get_task_name(task_func) for task_func in UNSCHEDULED_TASKS})


class TestBuildSchedule:
    def test_returns_empty_list_without_cron_and_interval(self) -> None:
        config = TaskConfig(func=cron_update_proxies_in_database_task)

        assert build_schedule(config) == []

    def test_builds_interval_schedule(self) -> None:
        config = TaskConfig(func=cron_update_proxies_in_database_task, interval=timedelta(seconds=5))

        assert build_schedule(config) == [{"kwargs": {}, "interval": timedelta(seconds=5)}]

    def test_builds_cron_schedule(self) -> None:
        config = TaskConfig(func=cron_update_proxies_in_database_task, cron=TaskPeriodEnum.every_minute)

        assert build_schedule(config) == [{"kwargs": {}, "cron": TaskPeriodEnum.every_minute}]

    def test_passes_task_kwargs_into_schedule(self) -> None:
        config = TaskConfig(
            func=cron_update_proxies_in_database_task,
            cron=TaskPeriodEnum.every_hour,
            kwargs={"source_urls": []},
        )

        assert build_schedule(config) == [{"kwargs": {"source_urls": []}, "cron": TaskPeriodEnum.every_hour}]
