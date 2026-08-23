from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from httpx import AsyncClient
from polyfactory.factories.sqlalchemy_factory import SQLAlchemyFactory
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.proxies.constants import ProxySourceStatusEnum, ProxyVendorNameEnum
from tests.integration.api.proxies.helpers import get_proxies_sources_by_id
from tests.support.factories.proxies import TelegramProxiesSourceFactory

NEW_SOURCE_NAME = "my-collector"
NEW_SOURCE_URL = "https://raw.githubusercontent.com/owner/repo/main/proxies.txt"


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

    data = response.json()["payload"]["data"]

    assert data == {
        "id": source_in_db.id,
        "name": NEW_SOURCE_NAME,
        "url": NEW_SOURCE_URL,
        "status": ProxySourceStatusEnum.disabled,
        "vendor": ProxyVendorNameEnum.external,
        "created_at": source_in_db.created_at.isoformat(),
        "updated_at": None,
        "proxies_count": 0,
        "active_proxies_count": 0,
    }


async def test_add_proxies_source_with_default_status_and_vendor(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
) -> None:
    """Без `status` / `vendor` источник заводится включённым гитхабовским: его сразу опрашивает сервис."""

    response = await rest_client.post(
        "/api/proxies/sources",
        json={"name": NEW_SOURCE_NAME, "url": NEW_SOURCE_URL},
    )

    assert response.status_code == status.HTTP_201_CREATED, response.text

    sources_in_db = await get_proxies_sources_by_id(db_rollback_session)

    assert len(sources_in_db) == 1

    source_in_db = next(iter(sources_in_db.values()))

    assert source_in_db.status == ProxySourceStatusEnum.enabled
    assert source_in_db.vendor == ProxyVendorNameEnum.github


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
        json={"name": NEW_SOURCE_NAME, "url": NEW_SOURCE_URL},
    )

    assert response.status_code == status.HTTP_201_CREATED, response.text

    new_source_id = response.json()["payload"]["data"]["id"]

    sources_in_db = await get_proxies_sources_by_id(db_rollback_session)

    assert sorted(sources_in_db) == sorted([existing_source_id, new_source_id])
    assert sources_in_db[existing_source_id].url == existing_source_url
    assert sources_in_db[new_source_id].url == NEW_SOURCE_URL


@pytest.mark.parametrize(
    "body",
    [
        pytest.param({"url": NEW_SOURCE_URL}, id="without name"),
        pytest.param({"name": NEW_SOURCE_NAME}, id="without url"),
        pytest.param({"name": "", "url": NEW_SOURCE_URL}, id="empty name"),
        pytest.param({"name": "a" * 201, "url": NEW_SOURCE_URL}, id="too long name"),
        pytest.param({"name": NEW_SOURCE_NAME, "url": "not-a-url"}, id="malformed url"),
        pytest.param(
            {"name": NEW_SOURCE_NAME, "url": NEW_SOURCE_URL, "status": "unknown"},
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
