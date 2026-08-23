from collections.abc import Awaitable, Callable

from httpx import AsyncClient
from polyfactory.factories.sqlalchemy_factory import SQLAlchemyFactory
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.proxies.constants import ProxySourceStatusEnum, ProxyStatusEnum
from tests.integration.api.proxies.helpers import (
    MISSING_PROXY_SOURCE_ID,
    get_proxies_by_id,
    get_proxies_sources_by_id,
)
from tests.support.factories.proxies import TelegramProxiesSourceFactory, TelegramProxyFactory


async def test_delete_proxies_source(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    proxies_source_factory = await sqlalchemy_model_factory_maker(
        factory_cls=TelegramProxiesSourceFactory, session=db_rollback_session
    )

    source_to_delete = await proxies_source_factory.create_async(status=ProxySourceStatusEnum.enabled)
    source_to_keep = await proxies_source_factory.create_async(status=ProxySourceStatusEnum.enabled)
    source_to_delete_id, source_to_keep_id = source_to_delete.id, source_to_keep.id

    response = await rest_client.delete(f"/api/proxies/sources/{source_to_delete_id}")

    assert response.status_code == status.HTTP_204_NO_CONTENT, response.text

    sources_in_db = await get_proxies_sources_by_id(db_rollback_session)

    assert sorted(sources_in_db) == [source_to_keep_id]


async def test_delete_proxies_source_keeps_its_proxies(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    """Прокси удалённого источника остаются в базе и просто теряют привязку (`ON DELETE SET NULL`)."""
    proxy_factory = await sqlalchemy_model_factory_maker(factory_cls=TelegramProxyFactory, session=db_rollback_session)
    proxies_source_factory = await sqlalchemy_model_factory_maker(
        factory_cls=TelegramProxiesSourceFactory, session=db_rollback_session
    )

    source_to_delete = await proxies_source_factory.create_async(status=ProxySourceStatusEnum.enabled)
    source_to_keep = await proxies_source_factory.create_async(status=ProxySourceStatusEnum.enabled)
    source_to_delete_id, source_to_keep_id = source_to_delete.id, source_to_keep.id

    orphaned_proxy = await proxy_factory.create_async(
        source_id=source_to_delete_id, latency=42, status=ProxyStatusEnum.enabled
    )
    kept_proxy = await proxy_factory.create_async(
        source_id=source_to_keep_id, latency=100, status=ProxyStatusEnum.enabled
    )
    orphaned_proxy_id, kept_proxy_id = orphaned_proxy.id, kept_proxy.id

    response = await rest_client.delete(f"/api/proxies/sources/{source_to_delete_id}")

    assert response.status_code == status.HTTP_204_NO_CONTENT, response.text

    sources_in_db = await get_proxies_sources_by_id(db_rollback_session)

    assert sorted(sources_in_db) == [source_to_keep_id]

    proxies_in_db = await get_proxies_by_id(db_rollback_session)

    assert sorted(proxies_in_db) == sorted([orphaned_proxy_id, kept_proxy_id])
    assert proxies_in_db[orphaned_proxy_id].source_id is None
    assert proxies_in_db[orphaned_proxy_id].latency == 42
    assert proxies_in_db[kept_proxy_id].source_id == source_to_keep_id


async def test_delete_proxies_source_is_idempotent(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    proxies_source_factory = await sqlalchemy_model_factory_maker(
        factory_cls=TelegramProxiesSourceFactory, session=db_rollback_session
    )

    existing_source = await proxies_source_factory.create_async(status=ProxySourceStatusEnum.enabled)
    existing_source_id = existing_source.id

    response = await rest_client.delete(f"/api/proxies/sources/{MISSING_PROXY_SOURCE_ID}")

    assert response.status_code == status.HTTP_204_NO_CONTENT, response.text

    sources_in_db = await get_proxies_sources_by_id(db_rollback_session)

    assert sorted(sources_in_db) == [existing_source_id]


async def test_delete_proxies_source_with_non_numeric_id(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
) -> None:

    response = await rest_client.delete("/api/proxies/sources/not-a-number")

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, response.text
