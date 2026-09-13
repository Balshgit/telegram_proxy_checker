from collections.abc import Awaitable, Callable

from polyfactory.factories.sqlalchemy_factory import SQLAlchemyFactory
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.proxies.constants import ProxyStatusEnum
from app.core.proxies.models import TelegramProxy
from app.core.proxies.tasks import (
    cron_add_proxies_to_database_task,
    cron_delete_stale_proxies_task,
    cron_update_proxies_in_database_task,
    save_proxies_to_database_task,
)
from app.core.proxies_sources.constants import ProxySourceStatusEnum
from app.di.dependency_injector import Container
from settings.config import AppTestSettings
from tests.integration.api.proxies.helpers import (
    CHUNK_SIZE_FOR_TESTS,
    GITHUB_PROXIES_ROUTE_NAME,
    build_proxy_url,
    deferred_source_urls,
    fresh_moment,
    get_database_now,
    get_proxies_by_name,
    get_proxies_by_url,
    get_proxies_ids,
    get_source_by_id,
    mocked_get_host_latency_by_server,
    mocked_get_host_latency_for_urls,
    mocked_github_get_proxies,
    mocked_github_get_proxies_by_source,
    mocked_save_postgres_chunk_size,
    mocked_taskiq_run,
    pinged_proxies,
    pinged_source_id_by_server,
    source_route_name,
    stale_moment,
)
from tests.integration.context import DummyContext
from tests.support.factories.proxies import TelegramProxyFactory
from tests.support.factories.proxies_sources import TelegramProxiesSourceFactory

FIRST_PROXY_SERVER = "1.2.3.4"
SECOND_PROXY_SERVER = "5.6.7.8"

#: Сколько урлов в тесте на чанк уезжает в отложенную таску сверх размера чанка.
PROXIES_OVER_CHUNK_SIZE = 2


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


async def test_cron_add_proxies_task_saves_new_proxies(
    container: Container,
    db_rollback_session: AsyncSession,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    """Кроновый добор складывает в базу ровно то же, что и ручной `POST /api/proxies`."""
    proxies_source_factory = await sqlalchemy_model_factory_maker(
        factory_cls=TelegramProxiesSourceFactory, session=db_rollback_session
    )

    source = await proxies_source_factory.create_async(status=ProxySourceStatusEnum.enabled)
    source_id = source.id

    first_url = build_proxy_url(server=FIRST_PROXY_SERVER)
    second_url = build_proxy_url(server=SECOND_PROXY_SERVER)
    latency_by_url: dict[str, int | None] = {first_url: 11, second_url: None}

    async with (
        mocked_github_get_proxies(f"{first_url}\n{second_url}") as mocked_github,
        mocked_get_host_latency_for_urls(latency_by_url) as mocked_latency,
    ):
        await cron_add_proxies_to_database_task(context=DummyContext(container=container))

        assert mocked_github.routes[GITHUB_PROXIES_ROUTE_NAME].call_count == 1

    mocked_latency.assert_awaited_once()
    assert sorted(str(proxy_to_ping.url) for proxy_to_ping in pinged_proxies(mocked_latency)) == sorted(latency_by_url)

    proxies_in_db = await get_proxies_by_url(db_rollback_session)

    assert sorted(proxies_in_db) == sorted(latency_by_url)

    assert proxies_in_db[first_url].name == FIRST_PROXY_SERVER
    assert proxies_in_db[first_url].latency == 11
    assert proxies_in_db[first_url].status == ProxyStatusEnum.enabled
    assert proxies_in_db[first_url].source_id == source_id
    # Живая прокси сразу получает отметку активности, иначе ночная чистка снесёт её как протухшую.
    assert proxies_in_db[first_url].last_active_at is not None

    assert proxies_in_db[second_url].name == SECOND_PROXY_SERVER
    assert proxies_in_db[second_url].latency is None
    assert proxies_in_db[second_url].status == ProxyStatusEnum.disabled
    assert proxies_in_db[second_url].source_id == source_id
    assert proxies_in_db[second_url].last_active_at is None


async def test_cron_add_proxies_task_pings_proxies_with_their_source(
    container: Container,
    db_rollback_session: AsyncSession,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    """Источников может быть несколько: каждая новая прокси должна запомнить именно свой."""
    proxies_source_factory = await sqlalchemy_model_factory_maker(
        factory_cls=TelegramProxiesSourceFactory, session=db_rollback_session
    )

    first_source = await proxies_source_factory.create_async(status=ProxySourceStatusEnum.enabled)
    second_source = await proxies_source_factory.create_async(status=ProxySourceStatusEnum.enabled)
    first_source_id, second_source_id = first_source.id, second_source.id

    first_url = build_proxy_url(server=FIRST_PROXY_SERVER)
    second_url = build_proxy_url(server=SECOND_PROXY_SERVER)

    raw_proxies_by_source = {first_source.url: first_url, second_source.url: second_url}

    async with (
        mocked_github_get_proxies_by_source(raw_proxies_by_source) as mocked_github,
        mocked_get_host_latency_for_urls(default_latency=42) as mocked_latency,
    ):
        await cron_add_proxies_to_database_task(context=DummyContext(container=container))

        assert mocked_github.calls.call_count == len(raw_proxies_by_source)
        for source_url in raw_proxies_by_source:
            assert mocked_github.routes[source_route_name(source_url)].call_count == 1

    # Пинг идёт одним пакетом на все источники сразу.
    mocked_latency.assert_awaited_once()
    assert pinged_source_id_by_server(mocked_latency) == {
        FIRST_PROXY_SERVER: first_source_id,
        SECOND_PROXY_SERVER: second_source_id,
    }

    proxies_in_db = await get_proxies_by_url(db_rollback_session)

    assert sorted(proxies_in_db) == sorted([first_url, second_url])
    assert proxies_in_db[first_url].source_id == first_source_id
    assert proxies_in_db[second_url].source_id == second_source_id


async def test_cron_add_proxies_task_ignores_disabled_source(
    container: Container,
    db_rollback_session: AsyncSession,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    """
    Выключенный источник кроном не опрашивается.

    Его урл специально не замокан: с `assert_all_mocked=True` любой поход за ним уронит тест
    на respx, а не молча добавит прокси в базу.
    """
    proxies_source_factory = await sqlalchemy_model_factory_maker(
        factory_cls=TelegramProxiesSourceFactory, session=db_rollback_session
    )

    enabled_source = await proxies_source_factory.create_async(status=ProxySourceStatusEnum.enabled)
    await proxies_source_factory.create_async(status=ProxySourceStatusEnum.disabled)
    enabled_source_id = enabled_source.id

    enabled_source_url = build_proxy_url(server=FIRST_PROXY_SERVER)

    async with (
        mocked_github_get_proxies_by_source({enabled_source.url: enabled_source_url}) as mocked_github,
        mocked_get_host_latency_for_urls(default_latency=42) as mocked_latency,
    ):
        await cron_add_proxies_to_database_task(context=DummyContext(container=container))

        assert mocked_github.calls.call_count == 1
        assert mocked_github.routes[source_route_name(enabled_source.url)].call_count == 1

    mocked_latency.assert_awaited_once()

    proxies_in_db = await get_proxies_by_url(db_rollback_session)

    assert list(proxies_in_db) == [enabled_source_url]
    assert proxies_in_db[enabled_source_url].source_id == enabled_source_id


async def test_cron_add_proxies_task_skips_already_saved_proxies(
    container: Container,
    db_rollback_session: AsyncSession,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    """Крон ходит по тем же источникам каждые 6 часов, поэтому уже сохранённые урлы он должен пропускать."""
    proxy_factory = await sqlalchemy_model_factory_maker(factory_cls=TelegramProxyFactory, session=db_rollback_session)
    proxies_source_factory = await sqlalchemy_model_factory_maker(
        factory_cls=TelegramProxiesSourceFactory, session=db_rollback_session
    )

    source = await proxies_source_factory.create_async(status=ProxySourceStatusEnum.enabled)
    source_id = source.id

    existing_url = build_proxy_url(server=FIRST_PROXY_SERVER)
    new_url = build_proxy_url(server=SECOND_PROXY_SERVER)

    # Источник задаём явно: иначе фабрика заведёт ещё один включённый источник,
    # и крон сходит в github дважды.
    existing_proxy = await proxy_factory.create_async(
        name=FIRST_PROXY_SERVER,
        url=existing_url,
        source_id=source_id,
        status=ProxyStatusEnum.enabled,
        latency=10,
    )
    existing_proxy_id = existing_proxy.id

    async with (
        mocked_github_get_proxies(f"{existing_url}\n{new_url}") as mocked_github,
        mocked_get_host_latency_for_urls(default_latency=77) as mocked_latency,
    ):
        await cron_add_proxies_to_database_task(context=DummyContext(container=container))

        assert mocked_github.routes[GITHUB_PROXIES_ROUTE_NAME].call_count == 1

    # Пингуется только новый урл: старый не перепроверяется, этим занимается кроновое обновление.
    mocked_latency.assert_awaited_once()
    assert [str(proxy_to_ping.url) for proxy_to_ping in pinged_proxies(mocked_latency)] == [new_url]

    proxies_in_db = await get_proxies_by_url(db_rollback_session)

    assert sorted(proxies_in_db) == sorted([existing_url, new_url])

    # Существующая запись осталась той же самой и не потеряла latency.
    assert proxies_in_db[existing_url].id == existing_proxy_id
    assert proxies_in_db[existing_url].latency == 10

    assert proxies_in_db[new_url].latency == 77
    assert proxies_in_db[new_url].status == ProxyStatusEnum.enabled
    assert proxies_in_db[new_url].source_id == source_id


async def test_cron_add_proxies_task_recalculates_source_counters(
    container: Container,
    db_rollback_session: AsyncSession,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    """Счётчики источника пересчитываются в той же транзакции, в которой прокси попали в базу."""
    proxies_source_factory = await sqlalchemy_model_factory_maker(
        factory_cls=TelegramProxiesSourceFactory, session=db_rollback_session
    )

    source = await proxies_source_factory.create_async(
        status=ProxySourceStatusEnum.enabled, proxies_count=0, active_proxies_count=0
    )
    source_id = source.id

    first_url = build_proxy_url(server=FIRST_PROXY_SERVER)
    second_url = build_proxy_url(server=SECOND_PROXY_SERVER)
    latency_by_url: dict[str, int | None] = {first_url: 15, second_url: None}

    async with (
        mocked_github_get_proxies(f"{first_url}\n{second_url}") as mocked_github,
        mocked_get_host_latency_for_urls(latency_by_url),
    ):
        await cron_add_proxies_to_database_task(context=DummyContext(container=container))

        assert mocked_github.routes[GITHUB_PROXIES_ROUTE_NAME].call_count == 1

    source_after = await get_source_by_id(db_rollback_session, source_id)

    assert source_after.proxies_count == 2
    assert source_after.active_proxies_count == 1


async def test_cron_add_proxies_task_sends_urls_over_chunk_size_to_taskiq(
    container: Container,
    db_rollback_session: AsyncSession,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    """Крон сохраняет синхронно только первый чанк, остальное уезжает в отложенную таску вместе с источником."""
    proxies_source_factory = await sqlalchemy_model_factory_maker(
        factory_cls=TelegramProxiesSourceFactory, session=db_rollback_session
    )

    source = await proxies_source_factory.create_async(status=ProxySourceStatusEnum.enabled)
    source_id = source.id

    total_proxies = CHUNK_SIZE_FOR_TESTS + PROXIES_OVER_CHUNK_SIZE
    all_urls = [build_proxy_url(server=f"10.0.0.{number}") for number in range(total_proxies)]

    async with (
        mocked_save_postgres_chunk_size(),
        mocked_github_get_proxies("\n".join(all_urls)) as mocked_github,
        mocked_get_host_latency_for_urls(default_latency=55) as mocked_latency,
        mocked_taskiq_run() as mocked_taskiq,
    ):
        await cron_add_proxies_to_database_task(context=DummyContext(container=container))

        assert mocked_github.routes[GITHUB_PROXIES_ROUTE_NAME].call_count == 1

    mocked_latency.assert_awaited_once()
    assert len(pinged_proxies(mocked_latency)) == CHUNK_SIZE_FOR_TESTS

    mocked_taskiq.assert_awaited_once()
    assert mocked_taskiq.await_args.args[0] is save_proxies_to_database_task

    deferred = deferred_source_urls(mocked_taskiq)
    deferred_urls = [item["url"] for item in deferred]

    assert len(deferred) == PROXIES_OVER_CHUNK_SIZE
    assert {item["source_id"] for item in deferred} == {source_id}

    proxies_in_db = await get_proxies_by_url(db_rollback_session)

    assert len(proxies_in_db) == CHUNK_SIZE_FOR_TESTS

    saved_urls = set(proxies_in_db)

    assert saved_urls.isdisjoint(deferred_urls)
    assert saved_urls | set(deferred_urls) == set(all_urls)

    for proxy in proxies_in_db.values():
        assert proxy.latency == 55
        assert proxy.source_id == source_id
