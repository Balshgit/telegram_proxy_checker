from collections.abc import Awaitable, Callable

from httpx import AsyncClient
from polyfactory.factories.sqlalchemy_factory import SQLAlchemyFactory
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.proxies.constants import ProxyStatusEnum
from app.core.proxies.models import TelegramProxy
from tests.support.factories.proxies import TelegramProxyFactory


async def test_delete_all_proxies(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    proxy_factory = await sqlalchemy_model_factory_maker(factory_cls=TelegramProxyFactory, session=db_rollback_session)

    await proxy_factory.create_async(latency=42, status=ProxyStatusEnum.enabled)
    await proxy_factory.create_async(latency=543, status=ProxyStatusEnum.disabled)
    await proxy_factory.create_async(latency=None, status=ProxyStatusEnum.enabled)

    proxies_before = (await db_rollback_session.execute(select(TelegramProxy))).scalars().all()
    assert len(proxies_before) == 3

    response = await rest_client.delete("/api/proxies")

    assert response.status_code == status.HTTP_202_ACCEPTED, response.text
    assert response.content == b"null"

    proxies_after = (await db_rollback_session.execute(select(TelegramProxy))).scalars().all()

    assert proxies_after == []


async def test_delete_all_proxies_on_empty_database(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
) -> None:

    response = await rest_client.delete("/api/proxies")

    assert response.status_code == status.HTTP_202_ACCEPTED, response.text
    assert response.content == b"null"

    proxies_in_db = (await db_rollback_session.execute(select(TelegramProxy))).scalars().all()

    assert proxies_in_db == []
