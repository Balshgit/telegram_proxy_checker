import os
from collections.abc import AsyncGenerator, Generator
from typing import Any

import pytest
from fastapi import FastAPI
from loguru import logger
from polyfactory.factories.base import BaseFactory
from sqlalchemy import event
from sqlalchemy.ext.asyncio.session import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Session, SessionTransaction
from testcontainers.postgres import PostgresContainer

from app.di.dependency_injector import Container
from app.infra.sqlalchemy.typing import DatabaseDB
from settings.config import AppTestSettings, StageEnum
from tests.application import ApplicationForTests


@pytest.fixture(scope="session")
def test_settings() -> AppTestSettings:
    stage_env = os.environ.get("STAGE", StageEnum.local_runtests)
    if stage_env not in {StageEnum.local_runtests, StageEnum.ci_runtests}:
        logger.warning("stage environment during pytest run set to %s", stage_env)
        message = "test probably starts on prod environment. Current STAGE env is {stage}".format(  # noqa: UP032
            stage=stage_env,
        )
        pytest.exit(message)
    return AppTestSettings()


@pytest.fixture(scope="session")
def postgres_container(test_settings: AppTestSettings) -> Generator[PostgresContainer | None, Any]:
    database = test_settings.POSTGRES_DB
    db_host = test_settings.DB_HOST
    if not database.endswith("test"):
        message = "dsn for database `{db}` not ending on test. probably real db on host {host}".format(  # noqa: UP032
            db=database,
            host=db_host,
        )
        pytest.exit(message)

    if StageEnum.local_runtests == test_settings.STAGE:
        with PostgresContainer(
            image=test_settings.DB_POSTGRES_IMAGE,
            username=test_settings.POSTGRES_USER,
            password=test_settings.POSTGRES_PASSWORD,
            dbname=test_settings.POSTGRES_DB,
            port=5432,
        ) as postgresql:
            postgres = postgresql.with_bind_ports("5432/tcp", f"{test_settings.POSTGRES_DB_PORT}/tcp")
            postgres.start()
            yield postgres
    else:
        yield None


@pytest.fixture(scope="session")
def container(
    test_settings: AppTestSettings,
    postgres_container: PostgresContainer | None,
) -> Generator[Container]:
    overrides: dict[str, Any] = {}

    if postgres_container is not None:
        overrides.update(
            {
                "DB_HOST": postgres_container.get_container_host_ip(),
                "POSTGRES_DB_PORT": int(postgres_container.get_exposed_port(5432)),
                "POSTGRES_USER": postgres_container.username,
                "POSTGRES_PASSWORD": postgres_container.password,
                "POSTGRES_DB": postgres_container.dbname,
            }
        )
        logger.info(f"Container database: jdbc:postgresql://localhost:{postgres_container.get_exposed_port(5432)}")
        print("\n", f"Container port: {int(postgres_container.get_exposed_port(5432))}".center(50, "*"))  # noqa: T201

    if overrides:
        test_settings = test_settings.model_copy(update=overrides)

    container = Container()
    container.config.from_pydantic(test_settings)

    return container


@pytest.fixture(scope="session")
async def app(container: Container) -> ApplicationForTests:
    return ApplicationForTests(container=container)


@pytest.fixture(scope="session")
async def fastapi_app(app: ApplicationForTests) -> FastAPI:
    return app.fastapi_app


@pytest.fixture(scope="session")
def db_connection(container: Container) -> DatabaseDB:
    return container.infra.database_engines().db


@pytest.fixture
async def db_session(
    db_connection: DatabaseDB,
) -> AsyncGenerator[AsyncSession]:
    """Yields a db session without committing or rolling back (for read operations)."""
    async with db_connection.session() as session:
        yield session


@pytest.fixture
async def db_rollback_session(
    db_connection: DatabaseDB,
    db_session: AsyncSession,
    test_settings: AppTestSettings,
) -> AsyncGenerator[AsyncSession]:
    """
    Yields an AsyncSession with transactional behavior tailored for testing.

    - In normal mode (DEBUG=False):
        * A SAVEPOINT is started within a transaction.
        * All changes are rolled back after the test.
        * Each commit restarts the savepoint automatically.

    - In debug mode (DEBUG=True):
        * A persistent AsyncSession is used across the test.
        * Each commit is real (not rolled back).
        * A new transaction is auto-started after each commit.
        * The outer transaction is committed at the end to keep changes for debugging.

    This fixture ensures either full test isolation or debug convenience depending on config.

    """
    async with db_connection.engine.connect() as conn, conn.begin() as outer_tx:
        if test_settings.DEBUG:
            await db_session.begin()

            @event.listens_for(db_session.sync_session, "after_transaction_end")
            def _restart_transaction(sess: Session, _: SessionTransaction) -> None:
                if not sess.in_transaction() and sess.is_active:
                    sess.begin()

            try:
                yield db_session
            finally:
                if db_session.in_transaction():
                    await db_session.commit()
                if outer_tx.is_active:
                    await outer_tx.commit()
        else:
            session_factory = async_sessionmaker(
                bind=conn,
                expire_on_commit=False,
                class_=AsyncSession,
                autoflush=False,
            )

            async with session_factory() as session:
                await session.begin_nested()

                @event.listens_for(session.sync_session, "after_transaction_end")
                def _restart_savepoint(sess: Session, trans: SessionTransaction) -> None:
                    if trans.nested and trans._parent is not None and not trans._parent.nested and sess.is_active:
                        sess.begin_nested()

                try:
                    yield session
                finally:
                    if session.in_transaction():
                        await session.rollback()
                    if outer_tx.is_active:
                        await outer_tx.rollback()


@pytest.fixture(autouse=True)
def _reset_faker_unique(test_settings: AppTestSettings) -> Generator[None]:
    """Drop polyfactory's faker unique cache in order to avoid faker.exceptions.UniquenessException."""
    test_settings.TESTS_CALL_COUNT += 1
    yield
    if not test_settings.TESTS_CALL_COUNT % 500:
        for factory in BaseFactory.__subclasses__():
            factory.__faker__.unique.clear()
