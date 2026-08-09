import contextlib
from collections.abc import AsyncGenerator
from typing import Any

from loguru import logger
from sqlalchemy import Select, text
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import merge_frozen_result

from app.core.concurrency import run_async
from app.infra.sqlalchemy.base import DBBase


class Database:
    def __init__(
        self,
        db_connect_url: str,
        echo_logs: bool = False,
    ) -> None:
        self._declarative_base = DBBase
        self._engine: AsyncEngine = create_async_engine(
            url=db_connect_url,
            pool_pre_ping=False,
            pool_recycle=3600,
            echo=echo_logs,
            echo_pool=echo_logs,
            logging_name="postgres",
            pool_logging_name="postgres",
        )

        self._async_session_factory = async_sessionmaker(
            bind=self._engine,
            autoflush=False,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    @property
    def engine(self) -> AsyncEngine:
        return self._engine

    @classmethod
    def build(cls, *, dsn: str, debug: bool) -> Database:
        return cls(db_connect_url=dsn, echo_logs=debug)

    async def create_postgres_tables(self) -> Exception | None:
        try:
            async with self._engine.begin() as conn:
                await self._create_postgres_shema(connection=conn, schema_name="public")
                await conn.run_sync(self._declarative_base.metadata.create_all, checkfirst=True)
        except Exception as error:  # noqa: BLE001
            return error

        return None

    async def _create_postgres_shema(self, connection: AsyncConnection, schema_name: str) -> None:
        result = await connection.execute(
            text(
                f"SELECT schema_name FROM information_schema.schemata WHERE schema_name = '{schema_name}'"  # noqa: S608
            )
        )
        schema_exists = result.first() is not None

        if not schema_exists:
            await connection.execute(text(f"CREATE SCHEMA {schema_name}"))

    async def disconnect(self) -> None:
        try:
            # to gracefully stop all hanging connections
            # https://docs.sqlalchemy.org/en/20/core/pooling.html#sqlalchemy.pool.Pool.dispose
            # https://docs.sqlalchemy.org/en/20/core/connections.html#engine-disposal
            while not self.engine.pool._pool.empty():  # type: ignore[attr-defined]
                conn = self.engine.pool._pool.get_nowait()  # type: ignore[attr-defined]
                await conn.driver_connection.close()
            await self._engine.dispose()
        except Exception as error:  # noqa: BLE001
            logger.warning("failed to close database connections", erorr=error)
        else:
            logger.info("database connections closed")

    @contextlib.asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession]:
        session: AsyncSession = self._async_session_factory()
        async with session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    async def execute_async(self, *queries: Select[Any], root_session: AsyncSession) -> list[Any]:
        """
        Run alchemy queries in async mode in different sessions.
        Cant be used for transaction only for read operations!!!

        how to use:

        >>> query_1 = select(Art).where(Art.id == 42)
        >>> query_2 = select(ArtEdition).where(ArtEdition.id == 42)
        >>>
        >>> async with self.session_wrap(session) as wrapped_session:
        >>>     result1, result2 = await self.db_ll.execute_async(query_1, query_2, root_session=wrapped_session)
        """
        coros = []
        for statement in queries:
            coro = self._run_in_new_session(root_session=root_session, statement=statement)
            coros.append(coro)
        frozen_results = await run_async(*coros)
        return [
            (
                await root_session.run_sync(
                    merge_frozen_result,
                    statement,
                    result,
                    load=False,
                )
            )()
            for statement, result in zip(queries, frozen_results, strict=True)
        ]

    async def _run_in_new_session(
        self, root_session: AsyncSession, statement: Select[Any], merge_results: bool = True
    ) -> Any | None:
        # can't run execute session though gather in one session (same connect).
        # That's why we run each query in separate session (different connects).
        # official doc: https://docs.sqlalchemy.org/en/20/_modules/examples/asyncio/gather_orm_statements.html
        async with self.session() as oob_session:
            # use AUTOCOMMIT for each connection to reduce transaction
            # overhead / contention
            await oob_session.connection(execution_options={"isolation_level": "AUTOCOMMIT"})

            result = await oob_session.execute(statement)
        if merge_results:
            return result.freeze()
        return None
