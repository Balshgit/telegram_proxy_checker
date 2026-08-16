from collections.abc import Awaitable, Callable

from assertpy import assert_that
from httpx import URL, AsyncClient
from polyfactory.factories.sqlalchemy_factory import SQLAlchemyFactory
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.proxies.constants import ProxyStatusEnum
from app.core.proxies.models import TelegramProxy
from tests.integration.api.proxies.helpers import (
    GITHUB_PROXIES_ROUTE_NAME,
    mocked_get_host_latency_for_urls,
    mocked_github_get_proxies,
)
from tests.support.factories.proxies import TelegramProxyFactory


async def test_save_new_proxies_success(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    proxy_factory = await sqlalchemy_model_factory_maker(factory_cls=TelegramProxyFactory, session=db_rollback_session)

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
