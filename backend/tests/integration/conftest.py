import asyncio
import contextlib
import types
from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import Any, TypeVar
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from polyfactory.factories.sqlalchemy_factory import SQLAlchemyFactory
from sqlalchemy.ext.asyncio import AsyncSession

from app.di.dependency_injector import Container
from app.infra.adapters.database import Database
from settings.config import AppTestSettings
from tests.support.factories.setup.factory_setup import setup_factory

TFactory = TypeVar("TFactory", bound=SQLAlchemyFactory)


@pytest.fixture(scope="session", autouse=True)
async def _create_tables_from_metadata(db_connection: Database) -> None:
    await db_connection.create_postgres_tables()


@pytest.fixture(autouse=True)
async def _clear_tables_in_metadata(db_connection: Database, test_settings: AppTestSettings) -> None:
    if test_settings.DEBUG:
        metadata = db_connection._declarative_base.metadata
        tables = reversed(metadata.sorted_tables)
        async with db_connection._engine.begin() as connection:
            for table in tables:
                await connection.execute(table.delete())
            await connection.commit()


@pytest.fixture
async def rest_client(
    fastapi_app: FastAPI,
) -> AsyncGenerator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=fastapi_app),
        base_url="http://test",
        headers={
            "Content-Type": "application/json",
        },
    ) as client:
        yield client


@pytest.fixture(autouse=True)
async def override_db_sessions(container: Container, db_rollback_session: AsyncSession) -> AsyncGenerator[None]:
    """
    Automatically overrides database session methods in the DI container
    to use test rollback sessions during test execution.

    This fixture:
    - Replaces the `session()` method and `_async_session_factory` of selected databases
      (defined by `DatabaseEnum`) with custom implementations that return a pre-created
      rollback-enabled `AsyncSession`.
    - Prevents redundant transaction handling inside `session()` since the test session
      is already wrapped in an outer transaction with nested savepoints.
    - Restores the original session methods after each test to avoid side effects.

    Applied automatically to all tests via `autouse=True`.
    """

    db = container.infra.database_engines().db

    original_state = {
        "session": db.session,
        "_async_session_factory": db._async_session_factory,
    }

    @contextlib.asynccontextmanager
    async def patched_session(_: Any, session: AsyncSession = db_rollback_session) -> AsyncGenerator[AsyncSession]:
        try:
            yield session
        finally:
            session.expunge_all()

    db.session = types.MethodType(patched_session, db)
    db._async_session_factory = lambda s=db_rollback_session: s

    yield

    db = container.infra.database_engines().db
    db.session = original_state["session"]
    db._async_session_factory = original_state["_async_session_factory"]


@pytest.fixture(autouse=True)
def patch_asyncio_gather_wait_all(monkeypatch):
    """
    Test-only patches for asyncio.gather and asyncio.wait to avoid DB concurrency issues
    with shared sessions.

    In production, concurrent queries usually use different sessions/connections.
    In tests we reuse a single rollback-enabled AsyncSession, so:
    - asyncio.gather() may raise on the first exception while other awaitables keep running,
    - asyncio.wait(FIRST_EXCEPTION) may cancel pending tasks mid-DB-operation,
    both leaving DB I/O in-flight and breaking teardown (readexactly/PendingRollbackError).

    These patches make gather/wait wait for completion of all awaitables (no cancellation),
    then re-raise the first exception (unless return_exceptions=True).
    """
    real_gather = asyncio.gather

    def patched_gather(*aws, return_exceptions: bool = False):
        async def _runner():
            tasks = [asyncio.ensure_future(aw) for aw in aws]

            results = await real_gather(*tasks, return_exceptions=True)

            if return_exceptions:
                return results

            for r in results:
                if isinstance(r, BaseException):
                    raise r
            return results

        return asyncio.create_task(_runner())

    monkeypatch.setattr(asyncio, "gather", patched_gather)

    real_wait = asyncio.wait

    async def patched_wait(fs, *, timeout=None, return_when=asyncio.FIRST_EXCEPTION):
        # Always wait for all tasks to finish, preventing cancellation mid-DB-operation
        done, pending = await real_wait(fs, timeout=timeout, return_when=asyncio.ALL_COMPLETED)
        return done, pending

    monkeypatch.setattr(asyncio, "wait", patched_wait)


@pytest.fixture
async def override_taskiq_run(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.taskiq.executor.TaskiqTasksExecutor.run",
        AsyncMock(return_value=None),
        raising=True,
    )


@pytest.fixture
def sqlalchemy_model_factory_maker() -> Callable[[type[TFactory], AsyncSession], Awaitable[type[TFactory]]]:
    async def _factory(factory_cls: type[SQLAlchemyFactory], session: AsyncSession) -> type[SQLAlchemyFactory]:
        return setup_factory(factory_cls, session)

    return _factory
