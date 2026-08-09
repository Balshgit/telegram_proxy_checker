import contextlib
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Select
from sqlalchemy.exc import NoResultFound
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import TPCCoreException
from app.infra.sqlalchemy.typing import DatabasePostgresDB


@dataclass
class BaseDBRepository:
    db: DatabasePostgresDB

    async def get_multiple_results(
        self, query: Select[Any], as_scalars: bool = False, session: AsyncSession | None = None
    ) -> list[Any]:

        async with self.session_wrap(session) as wrapped_session:
            result = await wrapped_session.execute(query)
            rows = result.scalars().all() if as_scalars else result.all()
        return list(rows)

    async def get_single_result(
        self, query: Select[Any], as_scalar: bool = False, session: AsyncSession | None = None
    ) -> Any:

        async with self.session_wrap(session) as wrapped_session:
            result = await wrapped_session.execute(query)

            row = result.scalars().first() if as_scalar else result.first()
            if row:
                return row

        raise NoResultFound()

    @contextlib.asynccontextmanager
    async def _yield_session_within_existing_transaction(
        self,
        existing_session: AsyncSession,
    ) -> AsyncGenerator[AsyncSession]:
        # If the session is already inside a transactional session, we don't wanna commit in a nested one,
        # since it will be done by the outer (transactional) session. This is necessary for tests inside a transaction.
        # We always attempt to flush() on exit to push pending ORM changes to the UoW,
        # so subsequent reads within the same session/transaction can observe them.
        try:
            yield existing_session
        finally:
            await existing_session.flush()

    @contextlib.asynccontextmanager
    async def get_transactional_session(
        self,
        no_rollback_exceptions: tuple[type[TPCCoreException], ...] = (),
    ) -> AsyncGenerator[AsyncSession]:

        async with self.db.session() as session:
            if session.in_transaction():
                async with self._yield_session_within_existing_transaction(session) as yielded_session:
                    yield yielded_session
                return

            tx = await session.begin()
            try:
                yield session
            except no_rollback_exceptions:
                await tx.commit()
                raise
            except Exception:
                await tx.rollback()
                raise
            else:
                await tx.commit()

    @contextlib.asynccontextmanager
    async def transactional_session_wrap(self, session: AsyncSession | None) -> AsyncGenerator[AsyncSession]:
        if session is not None:
            yield session
        else:
            async with self.get_transactional_session() as transactional_session:
                yield transactional_session

    @contextlib.asynccontextmanager
    async def session_wrap(self, session: AsyncSession | None) -> AsyncGenerator[AsyncSession]:
        if session is not None:
            yield session
        else:
            async with self.db.session() as session_wrapped:
                if session_wrapped.in_transaction():
                    async with self._yield_session_within_existing_transaction(session_wrapped) as yielded_session:
                        yield yielded_session
                    return

                yield session_wrapped
                await session_wrapped.commit()
