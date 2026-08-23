from collections.abc import Awaitable, Callable

from httpx import AsyncClient
from polyfactory.factories.sqlalchemy_factory import SQLAlchemyFactory
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.proxies.constants import ProxySourceStatusEnum
from app.core.proxies.models import TelegramProxy
from tests.integration.api.proxies.helpers import (
    MISSING_PROXY_SOURCE_ID,
    build_proxy_url,
    get_proxies_by_url,
    mocked_get_host_latency_for_urls,
    mocked_github_get_proxies_by_source,
    source_route_name,
)
from tests.support.factories.proxies import TelegramProxiesSourceFactory


async def test_save_proxies_from_the_chosen_source_only(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    """
    С непустым `source_ids` опрашивается только выбранный источник.

    Урл второго источника специально не замокан: с `assert_all_mocked=True` поход за ним
    уронит тест на respx, а не молча добавит лишние прокси.
    """
    proxies_source_factory = await sqlalchemy_model_factory_maker(
        factory_cls=TelegramProxiesSourceFactory, session=db_rollback_session
    )

    chosen_source = await proxies_source_factory.create_async(status=ProxySourceStatusEnum.enabled)
    await proxies_source_factory.create_async(status=ProxySourceStatusEnum.enabled)
    chosen_source_id, chosen_source_url = chosen_source.id, chosen_source.url

    chosen_source_urls = [build_proxy_url(server=f"10.0.0.{number}") for number in range(2)]

    async with (
        mocked_github_get_proxies_by_source({chosen_source_url: "\n".join(chosen_source_urls)}) as mocked_github,
        mocked_get_host_latency_for_urls(default_latency=42),
    ):
        response = await rest_client.post("/api/proxies", json={"source_ids": [chosen_source_id]})

        assert mocked_github.calls.call_count == 1
        assert mocked_github.routes[source_route_name(chosen_source_url)].call_count == 1

    assert response.status_code == status.HTTP_201_CREATED, response.text

    proxies_in_db = await get_proxies_by_url(db_rollback_session)

    assert sorted(proxies_in_db) == sorted(chosen_source_urls)

    for proxy in proxies_in_db.values():
        assert proxy.source_id == chosen_source_id


async def test_save_proxies_from_several_chosen_sources(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    proxies_source_factory = await sqlalchemy_model_factory_maker(
        factory_cls=TelegramProxiesSourceFactory, session=db_rollback_session
    )

    first_source = await proxies_source_factory.create_async(status=ProxySourceStatusEnum.enabled)
    second_source = await proxies_source_factory.create_async(status=ProxySourceStatusEnum.enabled)
    await proxies_source_factory.create_async(status=ProxySourceStatusEnum.enabled)

    first_source_id, second_source_id = first_source.id, second_source.id

    first_source_urls = [build_proxy_url(server=f"10.0.0.{number}") for number in range(2)]
    second_source_urls = [build_proxy_url(server=f"10.0.1.{number}") for number in range(3)]

    raw_proxies_by_source = {
        first_source.url: "\n".join(first_source_urls),
        second_source.url: "\n".join(second_source_urls),
    }

    async with (
        mocked_github_get_proxies_by_source(raw_proxies_by_source) as mocked_github,
        mocked_get_host_latency_for_urls(default_latency=42),
    ):
        response = await rest_client.post("/api/proxies", json={"source_ids": [first_source_id, second_source_id]})

        assert mocked_github.calls.call_count == len(raw_proxies_by_source)

    assert response.status_code == status.HTTP_201_CREATED, response.text

    proxies_in_db = await get_proxies_by_url(db_rollback_session)

    assert sorted(proxies_in_db) == sorted(first_source_urls + second_source_urls)

    expected_source_id_by_url = dict.fromkeys(first_source_urls, first_source_id) | dict.fromkeys(
        second_source_urls, second_source_id
    )

    assert {url: proxy.source_id for url, proxy in proxies_in_db.items()} == expected_source_id_by_url


async def test_save_proxies_ignores_unknown_source_ids(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    """Несуществующие id просто отсеиваются фильтром в репозитории, запрос не падает."""
    proxies_source_factory = await sqlalchemy_model_factory_maker(
        factory_cls=TelegramProxiesSourceFactory, session=db_rollback_session
    )

    chosen_source = await proxies_source_factory.create_async(status=ProxySourceStatusEnum.enabled)
    chosen_source_id, chosen_source_url = chosen_source.id, chosen_source.url

    chosen_source_urls = [build_proxy_url(server="10.0.0.1")]

    async with (
        mocked_github_get_proxies_by_source({chosen_source_url: "\n".join(chosen_source_urls)}) as mocked_github,
        mocked_get_host_latency_for_urls(default_latency=42),
    ):
        response = await rest_client.post(
            "/api/proxies", json={"source_ids": [chosen_source_id, MISSING_PROXY_SOURCE_ID]}
        )

        assert mocked_github.calls.call_count == 1

    assert response.status_code == status.HTTP_201_CREATED, response.text

    proxies_in_db = await get_proxies_by_url(db_rollback_session)

    assert sorted(proxies_in_db) == sorted(chosen_source_urls)
    assert proxies_in_db[chosen_source_urls[0]].source_id == chosen_source_id


async def test_save_proxies_with_only_unknown_source_ids(
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

    response = await rest_client.post("/api/proxies", json={"source_ids": [MISSING_PROXY_SOURCE_ID]})

    assert response.status_code == status.HTTP_202_ACCEPTED, response.text

    assert response.json()["error"] == {
        "meta": {"message": None},
        "type": "NoProxiesAddedError",
        "title": "No proxies to add",
    }

    proxies_in_db = (await db_rollback_session.execute(select(TelegramProxy))).scalars().all()

    assert proxies_in_db == []


async def test_save_proxies_with_disabled_chosen_source(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    """Выключенный источник не опрашивается, даже если его явно выбрали."""
    proxies_source_factory = await sqlalchemy_model_factory_maker(
        factory_cls=TelegramProxiesSourceFactory, session=db_rollback_session
    )

    disabled_source = await proxies_source_factory.create_async(status=ProxySourceStatusEnum.disabled)
    await proxies_source_factory.create_async(status=ProxySourceStatusEnum.enabled)
    disabled_source_id = disabled_source.id

    response = await rest_client.post("/api/proxies", json={"source_ids": [disabled_source_id]})

    assert response.status_code == status.HTTP_202_ACCEPTED, response.text

    proxies_in_db = (await db_rollback_session.execute(select(TelegramProxy))).scalars().all()

    assert proxies_in_db == []


async def test_save_proxies_with_empty_source_ids_uses_all_enabled_sources(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    """Пустой список — то же самое, что и отсутствие тела: обходим все включённые источники."""
    proxies_source_factory = await sqlalchemy_model_factory_maker(
        factory_cls=TelegramProxiesSourceFactory, session=db_rollback_session
    )

    first_source = await proxies_source_factory.create_async(status=ProxySourceStatusEnum.enabled)
    second_source = await proxies_source_factory.create_async(status=ProxySourceStatusEnum.enabled)

    first_source_urls = [build_proxy_url(server="10.0.0.1")]
    second_source_urls = [build_proxy_url(server="10.0.1.1")]

    raw_proxies_by_source = {
        first_source.url: "\n".join(first_source_urls),
        second_source.url: "\n".join(second_source_urls),
    }

    async with (
        mocked_github_get_proxies_by_source(raw_proxies_by_source) as mocked_github,
        mocked_get_host_latency_for_urls(default_latency=42),
    ):
        response = await rest_client.post("/api/proxies", json={"source_ids": []})

        assert mocked_github.calls.call_count == len(raw_proxies_by_source)

    assert response.status_code == status.HTTP_201_CREATED, response.text

    proxies_in_db = await get_proxies_by_url(db_rollback_session)

    assert sorted(proxies_in_db) == sorted(first_source_urls + second_source_urls)


async def test_save_proxies_with_invalid_source_ids(
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

    response = await rest_client.post("/api/proxies", json={"source_ids": ["not-a-number"]})

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, response.text

    proxies_in_db = (await db_rollback_session.execute(select(TelegramProxy))).scalars().all()

    assert proxies_in_db == []
