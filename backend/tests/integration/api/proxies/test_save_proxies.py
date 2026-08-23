from collections.abc import Awaitable, Callable

from httpx import URL, AsyncClient
from polyfactory.factories.sqlalchemy_factory import SQLAlchemyFactory
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.proxies.constants import ProxyStatusEnum
from app.core.proxies.models import TelegramProxy
from app.core.proxies.tasks import save_proxies_to_database_task
from app.core.proxies_sources.constants import ProxySourceStatusEnum
from tests.integration.api.proxies.helpers import (
    CHUNK_SIZE_FOR_TESTS,
    GITHUB_PROXIES_ROUTE_NAME,
    build_proxy_url,
    deferred_source_urls,
    get_proxies_by_url,
    mocked_get_host_latency_for_urls,
    mocked_github_get_proxies,
    mocked_github_get_proxies_by_source,
    mocked_save_postgres_chunk_size,
    mocked_taskiq_run,
    pinged_proxies,
    source_route_name,
)
from tests.support.factories.proxies import TelegramProxyFactory
from tests.support.factories.proxies_sources import TelegramProxiesSourceFactory

PROXIES_OVER_CHUNK_SIZE = 2


async def test_save_new_proxies_success(
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

    proxies = [proxy_factory.build() for _ in range(3)]
    raw_proxies = "\n".join(proxy.url for proxy in proxies)

    latency_by_url: dict[str, int | None] = {
        proxies[0].url: 10,
        proxies[1].url: 500,
        proxies[2].url: None,  # недоступная прокси -> disabled
    }

    async with (
        mocked_github_get_proxies(raw_proxies) as mocked_github,
        mocked_get_host_latency_for_urls(latency_by_url) as mocked_latency,
    ):
        response = await rest_client.post("/api/proxies")

        assert mocked_github.calls.call_count == 1
        assert mocked_github.routes[GITHUB_PROXIES_ROUTE_NAME].call_count == 1

    assert response.status_code == status.HTTP_201_CREATED, response.text
    assert response.content == b"null"

    mocked_latency.assert_awaited_once()
    assert sorted(str(proxy_to_ping.url) for proxy_to_ping in pinged_proxies(mocked_latency)) == sorted(latency_by_url)

    proxies_in_db = await get_proxies_by_url(db_rollback_session)

    assert sorted(proxies_in_db) == sorted(latency_by_url)

    for url, expected_latency in latency_by_url.items():
        proxy_in_db = proxies_in_db[url]
        assert proxy_in_db.name == URL(url).params["server"]
        assert proxy_in_db.latency == expected_latency
        assert proxy_in_db.status == (
            ProxyStatusEnum.enabled if expected_latency is not None else ProxyStatusEnum.disabled
        )
        # Источник, из которого прилетел урл, сохраняется вместе с прокси.
        assert proxy_in_db.source_id == source_id


async def test_save_new_proxies_from_several_sources(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    """Источников может быть несколько: сервис обходит их все и складывает урлы в одну кучу."""
    proxies_source_factory = await sqlalchemy_model_factory_maker(
        factory_cls=TelegramProxiesSourceFactory, session=db_rollback_session
    )

    first_source = await proxies_source_factory.create_async(status=ProxySourceStatusEnum.enabled)
    second_source = await proxies_source_factory.create_async(status=ProxySourceStatusEnum.enabled)
    first_source_id, second_source_id = first_source.id, second_source.id

    first_source_urls = [build_proxy_url(server=f"10.0.0.{number}") for number in range(2)]
    second_source_urls = [build_proxy_url(server=f"10.0.1.{number}") for number in range(3)]
    all_urls = first_source_urls + second_source_urls

    raw_proxies_by_source = {
        first_source.url: "\n".join(first_source_urls),
        second_source.url: "\n".join(second_source_urls),
    }

    async with (
        mocked_github_get_proxies_by_source(raw_proxies_by_source) as mocked_github,
        mocked_get_host_latency_for_urls(default_latency=42) as mocked_latency,
    ):
        response = await rest_client.post("/api/proxies")

        assert mocked_github.calls.call_count == len(raw_proxies_by_source)
        for source_url in raw_proxies_by_source:
            assert mocked_github.routes[source_route_name(source_url)].call_count == 1

    assert response.status_code == status.HTTP_201_CREATED, response.text
    assert response.content == b"null"

    # Пинг идёт одним пакетом на все источники сразу.
    mocked_latency.assert_awaited_once()
    assert sorted(str(proxy_to_ping.url) for proxy_to_ping in pinged_proxies(mocked_latency)) == sorted(all_urls)

    proxies_in_db = await get_proxies_by_url(db_rollback_session)

    assert sorted(proxies_in_db) == sorted(all_urls)

    for proxy in proxies_in_db.values():
        assert proxy.latency == 42
        assert proxy.status == ProxyStatusEnum.enabled

    # Каждая прокси помнит именно тот источник, который её отдал.
    expected_source_id_by_url = dict.fromkeys(first_source_urls, first_source_id) | dict.fromkeys(
        second_source_urls, second_source_id
    )

    assert {url: proxy.source_id for url, proxy in proxies_in_db.items()} == expected_source_id_by_url


async def test_save_new_proxies_ignores_disabled_source(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    """
    Выключенный источник не должен опрашиваться вообще.

    Урл выключенного источника специально не замокан: с `assert_all_mocked=True` любой поход
    за ним уронит тест на respx, а не молча добавит прокси в базу.
    """
    proxies_source_factory = await sqlalchemy_model_factory_maker(
        factory_cls=TelegramProxiesSourceFactory, session=db_rollback_session
    )

    enabled_source = await proxies_source_factory.create_async(status=ProxySourceStatusEnum.enabled)
    await proxies_source_factory.create_async(status=ProxySourceStatusEnum.disabled)
    enabled_source_id = enabled_source.id

    enabled_source_urls = [build_proxy_url(server=f"10.0.0.{number}") for number in range(2)]

    async with (
        mocked_github_get_proxies_by_source({enabled_source.url: "\n".join(enabled_source_urls)}) as mocked_github,
        mocked_get_host_latency_for_urls(default_latency=42) as mocked_latency,
    ):
        response = await rest_client.post("/api/proxies")

        assert mocked_github.calls.call_count == 1
        assert mocked_github.routes[source_route_name(enabled_source.url)].call_count == 1

    assert response.status_code == status.HTTP_201_CREATED, response.text

    mocked_latency.assert_awaited_once()
    assert sorted(str(proxy_to_ping.url) for proxy_to_ping in pinged_proxies(mocked_latency)) == sorted(
        enabled_source_urls
    )

    proxies_in_db = await get_proxies_by_url(db_rollback_session)

    assert sorted(proxies_in_db) == sorted(enabled_source_urls)

    for proxy in proxies_in_db.values():
        assert proxy.source_id == enabled_source_id


async def test_save_new_proxies_deduplicates_urls_from_several_sources(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    """
    Один и тот же урл в двух источниках должен сохраниться в базу ровно один раз.

    Дедупликация идёт по урлу, поэтому побеждает один из источников: какой именно —
    зависит от порядка обхода, и тест это не фиксирует.
    """
    proxies_source_factory = await sqlalchemy_model_factory_maker(
        factory_cls=TelegramProxiesSourceFactory, session=db_rollback_session
    )

    first_source = await proxies_source_factory.create_async(status=ProxySourceStatusEnum.enabled)
    second_source = await proxies_source_factory.create_async(status=ProxySourceStatusEnum.enabled)
    first_source_id, second_source_id = first_source.id, second_source.id

    shared_url = build_proxy_url(server="10.0.0.1")
    unique_url = build_proxy_url(server="10.0.0.2")

    raw_proxies_by_source = {
        first_source.url: shared_url,
        second_source.url: f"{shared_url}\n{unique_url}",
    }

    async with (
        mocked_github_get_proxies_by_source(raw_proxies_by_source) as mocked_github,
        mocked_get_host_latency_for_urls(default_latency=42),
    ):
        response = await rest_client.post("/api/proxies")

        assert mocked_github.calls.call_count == len(raw_proxies_by_source)

    assert response.status_code == status.HTTP_201_CREATED, response.text

    proxies_in_db = await get_proxies_by_url(db_rollback_session)

    assert sorted(proxies_in_db) == sorted([shared_url, unique_url])

    # У общего урла источник — один из двух, но обязательно проставлен.
    assert proxies_in_db[shared_url].source_id in {first_source_id, second_source_id}
    # Уникальный урл есть только у второго источника, тут разночтений быть не может.
    assert proxies_in_db[unique_url].source_id == second_source_id


async def test_save_new_proxies_skips_url_already_saved_from_another_source(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    """
    Урл, уже сохранённый из одного источника, не добавляется повторно из другого.

    Источник у существующей записи при этом не переписывается: сервис такие урлы просто пропускает.
    """
    proxy_factory = await sqlalchemy_model_factory_maker(factory_cls=TelegramProxyFactory, session=db_rollback_session)
    proxies_source_factory = await sqlalchemy_model_factory_maker(
        factory_cls=TelegramProxiesSourceFactory, session=db_rollback_session
    )

    old_source = await proxies_source_factory.create_async(status=ProxySourceStatusEnum.disabled)
    new_source = await proxies_source_factory.create_async(status=ProxySourceStatusEnum.enabled)
    old_source_id, new_source_id = old_source.id, new_source.id

    existing_url = build_proxy_url(server="10.0.0.1")
    fresh_url = build_proxy_url(server="10.0.0.2")

    existing_proxy = await proxy_factory.create_async(
        name="10.0.0.1", url=existing_url, source_id=old_source_id, latency=42, status=ProxyStatusEnum.enabled
    )
    existing_proxy_id = existing_proxy.id

    async with (
        mocked_github_get_proxies_by_source({new_source.url: f"{existing_url}\n{fresh_url}"}),
        mocked_get_host_latency_for_urls(default_latency=77) as mocked_latency,
    ):
        response = await rest_client.post("/api/proxies")

    assert response.status_code == status.HTTP_201_CREATED, response.text

    mocked_latency.assert_awaited_once()
    assert [str(proxy_to_ping.url) for proxy_to_ping in pinged_proxies(mocked_latency)] == [fresh_url]

    proxies_in_db = await get_proxies_by_url(db_rollback_session)

    assert sorted(proxies_in_db) == sorted([existing_url, fresh_url])

    assert proxies_in_db[existing_url].id == existing_proxy_id
    assert proxies_in_db[existing_url].source_id == old_source_id
    assert proxies_in_db[existing_url].latency == 42

    assert proxies_in_db[fresh_url].source_id == new_source_id
    assert proxies_in_db[fresh_url].latency == 77


async def test_save_proxies_when_all_proxies_already_exist(
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

    # Источник у прокси задаём явно: иначе фабрика заведёт ещё один включённый источник,
    # и сервис пойдёт в github дважды.
    existing_proxy = await proxy_factory.create_async(latency=42, source_id=source_id)
    existing_proxy_id = existing_proxy.id

    async with mocked_github_get_proxies(existing_proxy.url) as mocked_github:
        response = await rest_client.post("/api/proxies")

        assert mocked_github.routes[GITHUB_PROXIES_ROUTE_NAME].call_count == 1

    assert response.status_code == status.HTTP_202_ACCEPTED, response.text

    assert response.json()["error"] == {
        "meta": {"message": None},
        "type": "NoProxiesAddedError",
        "title": "No proxies to add",
    }

    proxies_in_db = (await db_rollback_session.execute(select(TelegramProxy))).scalars().all()

    assert [proxy.id for proxy in proxies_in_db] == [existing_proxy_id]
    assert [proxy.source_id for proxy in proxies_in_db] == [source_id]


async def test_save_proxies_skips_urls_without_server_and_port(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    proxies_source_factory = await sqlalchemy_model_factory_maker(
        factory_cls=TelegramProxiesSourceFactory, session=db_rollback_session
    )

    await proxies_source_factory.create_async(status=ProxySourceStatusEnum.enabled)

    raw_proxies = "https://proxy.example.com?secret=ee1337\nhttps://proxy.example.com"

    async with mocked_github_get_proxies(raw_proxies) as mocked_github:
        response = await rest_client.post("/api/proxies")

        assert mocked_github.routes[GITHUB_PROXIES_ROUTE_NAME].call_count == 1

    assert response.status_code == status.HTTP_202_ACCEPTED, response.text

    proxies_in_db = (await db_rollback_session.execute(select(TelegramProxy))).scalars().all()

    assert proxies_in_db == []


async def test_save_proxies_sends_urls_over_chunk_size_to_taskiq(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    proxies_source_factory = await sqlalchemy_model_factory_maker(
        factory_cls=TelegramProxiesSourceFactory, session=db_rollback_session
    )

    source = await proxies_source_factory.create_async(status=ProxySourceStatusEnum.enabled)
    source_id = source.id

    total_proxies = CHUNK_SIZE_FOR_TESTS + PROXIES_OVER_CHUNK_SIZE
    all_urls = [build_proxy_url(server=f"10.0.0.{number}") for number in range(total_proxies)]
    raw_proxies = "\n".join(all_urls)

    async with (
        mocked_save_postgres_chunk_size(),
        mocked_github_get_proxies(raw_proxies) as mocked_github,
        mocked_get_host_latency_for_urls(default_latency=55) as mocked_latency,
        mocked_taskiq_run() as mocked_taskiq,
    ):
        response = await rest_client.post("/api/proxies")

        assert mocked_github.routes[GITHUB_PROXIES_ROUTE_NAME].call_count == 1

    assert response.status_code == status.HTTP_201_CREATED, response.text
    assert response.content == b"null"

    mocked_latency.assert_awaited_once()
    assert len(pinged_proxies(mocked_latency)) == CHUNK_SIZE_FOR_TESTS

    mocked_taskiq.assert_awaited_once()
    assert mocked_taskiq.await_args.args[0] is save_proxies_to_database_task

    deferred = deferred_source_urls(mocked_taskiq)
    deferred_urls = [item["url"] for item in deferred]

    assert len(deferred) == PROXIES_OVER_CHUNK_SIZE
    # "Хвост" уезжает в таску вместе с источником, иначе отложенные прокси сохранились бы без него.
    assert {item["source_id"] for item in deferred} == {source_id}

    proxies_in_db = await get_proxies_by_url(db_rollback_session)

    assert len(proxies_in_db) == CHUNK_SIZE_FOR_TESTS

    saved_urls = set(proxies_in_db)

    assert saved_urls.isdisjoint(deferred_urls)
    assert saved_urls | set(deferred_urls) == set(all_urls)

    for proxy in proxies_in_db.values():
        assert proxy.latency == 55
        assert proxy.status == ProxyStatusEnum.enabled
        assert proxy.source_id == source_id
