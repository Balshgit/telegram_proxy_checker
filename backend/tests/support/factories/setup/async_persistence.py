import asyncio
from typing import TypeVar

from polyfactory import AsyncPersistenceProtocol
from sqlalchemy.ext.asyncio.session import AsyncSession

T = TypeVar("T")


class FlushOnlyAsyncPersistence(AsyncPersistenceProtocol[T]):
    """Overrides default persistence class for FlushOnly instead of committing."""

    def __init__(self, session: AsyncSession, debug: bool) -> None:
        self.session = session
        self.debug = debug
        self._lock = asyncio.Lock()

    async def save(self, data: T) -> T:
        async with self._lock:
            self.session.add(data)
            if self.debug:
                await self.session.commit()
            else:
                await self.session.flush()
        return data

    async def save_many(self, data: list[T]) -> list[T]:
        async with self._lock:
            self.session.add_all(data)
            if self.debug:
                await self.session.commit()
            else:
                await self.session.flush()
        return data
