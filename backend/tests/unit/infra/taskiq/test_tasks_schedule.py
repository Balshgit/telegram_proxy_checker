from collections.abc import Callable
from dataclasses import FrozenInstanceError
from datetime import timedelta
from typing import Any

import pytest
from taskiq import InMemoryBroker
from taskiq.exceptions import UnknownTaskError
from taskiq.schedule_sources import LabelScheduleSource

from app.core.proxies.tasks import (
    cron_add_proxies_to_database_task,
    cron_delete_stale_proxies_task,
    cron_update_proxies_in_database_task,
    save_proxies_to_database_task,
    update_proxies_in_database_task,
)
from app.infra.taskiq.helpers import TaskConfig, TaskiqTasks, TaskPeriodEnum, taskiq_tasks
from tests.unit.infra.helpers import (
    ADD_PROXIES_TASK_CRON,
    ADD_PROXIES_TASK_LABELS,
    CLEANUP_TASK_CRON,
    CRON_TASK_INTERVAL,
)

UNSCHEDULED_TASKS: list[Callable[..., Any]] = [save_proxies_to_database_task, update_proxies_in_database_task]


@pytest.fixture(scope="module")
def broker() -> InMemoryBroker:
    broker = InMemoryBroker()
    taskiq_tasks.register_tasks(broker)
    return broker


def test_cron_task_is_registered_in_broker(broker: InMemoryBroker) -> None:
    assert broker.find_task(taskiq_tasks.get_task_name(cron_update_proxies_in_database_task)) is not None


def test_cron_task_is_scheduled_every_four_hours(broker: InMemoryBroker) -> None:
    task = broker.find_task(taskiq_tasks.get_task_name(cron_update_proxies_in_database_task))

    assert task.labels["schedule"] == [{"kwargs": {}, "interval": CRON_TASK_INTERVAL}]


def test_cleanup_task_is_registered_in_broker(broker: InMemoryBroker) -> None:
    assert broker.find_task(taskiq_tasks.get_task_name(cron_delete_stale_proxies_task)) is not None


def test_cleanup_task_is_scheduled_daily_at_three_am(broker: InMemoryBroker) -> None:
    task = broker.find_task(taskiq_tasks.get_task_name(cron_delete_stale_proxies_task))

    assert task.labels["schedule"] == [{"kwargs": {}, "cron": CLEANUP_TASK_CRON}]


def test_every_day_period_is_three_am() -> None:
    assert TaskPeriodEnum.every_day == CLEANUP_TASK_CRON


def test_add_proxies_task_is_registered_in_broker(broker: InMemoryBroker) -> None:
    assert broker.find_task(taskiq_tasks.get_task_name(cron_add_proxies_to_database_task)) is not None


def test_add_proxies_task_is_scheduled_every_six_hours(broker: InMemoryBroker) -> None:
    task = broker.find_task(taskiq_tasks.get_task_name(cron_add_proxies_to_database_task))

    assert task.labels["schedule"] == [{"kwargs": {}, "cron": ADD_PROXIES_TASK_CRON}]


def test_every_six_hours_period_is_start_of_every_sixth_hour() -> None:
    assert TaskPeriodEnum.every_six_hours == ADD_PROXIES_TASK_CRON


def test_add_proxies_task_is_retried_on_error(broker: InMemoryBroker) -> None:
    """
    Единственная задача с ретраями: пропущенный добор проксей — это минус 6 часов свежих записей,
    поэтому разовая ошибка похода в github должна повторяться, а не молча гаситься до следующего крона.
    """
    task = broker.find_task(taskiq_tasks.get_task_name(cron_add_proxies_to_database_task))

    assert {label: task.labels[label] for label in ADD_PROXIES_TASK_LABELS} == ADD_PROXIES_TASK_LABELS


@pytest.mark.parametrize("task_func", [cron_update_proxies_in_database_task, cron_delete_stale_proxies_task])
def test_other_cron_tasks_are_not_retried(broker: InMemoryBroker, task_func: Callable[..., Any]) -> None:
    """Контраст к тесту выше: остальные кроны отрабатывают ровно один раз и ждут следующего запуска."""
    task = broker.find_task(taskiq_tasks.get_task_name(task_func))

    assert task.labels["retry_on_error"] is False
    assert task.labels["max_retries"] == 0


@pytest.mark.parametrize("task_func", UNSCHEDULED_TASKS)
def test_task_without_schedule_has_empty_schedule_label(
    broker: InMemoryBroker,
    task_func: Callable[..., Any],
) -> None:
    task = broker.find_task(taskiq_tasks.get_task_name(task_func))

    assert task.labels["schedule"] == []


def test_every_task_from_registry_is_registered(broker: InMemoryBroker) -> None:
    registered = set(broker.get_all_tasks())

    assert {taskiq_tasks.get_task_name(config.func) for config in taskiq_tasks.TASKS} <= registered


def test_register_tasks_is_idempotent(broker: InMemoryBroker) -> None:
    before = dict(broker.get_all_tasks())

    taskiq_tasks.register_tasks(broker)

    assert broker.get_all_tasks() == before


def test_get_task_name_raises_on_unregistered_task() -> None:
    async def not_registered_task() -> None: ...

    with pytest.raises(UnknownTaskError):
        taskiq_tasks.get_task_name(not_registered_task)


async def test_label_schedule_source_picks_up_cron_task(broker: InMemoryBroker) -> None:
    source = LabelScheduleSource(broker=broker)

    await source.startup()
    schedules = await source.get_schedules()

    cron_schedules = [
        schedule
        for schedule in schedules
        if schedule.task_name == taskiq_tasks.get_task_name(cron_update_proxies_in_database_task)
    ]

    assert len(cron_schedules) == 1
    assert cron_schedules[0].interval == CRON_TASK_INTERVAL
    assert cron_schedules[0].cron is None


async def test_label_schedule_source_picks_up_cleanup_task(broker: InMemoryBroker) -> None:
    source = LabelScheduleSource(broker=broker)

    await source.startup()
    schedules = await source.get_schedules()

    cleanup_schedules = [
        schedule
        for schedule in schedules
        if schedule.task_name == taskiq_tasks.get_task_name(cron_delete_stale_proxies_task)
    ]

    assert len(cleanup_schedules) == 1
    assert cleanup_schedules[0].cron == CLEANUP_TASK_CRON
    assert cleanup_schedules[0].interval is None


async def test_label_schedule_source_picks_up_add_proxies_task(broker: InMemoryBroker) -> None:
    source = LabelScheduleSource(broker=broker)

    await source.startup()
    schedules = await source.get_schedules()

    add_proxies_schedules = [
        schedule
        for schedule in schedules
        if schedule.task_name == taskiq_tasks.get_task_name(cron_add_proxies_to_database_task)
    ]

    assert len(add_proxies_schedules) == 1
    assert add_proxies_schedules[0].cron == ADD_PROXIES_TASK_CRON
    assert add_proxies_schedules[0].interval is None


async def test_label_schedule_source_ignores_tasks_without_schedule(broker: InMemoryBroker) -> None:
    source = LabelScheduleSource(broker=broker)

    await source.startup()
    scheduled_names = {schedule.task_name for schedule in await source.get_schedules()}

    assert scheduled_names.isdisjoint({taskiq_tasks.get_task_name(task_func) for task_func in UNSCHEDULED_TASKS})


class TestBuildSchedule:
    def test_returns_empty_list_without_cron_and_interval(self) -> None:
        config = TaskConfig(func=cron_update_proxies_in_database_task)

        assert taskiq_tasks.build_schedule(config) == []

    def test_builds_interval_schedule(self) -> None:
        config = TaskConfig(func=cron_update_proxies_in_database_task, interval=timedelta(seconds=5))

        assert taskiq_tasks.build_schedule(config) == [{"kwargs": {}, "interval": timedelta(seconds=5)}]

    def test_builds_cron_schedule(self) -> None:
        config = TaskConfig(func=cron_update_proxies_in_database_task, cron=TaskPeriodEnum.every_minute)

        assert taskiq_tasks.build_schedule(config) == [{"kwargs": {}, "cron": TaskPeriodEnum.every_minute}]

    def test_passes_task_kwargs_into_schedule(self) -> None:
        config = TaskConfig(
            func=cron_update_proxies_in_database_task,
            cron=TaskPeriodEnum.every_hour,
            kwargs={"source_urls": []},
        )

        assert taskiq_tasks.build_schedule(config) == [
            {"kwargs": {"source_urls": []}, "cron": TaskPeriodEnum.every_hour}
        ]


class TestTaskiqTasksIsImmutable:
    """
    Реестр собирается один раз на импорте модуля и дальше только читается.

    Подменить набор задач или кэш имён в рантайме нельзя: брокеров в приложении несколько,
    и любая правка реестра «на лету» развела бы их по разным наборам задач.
    """

    def test_tasks_cannot_be_reassigned(self) -> None:
        with pytest.raises(FrozenInstanceError):
            taskiq_tasks.TASKS = []

    def test_task_names_cannot_be_reassigned(self) -> None:
        with pytest.raises(FrozenInstanceError):
            taskiq_tasks.task_names = {}

    def test_tasks_cannot_be_mutated_in_place(self) -> None:
        """`tuple`, а не `list`: дописать задачу в уже собранный реестр тоже нельзя."""
        with pytest.raises(AttributeError):
            taskiq_tasks.TASKS.append(TaskConfig(func=cron_add_proxies_to_database_task))

    def test_task_names_cannot_be_mutated_in_place(self) -> None:
        """`MappingProxyType`: кэш имён отдаётся только на чтение."""
        with pytest.raises(TypeError):
            taskiq_tasks.task_names[cron_add_proxies_to_database_task] = "some_other_name"

    def test_registry_has_no_instance_dict(self) -> None:
        """
        `slots=True`: у реестра нет `__dict__`, поэтому дописать в него новое поле нельзя.

        Проверяем именно отсутствие `__dict__`, а не тип исключения при присваивании:
        для `frozen` + `slots` он разъезжается от версии к версии python.
        """
        assert not hasattr(taskiq_tasks, "__dict__")


class TestTaskiqTasksRegistry:
    """
    Тесты реестра как объекта.

    Собственные задачи объявляются прямо в тестах, а не берутся из `app.core.proxies.tasks`:
    `AsyncBroker.register_task` дописывает к `__name__` исходной функции суффикс, поэтому
    боевые задачи к этому моменту уже зарегистрированы соседними тестами и их `__name__` испорчен.
    Именно от этого реестр и защищает, считая имена один раз — до первой регистрации в брокере.
    """

    def test_task_name_is_built_for_every_configured_task(self) -> None:
        assert [taskiq_tasks.get_task_name(config.func) for config in taskiq_tasks.TASKS] == [
            "save_proxies_to_database_task",
            "update_proxies_in_database_task",
            "cron_update_proxies_in_database_task",
            "cron_delete_stale_proxies_task",
            "cron_add_proxies_to_database_task",
        ]

    def test_registry_knows_only_its_own_tasks(self) -> None:
        """Кэш имён считается по своему списку задач, а не по глобальному реестру."""

        async def own_task() -> None: ...

        async def foreign_task() -> None: ...

        registry = TaskiqTasks.build(TaskConfig(func=own_task))

        assert registry.get_task_name(own_task) == "own_task"

        with pytest.raises(UnknownTaskError):
            registry.get_task_name(foreign_task)

    def test_registry_registers_only_its_own_tasks(self) -> None:
        """Брокер получает ровно тот набор задач, который лежит в реестре."""

        async def own_task() -> None: ...

        registry = TaskiqTasks.build(TaskConfig(func=own_task))
        broker = InMemoryBroker()

        registry.register_tasks(broker)

        assert set(broker.get_all_tasks()) == {"own_task"}

    def test_task_names_are_cached_before_broker_rewrites_them(self) -> None:
        """
        Имя задачи в брокере остаётся тем, что реестр посчитал при создании.

        Это и есть причина, по которой `taskiq_tasks` собирается на импорте модуля:
        после регистрации `__name__` исходной функции уже не годится в качестве имени задачи.
        """

        async def own_task() -> None: ...

        registry = TaskiqTasks.build(TaskConfig(func=own_task))
        broker = InMemoryBroker()

        registry.register_tasks(broker)
        registry.register_tasks(InMemoryBroker())

        assert registry.get_task_name(own_task) == "own_task"
        assert set(broker.get_all_tasks()) == {"own_task"}
