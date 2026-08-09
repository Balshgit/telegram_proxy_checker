from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime
from typing import cast

from sqlalchemy import FunctionElement, func
from sqlalchemy.ext.compiler import compiles

from app.core.constants import MOSCOW_TZ
from app.di.dependency_injector import Container
from settings.config import AppTestSettings


class RaiseError(Exception):
    """Custom exception to raise from mocked (override) dependencies."""

    def __init__(self, message: str | None = None):
        self._message = message or "raise error"

    def __str__(self) -> str:
        return str(self._message)


def moscow_datetime_now_without_microsecond() -> datetime:
    return datetime.now(MOSCOW_TZ).replace(microsecond=0)


@contextmanager
def db_now_freeze(freeze_now: datetime | None = None) -> Generator[None]:
    """
    Context manager to freeze SQLAlchemy's NOW() and CURRENT_TIMESTAMP() functions
    to a fixed datetime value during test execution.

     Why this is tied to our test sessions:
    --------------------------------------
    - Our test setup uses transactional rollback sessions with nested savepoints,
      isolating tests and preventing side effects on the database.
    - Because of this layered session management, directly modifying the database server time or session
      parameters is complicated and error-prone.
    - Overriding SQLAlchemy's function compilation is a lightweight, reversible, and safe approach
      that fits cleanly into our fixture lifecycle.

    Note:
    -----
    - This patch affects only SQLAlchemy-generated calls to func.now() and func.current_timestamp().
    - Raw SQL queries using text('NOW()') or other direct calls to database functions are not intercepted
      by this context manager and will return the actual database server time.

    Example usage:
    --------------
    freeze_time = datetime(2025, 6, 16, 12, 0, 0)

    with mysql_now_freeze(freeze_time):
        response = await rest_client.post("/api/auth/sessions", json={"login": "Monty", "password": "secret"})
    """
    if freeze_now is None:
        freeze_now = moscow_datetime_now_without_microsecond()

    original_now = func.now
    original_current_timestamp = func.current_timestamp

    class FrozenNow(FunctionElement[None]):
        name = "now"
        inherit_cache = True

    @compiles(FrozenNow)
    def compile_frozen_now(element: FrozenNow, compiler, **kw) -> str:  # type: ignore[no-untyped-def]
        if element.name.lower() in ("now", "current_timestamp"):
            now_str = freeze_now.strftime("%Y-%m-%d %H:%M:%S")
            return f"TIMESTAMP('{now_str}')"
        return compiler.visit_function(element, **kw)

    func.now = cast(type(func.now), FrozenNow)  # type: ignore[misc]
    func.current_timestamp = cast(type(func.current_timestamp), FrozenNow)  # type: ignore[misc]

    try:
        yield
    finally:
        func.now = original_now  # type: ignore[misc]
        func.current_timestamp = original_current_timestamp  # type: ignore[misc]


@asynccontextmanager
async def override_settings(
    test_settings: AppTestSettings, new_settings: AppTestSettings, container: Container
) -> AsyncGenerator[None]:
    container.config.override(new_settings.model_dump())
    container.reset_singletons()
    yield
    container.config.override(test_settings.model_dump())
    container.reset_singletons()
