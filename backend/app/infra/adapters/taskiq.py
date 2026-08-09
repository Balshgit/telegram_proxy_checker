from taskiq import AsyncBroker, InMemoryBroker, SimpleRetryMiddleware
from taskiq_aio_pika import AioPikaBroker

from app.infra.taskiq.helpers import register_tasks


def initialize_taskiq_inmemory_broker() -> AsyncBroker:
    broker = InMemoryBroker().with_middlewares(
        SimpleRetryMiddleware(default_retry_count=0),
    )
    register_tasks(broker)
    return broker


def initialize_taskiq_rabbitmq_broker(broker_url: str) -> AsyncBroker:
    broker = AioPikaBroker(url=broker_url).with_middlewares(
        SimpleRetryMiddleware(default_retry_count=0),
    )
    register_tasks(broker)
    return broker
