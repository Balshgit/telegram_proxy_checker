import contextlib
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)
from sqlalchemy.orm import DeclarativeMeta

from app.infra.sqlalchemy.engines import DatabaseEngines


class SessionBuilder:
    def __init__(self, engines: DatabaseEngines):
        self._binds: dict[type[DeclarativeMeta], AsyncEngine] = {}
        self._engines = engines
        self._session_factory = async_sessionmaker(
            autoflush=False,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    @contextlib.asynccontextmanager
    async def build_scoped(self) -> AsyncGenerator[AsyncSession]:
        new_session = self._build()
        try:
            yield new_session
        finally:
            await new_session.close()

    def build(self) -> AsyncSession:
        return self._build()

    def _build(self) -> AsyncSession:
        self._session_factory.configure(binds=self._binds)
        return self._session_factory()

    def __str__(self) -> str:
        return f"{self.__class__} binds: {self._binds}"
