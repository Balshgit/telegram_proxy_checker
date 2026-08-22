from collections.abc import Awaitable, Callable

from httpx import AsyncClient
from polyfactory.factories.sqlalchemy_factory import SQLAlchemyFactory
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.proxies.constants import ProxyStatusEnum
from app.core.proxies.models import TelegramProxy
from tests.integration.api.proxies.helpers import MISSING_PROXY_ID
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


async def test_delete_a_proxy(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    proxy_factory = await sqlalchemy_model_factory_maker(factory_cls=TelegramProxyFactory, session=db_rollback_session)

    proxy_to_delete = await proxy_factory.create_async(latency=42, status=ProxyStatusEnum.enabled)
    proxy_to_keep = await proxy_factory.create_async(latency=543, status=ProxyStatusEnum.disabled)
    proxy_to_delete_id, proxy_to_keep_id = proxy_to_delete.id, proxy_to_keep.id

    response = await rest_client.delete(f"/api/proxies/{proxy_to_delete_id}")

    # 204 не допускает тела ответа, поэтому fastapi отдаёт пустой буфер, а не "null" как на удалении всех проксей
    assert response.status_code == status.HTTP_204_NO_CONTENT, response.text
    assert response.content == b""

    proxies_after = (await db_rollback_session.execute(select(TelegramProxy))).scalars().all()

    assert [proxy.id for proxy in proxies_after] == [proxy_to_keep_id]


async def test_delete_a_proxy_that_does_not_exist(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    """Удаление идемпотентно: репозиторий просто выполняет DELETE ... WHERE id = ..., 404 тут не поднимается."""
    proxy_factory = await sqlalchemy_model_factory_maker(factory_cls=TelegramProxyFactory, session=db_rollback_session)

    proxy = await proxy_factory.create_async(latency=42, status=ProxyStatusEnum.enabled)
    proxy_id = proxy.id

    response = await rest_client.delete(f"/api/proxies/{MISSING_PROXY_ID}")

    assert response.status_code == status.HTTP_204_NO_CONTENT, response.text
    assert response.content == b""

    proxies_in_db = (await db_rollback_session.execute(select(TelegramProxy))).scalars().all()

    assert [proxy_in_db.id for proxy_in_db in proxies_in_db] == [proxy_id]


async def test_delete_a_proxy_with_non_integer_id(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
) -> None:

    response = await rest_client.delete("/api/proxies/unknown")

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, response.text
