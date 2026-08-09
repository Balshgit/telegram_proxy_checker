import os
import typing
from enum import StrEnum, unique
from functools import lru_cache

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

from settings.infra import (
    DatabaseSettings,
    LoggingSettings,
    TaskiqSettings,
    TestDatabaseSettings,
)


@unique
class StageEnum(StrEnum):
    dev = "dev"
    ci_runtests = "ci.runtests"
    local_runtests = "local.runtests"
    production = "production"


class BaseAppSettings(BaseSettings):
    VERSION: str = "unknown"
    STAGE: StageEnum
    APP_HOST: str
    APP_PORT: int
    DEBUG: bool
    TIME_ZONE: int
    API_ROOT_PATH: str


class AppSettings(
    TaskiqSettings,
    LoggingSettings,
    DatabaseSettings,
    BaseAppSettings,
    BaseSettings,
):
    model_config = SettingsConfigDict(env_file=os.path.join(os.path.dirname(__file__), ".envs/.env"))


class AppTestSettings(TestDatabaseSettings, AppSettings):
    TESTS_CALL_COUNT: int = 0
    model_config = SettingsConfigDict(env_file=os.path.join(os.path.dirname(__file__), ".envs/.env.tests"))


environments: dict[str, type[AppSettings]] = {
    StageEnum.production: AppSettings,
    StageEnum.dev: AppSettings,
    StageEnum.local_runtests: AppTestSettings,
    StageEnum.ci_runtests: AppTestSettings,
}


@lru_cache(maxsize=None)  # noqa: UP033
def load_app_settings(stage: StageEnum | None = None) -> AppSettings:
    app_env = stage or AppSettings().STAGE
    environment_path = None
    match app_env:
        case StageEnum.production:
            environment_path = None
        case StageEnum.dev | StageEnum.production:
            environment_path = "../envs/.env"
        case StageEnum.local_runtests:
            environment_path = "../envs/.env.tests"
        case StageEnum.ci_runtests:
            environment_path = "../envs/.env.ci.runtests"
        case _ as unreachable:
            typing.assert_never(unreachable)
    if environment_path:
        load_dotenv(environment_path)
    config = environments[app_env]
    return config()
