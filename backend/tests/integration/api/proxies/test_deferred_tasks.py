from collections.abc import Awaitable, Callable

from polyfactory.factories.sqlalchemy_factory import SQLAlchemyFactory
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.proxies.constants import ProxySourceStatusEnum, ProxyStatusEnum
from app.core.proxies.tasks import save_proxies_to_database_task, update_proxies_in_database_task
from app.di.dependency_injector import Container
from tests.integration.api.proxies.helpers import (
    build_proxy_url,
    get_proxies_by_name,
    mocked_get_host_latency_by_server,
    pinged_source_id_by_server,
)
from tests.integration.context import DummyContext
from tests.support.factories.proxies import TelegramProxiesSourceFactory, TelegramProxyFactory

FIRST_PROXY_SERVER = "1.2.3.4"
SECOND_PROXY_SERVER = "5.6.7.8"


async def test_deferred_save_task_saves_source_id(
    container: Container,
    db_rollback_session: AsyncSession,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    """
    Отложенное сохранение "хвоста" тоже проставляет источник.

    Сервис кладёт в параметры таски словари `{"source_id": ..., "url": ...}`, таска собирает
    из них `ProxySourceToPingDTO` — источник обязан доехать до `TelegramProxy.source_id`.
    """
    proxies_source_factory = await sqlalchemy_model_factory_maker(
        factory_cls=TelegramProxiesSourceFactory, session=db_rollback_session
    )

    first_source = await proxies_source_factory.create_async(status=ProxySourceStatusEnum.enabled)
    second_source = await proxies_source_factory.create_async(status=ProxySourceStatusEnum.enabled)
    first_source_id, second_source_id = first_source.id, second_source.id

    source_urls = [
        {"source_id": first_source_id, "url": build_proxy_url(server=FIRST_PROXY_SERVER)},
        {"source_id": second_source_id, "url": build_proxy_url(server=SECOND_PROXY_SERVER)},
    ]

    async with mocked_get_host_latency_by_server(default_latency=42) as mocked_latency:
        await save_proxies_to_database_task(context=DummyContext(container=container), source_urls=source_urls)

    mocked_latency.assert_awaited_once()
    assert pinged_source_id_by_server(mocked_latency) == {
        FIRST_PROXY_SERVER: first_source_id,
        SECOND_PROXY_SERVER: second_source_id,
    }

    proxies_in_db = await get_proxies_by_name(db_rollback_session)

    assert sorted(proxies_in_db) == sorted([FIRST_PROXY_SERVER, SECOND_PROXY_SERVER])

    assert proxies_in_db[FIRST_PROXY_SERVER].source_id == first_source_id
    assert proxies_in_db[SECOND_PROXY_SERVER].source_id == second_source_id

    for proxy in proxies_in_db.values():
        assert proxy.latency == 42
        assert proxy.status == ProxyStatusEnum.enabled


async def test_deferred_save_task_saves_proxy_without_source(
    container: Container,
    db_rollback_session: AsyncSession,
) -> None:
    """`source_id=None` в параметрах таски — валидный случай: прокси сохраняется без источника."""
    source_urls = [{"source_id": None, "url": build_proxy_url(server=FIRST_PROXY_SERVER)}]

    async with mocked_get_host_latency_by_server(default_latency=7) as mocked_latency:
        await save_proxies_to_database_task(context=DummyContext(container=container), source_urls=source_urls)

    mocked_latency.assert_awaited_once()
    assert pinged_source_id_by_server(mocked_latency) == {FIRST_PROXY_SERVER: None}

    proxies_in_db = await get_proxies_by_name(db_rollback_session)

    assert list(proxies_in_db) == [FIRST_PROXY_SERVER]
    assert proxies_in_db[FIRST_PROXY_SERVER].source_id is None
    assert proxies_in_db[FIRST_PROXY_SERVER].latency == 7


async def test_deferred_update_task_keeps_source_id(
    container: Container,
    db_rollback_session: AsyncSession,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    """Отложенное обновление "хвоста" не сбрасывает источник у уже сохранённых проксей."""
    proxy_factory = await sqlalchemy_model_factory_maker(factory_cls=TelegramProxyFactory, session=db_rollback_session)
    proxies_source_factory = await sqlalchemy_model_factory_maker(
        factory_cls=TelegramProxiesSourceFactory, session=db_rollback_session
    )

    source = await proxies_source_factory.create_async(status=ProxySourceStatusEnum.enabled)
    source_id = source.id

    first_url = build_proxy_url(server=FIRST_PROXY_SERVER)
    second_url = build_proxy_url(server=SECOND_PROXY_SERVER)

    await proxy_factory.create_async(
        name=FIRST_PROXY_SERVER,
        url=first_url,
        source_id=source_id,
        status=ProxyStatusEnum.disabled,
        latency=None,
        updated_at=None,
    )
    await proxy_factory.create_async(
        name=SECOND_PROXY_SERVER,
        url=second_url,
        source_id=None,
        status=ProxyStatusEnum.disabled,
        latency=None,
        updated_at=None,
    )

    source_urls = [
        {"source_id": source_id, "url": first_url},
        {"source_id": None, "url": second_url},
    ]

    async with mocked_get_host_latency_by_server(default_latency=64) as mocked_latency:
        await update_proxies_in_database_task(context=DummyContext(container=container), source_urls=source_urls)

    mocked_latency.assert_awaited_once()
    assert pinged_source_id_by_server(mocked_latency) == {
        FIRST_PROXY_SERVER: source_id,
        SECOND_PROXY_SERVER: None,
    }

    proxies_in_db = await get_proxies_by_name(db_rollback_session)

    assert len(proxies_in_db) == 2

    assert proxies_in_db[FIRST_PROXY_SERVER].source_id == source_id
    assert proxies_in_db[SECOND_PROXY_SERVER].source_id is None

    for proxy in proxies_in_db.values():
        assert proxy.latency == 64
        assert proxy.status == ProxyStatusEnum.enabled
        assert proxy.updated_at is not None
