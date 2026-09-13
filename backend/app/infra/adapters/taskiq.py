from taskiq import AsyncBroker, InMemoryBroker, SimpleRetryMiddleware
from taskiq_aio_pika import AioPikaBroker

from app.infra.taskiq.helpers import taskiq_tasks


def initialize_taskiq_inmemory_broker() -> AsyncBroker:
    broker = InMemoryBroker().with_middlewares(
        SimpleRetryMiddleware(default_retry_count=0),
    )
    taskiq_tasks.register_tasks(broker)
    return broker


def initialize_taskiq_rabbitmq_broker(broker_url: str) -> AsyncBroker:
    broker = AioPikaBroker(url=broker_url).with_middlewares(
        SimpleRetryMiddleware(default_retry_count=0),
    )
    taskiq_tasks.register_tasks(broker)
    return broker
