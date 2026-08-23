from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta

import pytest
from assertpy import assert_that
from httpx import AsyncClient
from polyfactory.factories.sqlalchemy_factory import SQLAlchemyFactory
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.constants import MOSCOW_TZ
from app.core.proxies.constants import ProxySourceStatusEnum, ProxyVendorNameEnum
from tests.support.factories.proxies import TelegramProxiesSourceFactory


async def test_get_proxies_sources_empty_list(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
) -> None:

    response = await rest_client.get("/api/proxies/sources")

    assert response.status_code == status.HTTP_200_OK, response.text
    assert response.json()["payload"]["data"] == []


async def test_get_proxies_sources(
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
    updated_at = created_at + timedelta(hours=1)

    first_source = await proxies_source_factory.create_async(
        status=ProxySourceStatusEnum.enabled,
        vendor=ProxyVendorNameEnum.github,
        created_at=created_at,
        updated_at=None,
        proxies_count=10,
        active_proxies_count=4,
    )
    second_source = await proxies_source_factory.create_async(
        status=ProxySourceStatusEnum.disabled,
        vendor=ProxyVendorNameEnum.external,
        created_at=created_at,
        updated_at=updated_at,
        proxies_count=0,
        active_proxies_count=0,
    )

    response = await rest_client.get("/api/proxies/sources")

    assert response.status_code == status.HTTP_200_OK, response.text

    data = response.json()["payload"]["data"]

    assert data == [
        {
            "id": first_source.id,
            "name": first_source.name,
            "url": first_source.url,
            "status": ProxySourceStatusEnum.enabled,
            "vendor": ProxyVendorNameEnum.github,
            "created_at": created_at.isoformat(),
            "updated_at": None,
            "proxies_count": 10,
            "active_proxies_count": 4,
        },
        {
            "id": second_source.id,
            "name": second_source.name,
            "url": second_source.url,
            "status": ProxySourceStatusEnum.disabled,
            "vendor": ProxyVendorNameEnum.external,
            "created_at": created_at.isoformat(),
            "updated_at": updated_at.isoformat(),
            "proxies_count": 0,
            "active_proxies_count": 0,
        },
    ]


@pytest.mark.parametrize(
    "source_status",
    [
        pytest.param(ProxySourceStatusEnum.enabled, id="only enabled"),
        pytest.param(ProxySourceStatusEnum.disabled, id="only disabled"),
    ],
)
async def test_get_proxies_sources_filtered_by_status(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
    source_status: ProxySourceStatusEnum,
) -> None:
    proxies_source_factory = await sqlalchemy_model_factory_maker(
        factory_cls=TelegramProxiesSourceFactory, session=db_rollback_session
    )

    sources_by_status = {
        ProxySourceStatusEnum.enabled: await proxies_source_factory.create_async(status=ProxySourceStatusEnum.enabled),
        ProxySourceStatusEnum.disabled: await proxies_source_factory.create_async(
            status=ProxySourceStatusEnum.disabled
        ),
    }
    expected_id = sources_by_status[source_status].id

    response = await rest_client.get("/api/proxies/sources", params={"status": source_status})

    assert response.status_code == status.HTTP_200_OK, response.text

    data = response.json()["payload"]["data"]

    assert len(data) == 1
    assert_that(data).extracting("id").is_equal_to([expected_id])


async def test_get_proxies_sources_with_unknown_status(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
) -> None:

    response = await rest_client.get("/api/proxies/sources", params={"status": "unknown"})

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, response.text
