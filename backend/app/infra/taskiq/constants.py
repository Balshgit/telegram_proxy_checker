from enum import StrEnum


class TaskiqBrokerTypeEnum(StrEnum):
    in_memory = "in-memory"
    aio_pika = "aio-pika"
