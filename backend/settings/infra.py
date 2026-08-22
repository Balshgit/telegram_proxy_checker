from datetime import timedelta
from enum import StrEnum
from functools import cached_property

from pydantic import PostgresDsn, computed_field
from pydantic_settings import BaseSettings

from app.core.types import IntervalSeconds


class TaskiqSettings(BaseSettings):
    TASKIQ_BROKER_URL: str
    TASKIQ_BROKER_TYPE: str

    # Интервалы `TaskiqSchedulerRunner`: как часто планировщик перечитывает расписания и как часто делает тик цикла.
    TASKIQ_SCHEDULES_UPDATE_INTERVAL: IntervalSeconds = timedelta(hours=1)
    TASKIQ_SCHEDULER_LOOP_INTERVAL: IntervalSeconds = timedelta(minutes=5)


class LogLevelEnum(StrEnum):
    CRITICAL = "critical"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    DEBUG = "debug"
    NOTSET = ""


class LogTypeEnum(StrEnum):
    JSON = "json"
    PLAIN = "plain"


class LoggingSettings(BaseSettings):
    LOG_LEVEL: LogLevelEnum
    LOG_TYPE: LogTypeEnum = LogTypeEnum.JSON

    @computed_field  # type: ignore[prop-decorator]
    @cached_property
    def is_json_logs_enabled(self) -> bool:
        return self.LOG_TYPE == LogTypeEnum.JSON


class DatabaseSettings(BaseSettings):

    DB_HOST: str
    POSTGRES_DB_PORT: int
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    DB_SQLALCHEMY_LOGS: bool = False

    @computed_field  # type: ignore[prop-decorator]
    @cached_property
    def DB_SQLALCHEMY_DATABASE_URI(self) -> PostgresDsn:
        return PostgresDsn(
            f"postgresql+asyncpg://{self.POSTGRES_USER}"
            f":{self.POSTGRES_PASSWORD}"
            f"@{self.DB_HOST}"
            f":{self.POSTGRES_DB_PORT}"
            f"/{self.POSTGRES_DB}"
        )


class TestDatabaseSettings(BaseSettings):
    DB_POSTGRES_IMAGE: str = "postgres:18.4"
