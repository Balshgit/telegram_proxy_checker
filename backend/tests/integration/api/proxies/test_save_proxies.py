from collections.abc import Awaitable, Callable

from assertpy import assert_that
from httpx import AsyncClient
from polyfactory.factories.sqlalchemy_factory import SQLAlchemyFactory
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.proxies.models import TelegramProxy
from tests.integration.api.proxies.helpers import mocked_github_get_proxies
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

    async with mocked_github_get_proxies(raw_proxies) as mocked_github:
        response = await rest_client.post("/api/proxies")
    assert mocked_github.calls.call_count == 0

    assert response.status_code == status.HTTP_200_OK

    data = response.json()["payload"]["data"]
    assert_that(data).extracting("url").contains(*[proxy.tg_proxy_url for proxy in proxies])

    proxies_in_db = (await db_rollback_session.execute(select(TelegramProxy))).scalars().all()

    assert len(proxies_in_db) == 3
