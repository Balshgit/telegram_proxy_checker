from dependency_injector import containers, providers
from taskiq import TaskiqScheduler
from taskiq.schedule_sources import LabelScheduleSource

from app.infra.adapters.taskiq import initialize_taskiq_inmemory_broker, initialize_taskiq_rabbitmq_broker
from app.infra.sqlalchemy.engines import DatabaseEngines
from app.infra.taskiq.constants import TaskiqBrokerTypeEnum
from app.infra.taskiq.executor import TaskiqTasksExecutor
from app.infra.taskiq.scheduler_runner import TaskiqSchedulerRunner


class InfraContainer(containers.DeclarativeContainer):
    config = providers.Configuration(strict=True)

    database_engines: providers.Singleton[DatabaseEngines] = providers.Singleton(DatabaseEngines.build, settings=config)

    taskiq_in_memory_broker = providers.Singleton(
        initialize_taskiq_inmemory_broker,
    )

    taskiq_rabbitmq_broker = providers.Singleton(
        initialize_taskiq_rabbitmq_broker,
        broker_url=config.TASKIQ_BROKER_URL,
    )

    taskiq_broker = providers.Selector(
        config.TASKIQ_BROKER_TYPE,
        **{
            str(TaskiqBrokerTypeEnum.in_memory): taskiq_in_memory_broker,
            str(TaskiqBrokerTypeEnum.aio_pika): taskiq_rabbitmq_broker,
        },
    )

    taskiq_broker_source = providers.Singleton(LabelScheduleSource, broker=taskiq_broker)
    taskiq_scheduler = providers.Singleton(
        TaskiqScheduler, broker=taskiq_broker, sources=providers.List(taskiq_broker_source)
    )
    taskiq_tasks_executor = providers.Singleton(TaskiqTasksExecutor, broker=taskiq_broker)
    taskiq_scheduler_runner = providers.Singleton(TaskiqSchedulerRunner, scheduler=taskiq_scheduler)
