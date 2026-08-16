from collections.abc import Awaitable, Callable

from httpx import AsyncClient
from polyfactory.factories.sqlalchemy_factory import SQLAlchemyFactory
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.proxies.constants import ProxyStatusEnum
from app.core.proxies.models import TelegramProxy
from tests.integration.api.proxies.helpers import build_proxy_url, mocked_get_host_latency_by_server
from tests.support.factories.proxies import TelegramProxyFactory

FIRST_PROXY_SERVER = "1.2.3.4"
SECOND_PROXY_SERVER = "5.6.7.8"


async def test_update_all_proxies(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    proxy_factory = await sqlalchemy_model_factory_maker(factory_cls=TelegramProxyFactory, session=db_rollback_session)

    await proxy_factory.create_async(
        name=FIRST_PROXY_SERVER,
        url=build_proxy_url(server=FIRST_PROXY_SERVER),
        status=ProxyStatusEnum.disabled,
        latency=None,
        updated_at=None,
    )
    await proxy_factory.create_async(
        name=SECOND_PROXY_SERVER,
        url=build_proxy_url(server=SECOND_PROXY_SERVER),
        status=ProxyStatusEnum.enabled,
        latency=10,
        updated_at=None,
    )

    latency_by_server: dict[str, int | None] = {FIRST_PROXY_SERVER: 55, SECOND_PROXY_SERVER: 606}

    async with mocked_get_host_latency_by_server(latency_by_server) as mocked_latency:
        response = await rest_client.post("/api/proxies/status")

    assert response.status_code == status.HTTP_200_OK, response.text
    assert response.content == b"null"

    mocked_latency.assert_awaited_once()
    assert sorted(url.params["server"] for url in mocked_latency.await_args.kwargs["urls"]) == sorted(latency_by_server)

    proxies_in_db = {
        proxy.name: proxy for proxy in (await db_rollback_session.execute(select(TelegramProxy))).scalars().all()
    }

    assert len(proxies_in_db) == 2

    for server, expected_latency in latency_by_server.items():
        assert proxies_in_db[server].latency == expected_latency
        assert proxies_in_db[server].status == ProxyStatusEnum.enabled
        assert proxies_in_db[server].updated_at is not None


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
    proxy_id = proxy.id

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

    async with mocked_get_host_latency_by_server({FIRST_PROXY_SERVER: 55, SECOND_PROXY_SERVER: 606}):
        response = await rest_client.post("/api/proxies/status")

    assert response.status_code == status.HTTP_200_OK, response.text

    proxies_in_db = {
        proxy.id: proxy for proxy in (await db_rollback_session.execute(select(TelegramProxy))).scalars().all()
    }

    assert proxies_in_db[matched_proxy_id].latency == 55
    assert proxies_in_db[matched_proxy_id].status == ProxyStatusEnum.enabled
    assert proxies_in_db[matched_proxy_id].updated_at is not None

    assert proxies_in_db[unmatched_proxy_id].latency is None
    assert proxies_in_db[unmatched_proxy_id].status == ProxyStatusEnum.disabled
    assert proxies_in_db[unmatched_proxy_id].updated_at is None


async def test_update_all_proxies_on_empty_database(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
) -> None:

    async with mocked_get_host_latency_by_server() as mocked_latency:
        response = await rest_client.post("/api/proxies/status")

    assert response.status_code == status.HTTP_200_OK, response.text
    assert response.content == b"null"

    mocked_latency.assert_awaited_once_with(urls=[])

    proxies_in_db = (await db_rollback_session.execute(select(TelegramProxy))).scalars().all()

    assert proxies_in_db == []
