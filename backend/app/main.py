from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from sqlalchemy.orm import configure_mappers
from taskiq import InMemoryBroker

from app.api.exceptions import (
    BaseAPIException,
    internal_server_error_handler,
    on_api_exception,
    validation_exception_handler,
)
from app.api.routes import api_router
from app.di.dependency_injector import Container
from app.infra.logging import configure_logging
from settings.config import AppSettings, load_app_settings


class Application:
    def __init__(self, container: Container):
        self.container = container
        self.app = FastAPI(
            version=container.config.VERSION(),
            title="TPC API",
            description="Python API for Telegram proxy checker",
            root_path=self.container.config.API_ROOT_PATH(),
            lifespan=self.lifespan,
            exception_handlers={
                RequestValidationError: validation_exception_handler,
                BaseAPIException: on_api_exception,
                Exception: internal_server_error_handler,
            },
        )
        self.app.include_router(api_router)
        self.app.state.config = container.config
        self.add_logging()
        self._configure_swagger_auth()

    def _configure_swagger_auth(self) -> None:
        def custom_openapi() -> dict[str, Any]:
            if self.app.openapi_schema:
                return self.app.openapi_schema
            openapi_schema = FastAPI.openapi(self.app)
            openapi_schema.setdefault("components", {}).setdefault("securitySchemes", {})
            openapi_schema["components"]["securitySchemes"]["BearerAuth"] = {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
            }
            openapi_schema["security"] = [{"BearerAuth": []}]
            self.app.openapi_schema = openapi_schema
            return openapi_schema

        self.app.openapi = custom_openapi  # type: ignore[method-assign]

    def add_logging(self) -> None:
        configure_logging(
            level=self.container.config.LOG_LEVEL(),
            enable_json_logs=self.container.config.is_json_logs_enabled(),
        )

    @property
    def fastapi_app(self) -> FastAPI:
        return self.app

    @staticmethod
    def _configure_orm_mappers() -> None:
        configure_mappers()

    @asynccontextmanager
    async def lifespan(self, _: FastAPI) -> AsyncGenerator[None]:
        init_resources = self.container.init_resources()
        if init_resources is not None:
            await init_resources

        self._configure_orm_mappers()
        await self.container.infra.database_engines().create_all_tables()

        broker = self.container.infra.taskiq_broker()
        if isinstance(broker, InMemoryBroker):
            broker.state.container = self.container
        await broker.startup()

        yield

        shutdown_resources = self.container.shutdown_resources()
        if shutdown_resources is not None:
            await shutdown_resources

        await broker.shutdown()
        await self.container.infra.database_engines().disconnect()


def create_app() -> FastAPI:
    container = Container()
    container.config.from_pydantic(AppSettings())
    return Application(container=container).app


if __name__ == "__main__":
    import uvicorn

    settings = load_app_settings()

    uvicorn.run(
        app="app.main:create_app",
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        workers=1,
        reload=True,
        factory=True,
    )
