from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

import pytest
from httpx import AsyncClient
from polyfactory.factories.sqlalchemy_factory import SQLAlchemyFactory
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.constants import MOSCOW_TZ
from app.core.proxies_sources.constants import ProxySourceStatusEnum, ProxyVendorNameEnum
from tests.integration.api.proxies_sources.helpers import (
    MISSING_PROXY_SOURCE_ID,
    UPDATED_SOURCE_NAME,
    UPDATED_SOURCE_URL,
    get_proxies_sources_by_id,
)
from tests.support.factories.proxies_sources import TelegramProxiesSourceFactory


async def test_update_proxies_source_all_fields(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    proxies_source_factory = await sqlalchemy_model_factory_maker(
        factory_cls=TelegramProxiesSourceFactory, session=db_rollback_session
    )

    created_at = datetime.now(tz=MOSCOW_TZ).replace(tzinfo=None)

    source = await proxies_source_factory.create_async(
        status=ProxySourceStatusEnum.enabled,
        vendor=ProxyVendorNameEnum.github,
        created_at=created_at,
        updated_at=None,
        proxies_count=7,
        active_proxies_count=3,
    )
    source_id = source.id

    response = await rest_client.patch(
        f"/api/proxies/sources/{source_id}",
        json={
            "name": UPDATED_SOURCE_NAME,
            "url": UPDATED_SOURCE_URL,
            "status": ProxySourceStatusEnum.disabled,
            "vendor": ProxyVendorNameEnum.external,
        },
    )

    assert response.status_code == status.HTTP_204_NO_CONTENT, response.text
    assert response.content == b""

    sources_in_db = await get_proxies_sources_by_id(db_rollback_session)
    source_in_db = sources_in_db[source_id]

    assert source_in_db.name == UPDATED_SOURCE_NAME
    assert source_in_db.url == UPDATED_SOURCE_URL
    assert source_in_db.status == ProxySourceStatusEnum.disabled
    assert source_in_db.vendor == ProxyVendorNameEnum.external
    assert source_in_db.updated_at is not None
    # Счётчики и дата создания принадлежат серверу: обновление источника их не трогает.
    assert source_in_db.created_at == created_at
    assert source_in_db.proxies_count == 7
    assert source_in_db.active_proxies_count == 3


async def test_update_proxies_source_partially(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    """Поля, которых нет в теле, остаются прежними: `None` в сериализаторе означает "не меняем"."""
    proxies_source_factory = await sqlalchemy_model_factory_maker(
        factory_cls=TelegramProxiesSourceFactory, session=db_rollback_session
    )

    source = await proxies_source_factory.create_async(
        status=ProxySourceStatusEnum.enabled, vendor=ProxyVendorNameEnum.github, updated_at=None
    )
    source_id, source_name, source_url = source.id, source.name, source.url

    response = await rest_client.patch(
        f"/api/proxies/sources/{source_id}",
        json={"status": ProxySourceStatusEnum.disabled},
    )

    assert response.status_code == status.HTTP_204_NO_CONTENT, response.text

    sources_in_db = await get_proxies_sources_by_id(db_rollback_session)
    source_in_db = sources_in_db[source_id]

    assert source_in_db.status == ProxySourceStatusEnum.disabled
    assert source_in_db.updated_at is not None
    assert source_in_db.name == source_name
    assert source_in_db.url == source_url
    assert source_in_db.vendor == ProxyVendorNameEnum.github


async def test_update_proxies_source_without_any_changes(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    """Пустое тело не считается обновлением: `updated_at` остаётся нетронутым."""
    proxies_source_factory = await sqlalchemy_model_factory_maker(
        factory_cls=TelegramProxiesSourceFactory, session=db_rollback_session
    )

    source = await proxies_source_factory.create_async(status=ProxySourceStatusEnum.enabled, updated_at=None)
    source_id, source_name, source_url = source.id, source.name, source.url

    response = await rest_client.patch(f"/api/proxies/sources/{source_id}", json={})

    assert response.status_code == status.HTTP_204_NO_CONTENT, response.text

    sources_in_db = await get_proxies_sources_by_id(db_rollback_session)
    source_in_db = sources_in_db[source_id]

    assert source_in_db.updated_at is None
    assert source_in_db.name == source_name
    assert source_in_db.url == source_url
    assert source_in_db.status == ProxySourceStatusEnum.enabled


async def test_update_proxies_source_does_not_touch_other_sources(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    proxies_source_factory = await sqlalchemy_model_factory_maker(
        factory_cls=TelegramProxiesSourceFactory, session=db_rollback_session
    )

    target_source = await proxies_source_factory.create_async(status=ProxySourceStatusEnum.enabled, updated_at=None)
    another_source = await proxies_source_factory.create_async(status=ProxySourceStatusEnum.enabled, updated_at=None)
    target_source_id, another_source_id = target_source.id, another_source.id
    another_source_name = another_source.name

    response = await rest_client.patch(f"/api/proxies/sources/{target_source_id}", json={"name": UPDATED_SOURCE_NAME})

    assert response.status_code == status.HTTP_204_NO_CONTENT, response.text

    sources_in_db = await get_proxies_sources_by_id(db_rollback_session)

    assert sources_in_db[target_source_id].name == UPDATED_SOURCE_NAME
    assert sources_in_db[another_source_id].name == another_source_name
    assert sources_in_db[another_source_id].updated_at is None


async def test_update_proxies_source_not_found(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
) -> None:

    response = await rest_client.patch(
        f"/api/proxies/sources/{MISSING_PROXY_SOURCE_ID}", json={"name": UPDATED_SOURCE_NAME}
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND, response.text

    assert response.json()["error"] == {
        "type": "ResourceNotFoundByID",
        "title": "Resource not found",
        "detail": f"Could not find proxy_source with {MISSING_PROXY_SOURCE_ID} as an identifier",
        "meta": {"message": None},
        "resource_type": "proxy_source",
        "resource_id": MISSING_PROXY_SOURCE_ID,
    }

    assert await get_proxies_sources_by_id(db_rollback_session) == {}


@pytest.mark.parametrize(
    "body",
    [
        pytest.param({"status": "unknown"}, id="unknown status"),
        pytest.param({"vendor": "unknown"}, id="unknown vendor"),
        pytest.param({"name": ""}, id="empty name"),
        pytest.param({"url": "not-a-url"}, id="malformed url"),
    ],
)
async def test_update_proxies_source_with_invalid_body(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
    body: dict[str, Any],
) -> None:
    proxies_source_factory = await sqlalchemy_model_factory_maker(
        factory_cls=TelegramProxiesSourceFactory, session=db_rollback_session
    )

    source = await proxies_source_factory.create_async(status=ProxySourceStatusEnum.enabled, updated_at=None)
    source_id, source_name, source_url = source.id, source.name, source.url

    response = await rest_client.patch(f"/api/proxies/sources/{source_id}", json=body)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, response.text

    sources_in_db = await get_proxies_sources_by_id(db_rollback_session)
    source_in_db = sources_in_db[source_id]

    assert source_in_db.name == source_name
    assert source_in_db.url == source_url
    assert source_in_db.status == ProxySourceStatusEnum.enabled
    assert source_in_db.updated_at is None
