from collections.abc import Awaitable, Callable

from polyfactory.factories.sqlalchemy_factory import SQLAlchemyFactory
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.proxies.constants import ProxyStatusEnum
from app.core.proxies.models import TelegramProxy
from app.core.proxies.tasks import cron_delete_stale_proxies_task, cron_update_proxies_in_database_task
from app.core.proxies_sources.constants import ProxySourceStatusEnum
from app.di.dependency_injector import Container
from settings.config import AppTestSettings
from tests.integration.api.proxies.helpers import (
    build_proxy_url,
    fresh_moment,
    get_database_now,
    get_proxies_by_name,
    get_proxies_ids,
    get_source_by_id,
    mocked_get_host_latency_by_server,
    pinged_proxies,
    pinged_source_id_by_server,
    stale_moment,
)
from tests.integration.context import DummyContext
from tests.support.factories.proxies import TelegramProxyFactory
from tests.support.factories.proxies_sources import TelegramProxiesSourceFactory

FIRST_PROXY_SERVER = "1.2.3.4"
SECOND_PROXY_SERVER = "5.6.7.8"


async def test_cron_task_updates_all_proxies(
    container: Container,
    db_rollback_session: AsyncSession,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    """Задача, которую дёргает планировщик по интервалу, обновляет прокси так же, как ручной эндпоинт."""
    proxy_factory = await sqlalchemy_model_factory_maker(factory_cls=TelegramProxyFactory, session=db_rollback_session)

    first_proxy = await proxy_factory.create_async(
        name=FIRST_PROXY_SERVER,
        url=build_proxy_url(server=FIRST_PROXY_SERVER),
        status=ProxyStatusEnum.disabled,
        latency=None,
        updated_at=None,
    )
    second_proxy = await proxy_factory.create_async(
        name=SECOND_PROXY_SERVER,
        url=build_proxy_url(server=SECOND_PROXY_SERVER),
        status=ProxyStatusEnum.enabled,
        latency=10,
        updated_at=None,
    )
    first_source_id, second_source_id = first_proxy.source_id, second_proxy.source_id

    latency_by_server: dict[str, int | None] = {FIRST_PROXY_SERVER: 55, SECOND_PROXY_SERVER: None}

    async with mocked_get_host_latency_by_server(latency_by_server) as mocked_latency:
        await cron_update_proxies_in_database_task(context=DummyContext(container=container))

    mocked_latency.assert_awaited_once()
    assert sorted(proxy_to_ping.url.params["server"] for proxy_to_ping in pinged_proxies(mocked_latency)) == sorted(
        latency_by_server
    )

    proxies_in_db = await get_proxies_by_name(db_rollback_session)

    assert proxies_in_db[FIRST_PROXY_SERVER].latency == 55
    assert proxies_in_db[FIRST_PROXY_SERVER].status == ProxyStatusEnum.enabled
    assert proxies_in_db[FIRST_PROXY_SERVER].updated_at is not None
    assert proxies_in_db[FIRST_PROXY_SERVER].source_id == first_source_id

    assert proxies_in_db[SECOND_PROXY_SERVER].latency is None
    assert proxies_in_db[SECOND_PROXY_SERVER].status == ProxyStatusEnum.disabled
    assert proxies_in_db[SECOND_PROXY_SERVER].updated_at is not None
    assert proxies_in_db[SECOND_PROXY_SERVER].source_id == second_source_id


async def test_cron_task_pings_proxies_with_their_source(
    container: Container,
    db_rollback_session: AsyncSession,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    """Кроновое обновление тоже носит источник с собой: гейтвей получает пары (source_id, url)."""
    proxy_factory = await sqlalchemy_model_factory_maker(factory_cls=TelegramProxyFactory, session=db_rollback_session)
    proxies_source_factory = await sqlalchemy_model_factory_maker(
        factory_cls=TelegramProxiesSourceFactory, session=db_rollback_session
    )

    source = await proxies_source_factory.create_async(status=ProxySourceStatusEnum.enabled)
    source_id = source.id

    await proxy_factory.create_async(
        name=FIRST_PROXY_SERVER,
        url=build_proxy_url(server=FIRST_PROXY_SERVER),
        source_id=source_id,
        status=ProxyStatusEnum.disabled,
        latency=None,
        updated_at=None,
    )
    await proxy_factory.create_async(
        name=SECOND_PROXY_SERVER,
        url=build_proxy_url(server=SECOND_PROXY_SERVER),
        source_id=None,
        status=ProxyStatusEnum.disabled,
        latency=None,
        updated_at=None,
    )

    async with mocked_get_host_latency_by_server(default_latency=99) as mocked_latency:
        await cron_update_proxies_in_database_task(context=DummyContext(container=container))

    mocked_latency.assert_awaited_once()
    assert pinged_source_id_by_server(mocked_latency) == {
        FIRST_PROXY_SERVER: source_id,
        SECOND_PROXY_SERVER: None,
    }

    proxies_in_db = await get_proxies_by_name(db_rollback_session)

    assert proxies_in_db[FIRST_PROXY_SERVER].source_id == source_id
    assert proxies_in_db[FIRST_PROXY_SERVER].latency == 99
    assert proxies_in_db[SECOND_PROXY_SERVER].source_id is None
    assert proxies_in_db[SECOND_PROXY_SERVER].latency == 99


async def test_cron_task_on_empty_database(
    container: Container,
    db_rollback_session: AsyncSession,
) -> None:
    async with mocked_get_host_latency_by_server() as mocked_latency:
        await cron_update_proxies_in_database_task(context=DummyContext(container=container))

    mocked_latency.assert_awaited_once_with(urls_with_source=[])

    assert (await db_rollback_session.execute(select(TelegramProxy))).scalars().all() == []


async def test_cron_cleanup_task_deletes_stale_proxies(
    container: Container,
    db_rollback_session: AsyncSession,
    test_settings: AppTestSettings,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    """Ночная задача чистит базу так же, как ручной эндпоинт, и пересчитывает счётчики источника."""
    proxy_factory = await sqlalchemy_model_factory_maker(factory_cls=TelegramProxyFactory, session=db_rollback_session)
    proxies_source_factory = await sqlalchemy_model_factory_maker(
        factory_cls=TelegramProxiesSourceFactory, session=db_rollback_session
    )

    database_now = await get_database_now(db_rollback_session)
    stale_period = test_settings.PROXY_STALE_PERIOD

    source = await proxies_source_factory.create_async(
        status=ProxySourceStatusEnum.enabled, proxies_count=2, active_proxies_count=2
    )
    source_id = source.id

    await proxy_factory.create_async(
        source_id=source_id,
        status=ProxyStatusEnum.enabled,
        created_at=stale_moment(database_now, stale_period),
        last_active_at=stale_moment(database_now, stale_period),
    )
    await proxy_factory.create_async(
        source_id=source_id,
        status=ProxyStatusEnum.disabled,
        created_at=stale_moment(database_now, stale_period),
        last_active_at=None,
    )
    survivor = await proxy_factory.create_async(
        source_id=source_id,
        status=ProxyStatusEnum.enabled,
        created_at=stale_moment(database_now, stale_period),
        last_active_at=fresh_moment(database_now, stale_period),
    )
    survivor_id = survivor.id

    await cron_delete_stale_proxies_task(context=DummyContext(container=container))

    assert await get_proxies_ids(db_rollback_session) == {survivor_id}

    source_after = await get_source_by_id(db_rollback_session, source_id)

    assert source_after.proxies_count == 1
    assert source_after.active_proxies_count == 1


async def test_cron_cleanup_task_on_empty_database(
    container: Container,
    db_rollback_session: AsyncSession,
) -> None:
    await cron_delete_stale_proxies_task(context=DummyContext(container=container))

    assert (await db_rollback_session.execute(select(TelegramProxy))).scalars().all() == []
