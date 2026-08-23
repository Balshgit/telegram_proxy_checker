from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from httpx import AsyncClient
from polyfactory.factories.sqlalchemy_factory import SQLAlchemyFactory
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.proxies_sources.constants import ProxySourceStatusEnum, ProxyVendorNameEnum
from tests.integration.api.proxies_sources.helpers import (
    NEW_SOURCE_NAME,
    NEW_SOURCE_URL,
    get_proxies_sources_by_id,
)
from tests.support.factories.proxies_sources import TelegramProxiesSourceFactory


async def test_add_proxies_source(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
) -> None:

    response = await rest_client.post(
        "/api/proxies/sources",
        json={
            "name": NEW_SOURCE_NAME,
            "url": NEW_SOURCE_URL,
            "status": ProxySourceStatusEnum.disabled,
            "vendor": ProxyVendorNameEnum.external,
        },
    )

    assert response.status_code == status.HTTP_201_CREATED, response.text

    sources_in_db = await get_proxies_sources_by_id(db_rollback_session)

    assert len(sources_in_db) == 1

    source_in_db = next(iter(sources_in_db.values()))

    assert source_in_db.name == NEW_SOURCE_NAME
    assert source_in_db.url == NEW_SOURCE_URL
    assert source_in_db.status == ProxySourceStatusEnum.disabled
    assert source_in_db.vendor == ProxyVendorNameEnum.external
    assert source_in_db.proxies_count == 0
    assert source_in_db.active_proxies_count == 0
    assert source_in_db.created_at is not None
    assert source_in_db.updated_at is None


async def test_add_proxies_source_with_default_status_and_vendor(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
) -> None:
    """Без `status` источник заводится включённым: его сразу опрашивает сервис."""

    response = await rest_client.post(
        "/api/proxies/sources",
        json={"name": NEW_SOURCE_NAME, "url": NEW_SOURCE_URL, "vendor": "external"},
    )

    assert response.status_code == status.HTTP_201_CREATED, response.text

    sources_in_db = await get_proxies_sources_by_id(db_rollback_session)

    assert len(sources_in_db) == 1

    source_in_db = next(iter(sources_in_db.values()))

    assert source_in_db.status == ProxySourceStatusEnum.enabled
    assert source_in_db.vendor == ProxyVendorNameEnum.external


async def test_add_proxies_source_keeps_existing_sources(
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
    existing_source_id, existing_source_url = existing_source.id, existing_source.url

    response = await rest_client.post(
        "/api/proxies/sources",
        json={"name": NEW_SOURCE_NAME, "url": NEW_SOURCE_URL, "vendor": "external"},
    )

    assert response.status_code == status.HTTP_201_CREATED, response.text

    sources_in_db = await get_proxies_sources_by_id(db_rollback_session)

    # Эндпоинт ничего не отдаёт в теле, поэтому новый источник ищем в базе по остатку.
    new_source_ids = set(sources_in_db) - {existing_source_id}

    assert len(new_source_ids) == 1

    new_source_id = next(iter(new_source_ids))

    assert sources_in_db[existing_source_id].url == existing_source_url
    assert sources_in_db[new_source_id].url == NEW_SOURCE_URL


@pytest.mark.parametrize(
    "body",
    [
        pytest.param({"url": NEW_SOURCE_URL, "vendor": "external"}, id="without name"),
        pytest.param({"name": NEW_SOURCE_NAME, "vendor": "external"}, id="without url"),
        pytest.param({"name": NEW_SOURCE_NAME, "url": NEW_SOURCE_URL}, id="without vendor"),
        pytest.param({"name": "", "url": NEW_SOURCE_URL, "vendor": "external"}, id="empty name"),
        pytest.param({"name": "a" * 201, "url": NEW_SOURCE_URL, "vendor": "external"}, id="too long name"),
        pytest.param({"name": NEW_SOURCE_NAME, "url": "not-a-url", "vendor": "external"}, id="malformed url"),
        pytest.param(
            {"name": NEW_SOURCE_NAME, "url": NEW_SOURCE_URL, "vendor": "external", "status": "unknown"},
            id="unknown status",
        ),
        pytest.param(
            {"name": NEW_SOURCE_NAME, "url": NEW_SOURCE_URL, "vendor": "unknown"},
            id="unknown vendor",
        ),
    ],
)
async def test_add_proxies_source_with_invalid_body(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
    body: dict[str, Any],
) -> None:

    response = await rest_client.post("/api/proxies/sources", json=body)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, response.text

    assert await get_proxies_sources_by_id(db_rollback_session) == {}
