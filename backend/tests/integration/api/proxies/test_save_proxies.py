from collections.abc import Awaitable, Callable

from assertpy import assert_that
from httpx import URL, AsyncClient
from polyfactory.factories.sqlalchemy_factory import SQLAlchemyFactory
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.proxies.constants import ProxySourceStatusEnum, ProxyStatusEnum
from app.core.proxies.models import TelegramProxy
from app.core.proxies.tasks import save_proxies_to_database_task
from tests.integration.api.proxies.helpers import (
    CHUNK_SIZE_FOR_TESTS,
    GITHUB_PROXIES_ROUTE_NAME,
    build_proxy_url,
    mocked_get_host_latency_for_urls,
    mocked_github_get_proxies,
    mocked_github_get_proxies_by_source,
    mocked_save_postgres_chunk_size,
    mocked_taskiq_run,
    source_route_name,
)
from tests.support.factories.proxies import TelegramProxiesSourceFactory, TelegramProxyFactory

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

    await proxies_source_factory.create_async(status=ProxySourceStatusEnum.enabled)

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

    assert response.status_code == status.HTTP_200_OK

    mocked_latency.assert_awaited_once()
    assert sorted(str(url) for url in mocked_latency.await_args.kwargs["urls"]) == sorted(latency_by_url)

    data = response.json()["payload"]["data"]
    assert_that(data).extracting("url").contains(*[proxy.tg_proxy_url for proxy in proxies])

    proxies_in_db = (await db_rollback_session.execute(select(TelegramProxy))).scalars().all()

    assert len(proxies_in_db) == 3

    latency_by_name = {item["name"]: item["latency"] for item in data}
    status_by_name = {item["name"]: item["status"] for item in data}
    for proxy in proxies_in_db:
        expected_latency = latency_by_url[str(proxy.url)]
        proxy_name = URL(proxy.url).params["server"]
        assert latency_by_name[proxy_name] == expected_latency
        assert status_by_name[proxy_name] == (
            ProxyStatusEnum.enabled if expected_latency is not None else ProxyStatusEnum.disabled
        )


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

    assert response.status_code == status.HTTP_200_OK, response.text

    # Пинг идёт одним пакетом на все источники сразу.
    mocked_latency.assert_awaited_once()
    assert sorted(str(url) for url in mocked_latency.await_args.kwargs["urls"]) == sorted(all_urls)

    data = response.json()["payload"]["data"]

    assert len(data) == len(all_urls)

    proxies_in_db = (await db_rollback_session.execute(select(TelegramProxy))).scalars().all()

    assert sorted(proxy.url for proxy in proxies_in_db) == sorted(all_urls)

    for proxy in proxies_in_db:
        assert proxy.latency == 42
        assert proxy.status == ProxyStatusEnum.enabled


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

    enabled_source_urls = [build_proxy_url(server=f"10.0.0.{number}") for number in range(2)]

    async with (
        mocked_github_get_proxies_by_source({enabled_source.url: "\n".join(enabled_source_urls)}) as mocked_github,
        mocked_get_host_latency_for_urls(default_latency=42) as mocked_latency,
    ):
        response = await rest_client.post("/api/proxies")

        assert mocked_github.calls.call_count == 1
        assert mocked_github.routes[source_route_name(enabled_source.url)].call_count == 1

    assert response.status_code == status.HTTP_200_OK, response.text

    mocked_latency.assert_awaited_once()
    assert sorted(str(url) for url in mocked_latency.await_args.kwargs["urls"]) == sorted(enabled_source_urls)

    proxies_in_db = (await db_rollback_session.execute(select(TelegramProxy))).scalars().all()

    assert sorted(proxy.url for proxy in proxies_in_db) == sorted(enabled_source_urls)


async def test_save_new_proxies_deduplicates_urls_from_several_sources(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    """Один и тот же урл в двух источниках должен сохраниться в базу ровно один раз."""
    proxies_source_factory = await sqlalchemy_model_factory_maker(
        factory_cls=TelegramProxiesSourceFactory, session=db_rollback_session
    )

    first_source = await proxies_source_factory.create_async(status=ProxySourceStatusEnum.enabled)
    second_source = await proxies_source_factory.create_async(status=ProxySourceStatusEnum.enabled)

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

    assert response.status_code == status.HTTP_200_OK, response.text

    proxies_in_db = (await db_rollback_session.execute(select(TelegramProxy))).scalars().all()

    assert sorted(proxy.url for proxy in proxies_in_db) == sorted([shared_url, unique_url])


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

    await proxies_source_factory.create_async(status=ProxySourceStatusEnum.enabled)

    existing_proxy = await proxy_factory.create_async(latency=42)
    existing_proxy_id = existing_proxy.id

    async with mocked_github_get_proxies(existing_proxy.url) as mocked_github:
        response = await rest_client.post("/api/proxies")

        assert mocked_github.routes[GITHUB_PROXIES_ROUTE_NAME].call_count == 1

    assert response.status_code == status.HTTP_400_BAD_REQUEST, response.text

    assert response.json()["error"] == {
        "meta": {"message": None},
        "type": "NoProxiesAddedError",
        "title": "No proxies to add",
    }

    proxies_in_db = (await db_rollback_session.execute(select(TelegramProxy))).scalars().all()

    assert [proxy.id for proxy in proxies_in_db] == [existing_proxy_id]


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

    assert response.status_code == status.HTTP_400_BAD_REQUEST, response.text

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

    await proxies_source_factory.create_async(status=ProxySourceStatusEnum.enabled)

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

    assert response.status_code == status.HTTP_200_OK, response.text

    mocked_latency.assert_awaited_once()
    assert len(mocked_latency.await_args.kwargs["urls"]) == CHUNK_SIZE_FOR_TESTS

    mocked_taskiq.assert_awaited_once()
    assert mocked_taskiq.await_args.args[0] is save_proxies_to_database_task

    deferred_urls = mocked_taskiq.await_args.kwargs["params"]["urls"]
    assert len(deferred_urls) == PROXIES_OVER_CHUNK_SIZE

    data = response.json()["payload"]["data"]
    assert len(data) == CHUNK_SIZE_FOR_TESTS

    proxies_in_db = (await db_rollback_session.execute(select(TelegramProxy))).scalars().all()

    assert len(proxies_in_db) == CHUNK_SIZE_FOR_TESTS

    # Сервис берёт урлы из set().difference(), порядок недетерминированный:
    # проверяем, что сохранённые и отложенные урлы не пересекаются и вместе дают исходный список.
    saved_urls = {proxy.url for proxy in proxies_in_db}

    assert saved_urls.isdisjoint(deferred_urls)
    assert saved_urls | set(deferred_urls) == set(all_urls)

    for proxy in proxies_in_db:
        assert proxy.latency == 55
        assert proxy.status == ProxyStatusEnum.enabled
