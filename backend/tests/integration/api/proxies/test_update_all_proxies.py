from collections.abc import Awaitable, Callable

from httpx import URL, AsyncClient
from polyfactory.factories.sqlalchemy_factory import SQLAlchemyFactory
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.proxies.constants import ProxyStatusEnum
from app.core.proxies.models import TelegramProxy
from app.core.proxies.tasks import update_proxies_in_database_task
from app.core.proxies_sources.constants import ProxySourceStatusEnum
from tests.integration.api.proxies.helpers import (
    CHUNK_SIZE_FOR_TESTS,
    build_proxy_url,
    deferred_source_urls,
    get_proxies_by_id,
    get_proxies_by_name,
    mocked_get_host_latency_by_server,
    mocked_save_postgres_chunk_size,
    mocked_taskiq_run,
    pinged_proxies,
    pinged_source_id_by_server,
)
from tests.integration.api.proxies_sources.helpers import get_proxies_sources_by_id
from tests.support.factories.proxies import TelegramProxyFactory
from tests.support.factories.proxies_sources import TelegramProxiesSourceFactory

FIRST_PROXY_SERVER = "1.2.3.4"
SECOND_PROXY_SERVER = "5.6.7.8"

PROXIES_OVER_CHUNK_SIZE = 2


async def test_update_all_proxies(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
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
    source_id_by_server = {FIRST_PROXY_SERVER: first_proxy.source_id, SECOND_PROXY_SERVER: second_proxy.source_id}

    latency_by_server: dict[str, int | None] = {FIRST_PROXY_SERVER: 55, SECOND_PROXY_SERVER: 606}

    async with mocked_get_host_latency_by_server(latency_by_server) as mocked_latency:
        response = await rest_client.post("/api/proxies/status")

    assert response.status_code == status.HTTP_200_OK, response.text
    assert response.content == b"null"

    mocked_latency.assert_awaited_once()
    assert sorted(proxy_to_ping.url.params["server"] for proxy_to_ping in pinged_proxies(mocked_latency)) == sorted(
        latency_by_server
    )

    proxies_in_db = await get_proxies_by_name(db_rollback_session)

    assert len(proxies_in_db) == 2

    for server, expected_latency in latency_by_server.items():
        assert proxies_in_db[server].latency == expected_latency
        assert proxies_in_db[server].status == ProxyStatusEnum.enabled
        assert proxies_in_db[server].updated_at is not None
        assert proxies_in_db[server].source_id == source_id_by_server[server]


async def test_update_all_proxies_sends_source_id_to_gateway(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    """
    На пинг сервис отдаёт не голые урлы, а пары (source_id, url).

    Источник берётся из существующей записи, поэтому по всей цепочке
    сервис -> гейтвей -> репозиторий прокси остаётся привязанной к своему источнику.
    """
    proxy_factory = await sqlalchemy_model_factory_maker(factory_cls=TelegramProxyFactory, session=db_rollback_session)
    proxies_source_factory = await sqlalchemy_model_factory_maker(
        factory_cls=TelegramProxiesSourceFactory, session=db_rollback_session
    )

    first_source = await proxies_source_factory.create_async(status=ProxySourceStatusEnum.enabled)
    second_source = await proxies_source_factory.create_async(status=ProxySourceStatusEnum.enabled)
    first_source_id, second_source_id = first_source.id, second_source.id

    await proxy_factory.create_async(
        name=FIRST_PROXY_SERVER,
        url=build_proxy_url(server=FIRST_PROXY_SERVER),
        source_id=first_source_id,
        status=ProxyStatusEnum.disabled,
        latency=None,
        updated_at=None,
    )
    await proxy_factory.create_async(
        name=SECOND_PROXY_SERVER,
        url=build_proxy_url(server=SECOND_PROXY_SERVER),
        source_id=second_source_id,
        status=ProxyStatusEnum.disabled,
        latency=None,
        updated_at=None,
    )

    async with mocked_get_host_latency_by_server(default_latency=42) as mocked_latency:
        response = await rest_client.post("/api/proxies/status")

    assert response.status_code == status.HTTP_200_OK, response.text

    mocked_latency.assert_awaited_once()
    assert pinged_source_id_by_server(mocked_latency) == {
        FIRST_PROXY_SERVER: first_source_id,
        SECOND_PROXY_SERVER: second_source_id,
    }

    proxies_in_db = await get_proxies_by_name(db_rollback_session)

    assert proxies_in_db[FIRST_PROXY_SERVER].source_id == first_source_id
    assert proxies_in_db[SECOND_PROXY_SERVER].source_id == second_source_id
    assert proxies_in_db[FIRST_PROXY_SERVER].latency == 42
    assert proxies_in_db[SECOND_PROXY_SERVER].latency == 42


async def test_update_all_proxies_keeps_source_of_a_proxy_without_source(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    """У прокси без источника `source_id` остаётся `None` и не подменяется чужим источником."""
    proxy_factory = await sqlalchemy_model_factory_maker(factory_cls=TelegramProxyFactory, session=db_rollback_session)
    proxies_source_factory = await sqlalchemy_model_factory_maker(
        factory_cls=TelegramProxiesSourceFactory, session=db_rollback_session
    )

    source = await proxies_source_factory.create_async(status=ProxySourceStatusEnum.enabled)
    source_id = source.id

    await proxy_factory.create_async(
        name=FIRST_PROXY_SERVER,
        url=build_proxy_url(server=FIRST_PROXY_SERVER),
        source_id=None,
        status=ProxyStatusEnum.disabled,
        latency=None,
        updated_at=None,
    )
    await proxy_factory.create_async(
        name=SECOND_PROXY_SERVER,
        url=build_proxy_url(server=SECOND_PROXY_SERVER),
        source_id=source_id,
        status=ProxyStatusEnum.disabled,
        latency=None,
        updated_at=None,
    )

    async with mocked_get_host_latency_by_server(default_latency=42) as mocked_latency:
        response = await rest_client.post("/api/proxies/status")

    assert response.status_code == status.HTTP_200_OK, response.text

    mocked_latency.assert_awaited_once()
    assert pinged_source_id_by_server(mocked_latency) == {
        FIRST_PROXY_SERVER: None,
        SECOND_PROXY_SERVER: source_id,
    }

    proxies_in_db = await get_proxies_by_name(db_rollback_session)

    assert proxies_in_db[FIRST_PROXY_SERVER].source_id is None
    assert proxies_in_db[FIRST_PROXY_SERVER].updated_at is not None
    assert proxies_in_db[SECOND_PROXY_SERVER].source_id == source_id


async def test_update_all_proxies_when_proxy_is_unreachable(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    proxy_factory = await sqlalchemy_model_factory_maker(factory_cls=TelegramProxyFactory, session=db_rollback_session)

    proxy = await proxy_factory.create_async(
        name=FIRST_PROXY_SERVER,
        url=build_proxy_url(server=FIRST_PROXY_SERVER),
        status=ProxyStatusEnum.enabled,
        latency=42,
        updated_at=None,
    )
    proxy_id, source_id = proxy.id, proxy.source_id

    async with mocked_get_host_latency_by_server({FIRST_PROXY_SERVER: None}) as mocked_latency:
        response = await rest_client.post("/api/proxies/status")

    assert response.status_code == status.HTTP_200_OK, response.text

    mocked_latency.assert_awaited_once()

    updated_proxy = (
        await db_rollback_session.execute(select(TelegramProxy).where(TelegramProxy.id == proxy_id))
    ).scalar_one()

    assert updated_proxy.latency is None
    assert updated_proxy.status == ProxyStatusEnum.disabled
    assert updated_proxy.updated_at is not None
    # Прокси отвалилась, но своего источника не теряет.
    assert updated_proxy.source_id == source_id


async def test_update_all_proxies_does_not_touch_proxies_with_another_name(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    proxy_factory = await sqlalchemy_model_factory_maker(factory_cls=TelegramProxyFactory, session=db_rollback_session)

    matched_proxy = await proxy_factory.create_async(
        name=FIRST_PROXY_SERVER,
        url=build_proxy_url(server=FIRST_PROXY_SERVER),
        status=ProxyStatusEnum.disabled,
        latency=None,
        updated_at=None,
    )
    # `name` не совпадает с параметром `server` в урле, поэтому массовое обновление
    # (джойн по TelegramProxy.name) эту запись не найдёт.
    unmatched_proxy = await proxy_factory.create_async(
        name="another-name",
        url=build_proxy_url(server=SECOND_PROXY_SERVER),
        status=ProxyStatusEnum.disabled,
        latency=None,
        updated_at=None,
    )
    matched_proxy_id, unmatched_proxy_id = matched_proxy.id, unmatched_proxy.id
    matched_source_id, unmatched_source_id = matched_proxy.source_id, unmatched_proxy.source_id

    async with mocked_get_host_latency_by_server({FIRST_PROXY_SERVER: 55, SECOND_PROXY_SERVER: 606}):
        response = await rest_client.post("/api/proxies/status")

    assert response.status_code == status.HTTP_200_OK, response.text

    proxies_in_db = {
        proxy.id: proxy for proxy in (await db_rollback_session.execute(select(TelegramProxy))).scalars().all()
    }

    assert proxies_in_db[matched_proxy_id].latency == 55
    assert proxies_in_db[matched_proxy_id].status == ProxyStatusEnum.enabled
    assert proxies_in_db[matched_proxy_id].updated_at is not None
    assert proxies_in_db[matched_proxy_id].source_id == matched_source_id

    assert proxies_in_db[unmatched_proxy_id].latency is None
    assert proxies_in_db[unmatched_proxy_id].status == ProxyStatusEnum.disabled
    assert proxies_in_db[unmatched_proxy_id].updated_at is None
    assert proxies_in_db[unmatched_proxy_id].source_id == unmatched_source_id


async def test_update_all_proxies_deletes_duplicated_proxies_by_url(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    """
    Прокси с полностью совпадающим урлом считаются дублями и удаляются.

    В базе остаётся самая ранняя прокси группы, и именно она (вместе с уникальными) уезжает на пинг и обновление.
    """
    proxy_factory = await sqlalchemy_model_factory_maker(factory_cls=TelegramProxyFactory, session=db_rollback_session)
    proxies_source_factory = await sqlalchemy_model_factory_maker(
        factory_cls=TelegramProxiesSourceFactory, session=db_rollback_session
    )

    source = await proxies_source_factory.create_async(status=ProxySourceStatusEnum.enabled)
    source_id = source.id

    duplicated_url = build_proxy_url(server=FIRST_PROXY_SERVER)

    proxy_to_keep = await proxy_factory.create_async(
        name=FIRST_PROXY_SERVER,
        url=duplicated_url,
        source_id=source_id,
        status=ProxyStatusEnum.disabled,
        latency=None,
        updated_at=None,
    )
    first_duplicate = await proxy_factory.create_async(
        name=FIRST_PROXY_SERVER,
        url=duplicated_url,
        source_id=source_id,
        status=ProxyStatusEnum.disabled,
        latency=None,
        updated_at=None,
    )
    second_duplicate = await proxy_factory.create_async(
        name=FIRST_PROXY_SERVER,
        url=duplicated_url,
        source_id=source_id,
        status=ProxyStatusEnum.disabled,
        latency=None,
        updated_at=None,
    )
    unique_proxy = await proxy_factory.create_async(
        name=SECOND_PROXY_SERVER,
        url=build_proxy_url(server=SECOND_PROXY_SERVER),
        source_id=source_id,
        status=ProxyStatusEnum.disabled,
        latency=None,
        updated_at=None,
    )
    proxy_to_keep_id, unique_proxy_id = proxy_to_keep.id, unique_proxy.id
    duplicated_proxies_ids = {first_duplicate.id, second_duplicate.id}

    async with mocked_get_host_latency_by_server({FIRST_PROXY_SERVER: 55, SECOND_PROXY_SERVER: 606}) as mocked_latency:
        response = await rest_client.post("/api/proxies/status")

    assert response.status_code == status.HTTP_200_OK, response.text

    # Дубли отсеиваются до пинга: каждый урл уезжает в гейтвей ровно один раз.
    mocked_latency.assert_awaited_once()
    assert sorted(proxy_to_ping.url.params["server"] for proxy_to_ping in pinged_proxies(mocked_latency)) == sorted(
        [FIRST_PROXY_SERVER, SECOND_PROXY_SERVER]
    )

    proxies_in_db = await get_proxies_by_id(db_rollback_session)

    assert set(proxies_in_db) == {proxy_to_keep_id, unique_proxy_id}
    assert not duplicated_proxies_ids & set(proxies_in_db)

    assert proxies_in_db[proxy_to_keep_id].url == duplicated_url
    assert proxies_in_db[proxy_to_keep_id].latency == 55
    assert proxies_in_db[proxy_to_keep_id].status == ProxyStatusEnum.enabled
    assert proxies_in_db[proxy_to_keep_id].updated_at is not None
    assert proxies_in_db[proxy_to_keep_id].source_id == source_id

    assert proxies_in_db[unique_proxy_id].latency == 606
    assert proxies_in_db[unique_proxy_id].status == ProxyStatusEnum.enabled
    assert proxies_in_db[unique_proxy_id].updated_at is not None
    assert proxies_in_db[unique_proxy_id].source_id == source_id


async def test_update_all_proxies_recalculates_counters_after_deleting_duplicates(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    """Счётчики источника пересчитываются по тому, что осталось в базе после удаления дублей."""
    proxy_factory = await sqlalchemy_model_factory_maker(factory_cls=TelegramProxyFactory, session=db_rollback_session)
    proxies_source_factory = await sqlalchemy_model_factory_maker(
        factory_cls=TelegramProxiesSourceFactory, session=db_rollback_session
    )

    source = await proxies_source_factory.create_async(
        status=ProxySourceStatusEnum.enabled, proxies_count=3, active_proxies_count=0
    )
    source_id = source.id

    duplicated_url = build_proxy_url(server=FIRST_PROXY_SERVER)

    proxy_to_keep = await proxy_factory.create_async(
        name=FIRST_PROXY_SERVER,
        url=duplicated_url,
        source_id=source_id,
        status=ProxyStatusEnum.disabled,
        latency=None,
        updated_at=None,
    )
    duplicated_proxy = await proxy_factory.create_async(
        name=FIRST_PROXY_SERVER,
        url=duplicated_url,
        source_id=source_id,
        status=ProxyStatusEnum.disabled,
        latency=None,
        updated_at=None,
    )
    unique_proxy = await proxy_factory.create_async(
        name=SECOND_PROXY_SERVER,
        url=build_proxy_url(server=SECOND_PROXY_SERVER),
        source_id=source_id,
        status=ProxyStatusEnum.disabled,
        latency=None,
        updated_at=None,
    )
    proxy_to_keep_id, duplicated_proxy_id, unique_proxy_id = proxy_to_keep.id, duplicated_proxy.id, unique_proxy.id

    async with mocked_get_host_latency_by_server({FIRST_PROXY_SERVER: 55, SECOND_PROXY_SERVER: None}):
        response = await rest_client.post("/api/proxies/status")

    assert response.status_code == status.HTTP_200_OK, response.text

    proxies_in_db = await get_proxies_by_id(db_rollback_session)

    assert set(proxies_in_db) == {proxy_to_keep_id, unique_proxy_id}
    assert duplicated_proxy_id not in proxies_in_db

    source_in_db = (await get_proxies_sources_by_id(db_rollback_session))[source_id]

    assert source_in_db.proxies_count == 2
    assert source_in_db.active_proxies_count == 1


async def test_update_all_proxies_on_empty_database(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
) -> None:

    async with mocked_get_host_latency_by_server() as mocked_latency:
        response = await rest_client.post("/api/proxies/status")

    assert response.status_code == status.HTTP_200_OK, response.text
    assert response.content == b"null"

    mocked_latency.assert_awaited_once_with(urls_with_source=[])

    proxies_in_db = (await db_rollback_session.execute(select(TelegramProxy))).scalars().all()

    assert proxies_in_db == []


async def test_update_all_proxies_sends_proxies_over_chunk_size_to_taskiq(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    proxy_factory = await sqlalchemy_model_factory_maker(factory_cls=TelegramProxyFactory, session=db_rollback_session)
    proxies_source_factory = await sqlalchemy_model_factory_maker(
        factory_cls=TelegramProxiesSourceFactory, session=db_rollback_session
    )

    source = await proxies_source_factory.create_async(status=ProxySourceStatusEnum.enabled)
    source_id = source.id

    total_proxies = CHUNK_SIZE_FOR_TESTS + PROXIES_OVER_CHUNK_SIZE
    all_servers = [f"10.0.0.{number}" for number in range(total_proxies)]

    for server in all_servers:
        await proxy_factory.create_async(
            name=server,
            url=build_proxy_url(server=server),
            source_id=source_id,
            status=ProxyStatusEnum.disabled,
            latency=None,
            updated_at=None,
        )

    async with (
        mocked_save_postgres_chunk_size(),
        mocked_get_host_latency_by_server(default_latency=55) as mocked_latency,
        mocked_taskiq_run() as mocked_taskiq,
    ):
        response = await rest_client.post("/api/proxies/status")

    assert response.status_code == status.HTTP_200_OK, response.text

    mocked_latency.assert_awaited_once()
    pinged_servers = set(pinged_source_id_by_server(mocked_latency))
    assert len(pinged_servers) == CHUNK_SIZE_FOR_TESTS
    assert set(pinged_source_id_by_server(mocked_latency).values()) == {source_id}

    mocked_taskiq.assert_awaited_once()
    assert mocked_taskiq.await_args.args[0] is update_proxies_in_database_task

    deferred = deferred_source_urls(mocked_taskiq)
    deferred_servers = {URL(item["url"]).params["server"] for item in deferred}

    assert len(deferred) == PROXIES_OVER_CHUNK_SIZE
    assert pinged_servers.isdisjoint(deferred_servers)
    assert pinged_servers | deferred_servers == set(all_servers)
    # "Хвост" уезжает в таску вместе с источником каждой прокси.
    assert {item["source_id"] for item in deferred} == {source_id}

    proxies_in_db = await get_proxies_by_name(db_rollback_session)

    assert len(proxies_in_db) == total_proxies

    for server in pinged_servers:
        assert proxies_in_db[server].latency == 55
        assert proxies_in_db[server].status == ProxyStatusEnum.enabled
        assert proxies_in_db[server].updated_at is not None
        assert proxies_in_db[server].source_id == source_id

    # "Хвост" уехал в taskiq, поэтому в рамках этого запроса такие прокси остаются нетронутыми.
    for server in deferred_servers:
        assert proxies_in_db[server].latency is None
        assert proxies_in_db[server].status == ProxyStatusEnum.disabled
        assert proxies_in_db[server].updated_at is None
        assert proxies_in_db[server].source_id == source_id
