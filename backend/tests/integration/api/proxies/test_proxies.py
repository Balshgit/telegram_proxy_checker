from collections.abc import Awaitable, Callable

from httpx import AsyncClient
from polyfactory.factories.sqlalchemy_factory import SQLAlchemyFactory
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from tests.support.factories.proxies import TelegramProxyFactory


async def test_get_all_proxies(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    proxy_factory = await sqlalchemy_model_factory_maker(factory_cls=TelegramProxyFactory, session=db_rollback_session)

    proxies = await proxy_factory.create_batch_async(size=3)

    response = await rest_client.get("/api/proxies")
    assert response.status_code == status.HTTP_200_OK

    proxy_1, proxy_2, proxy_3 = sorted(proxies, key=lambda x: x.id)

    data = response.json()["payload"]["data"]
    counters = response.json()["payload"]["counters"]

    assert len(data) == 3
    assert counters["total"] == 3

    assert data == [
        {
            "id": proxy_1.id,
            "url": proxy_1.url,
            "created_at": proxy_1.created_at.isoformat(),
            "updated_at": None,
            "status": proxy_1.status,
            "ping": proxy_1.ping,
        },
        {
            "id": proxy_2.id,
            "url": proxy_2.url,
            "created_at": proxy_2.created_at.isoformat(),
            "updated_at": None,
            "status": proxy_2.status,
            "ping": proxy_2.ping,
        },
        {
            "id": proxy_3.id,
            "url": proxy_3.url,
            "created_at": proxy_3.created_at.isoformat(),
            "updated_at": None,
            "status": proxy_3.status,
            "ping": proxy_3.ping,
        },
    ]
