from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Any

import pytest
from assertpy import assert_that
from httpx import AsyncClient
from polyfactory.factories.sqlalchemy_factory import SQLAlchemyFactory
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.constants import MOSCOW_TZ
from app.core.proxies.constants import ProxyStatusEnum
from tests.support.factories.proxies import TelegramProxyFactory


async def test_get_all_proxies_empty_list(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
) -> None:

    response = await rest_client.get("/api/proxies")
    assert response.status_code == status.HTTP_200_OK

    data = response.json()["payload"]["data"]
    counters = response.json()["payload"]["counters"]

    assert data == []
    assert counters == {"total": 0}


async def test_get_all_proxies(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    proxy_factory = await sqlalchemy_model_factory_maker(factory_cls=TelegramProxyFactory, session=db_rollback_session)

    proxies = await proxy_factory.create_batch_async(size=3, latency=42)

    response = await rest_client.get("/api/proxies")
    assert response.status_code == status.HTTP_200_OK

    proxy_1, proxy_2, proxy_3 = sorted(proxies, key=lambda x: (x.latency, x.id))

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
            "latency": proxy_1.latency,
        },
        {
            "id": proxy_2.id,
            "url": proxy_2.url,
            "created_at": proxy_2.created_at.isoformat(),
            "updated_at": None,
            "status": proxy_2.status,
            "latency": proxy_2.latency,
        },
        {
            "id": proxy_3.id,
            "url": proxy_3.url,
            "created_at": proxy_3.created_at.isoformat(),
            "updated_at": None,
            "status": proxy_3.status,
            "latency": proxy_3.latency,
        },
    ]


async def test_get_all_proxies_paginated(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    proxy_factory = await sqlalchemy_model_factory_maker(factory_cls=TelegramProxyFactory, session=db_rollback_session)

    proxies = await proxy_factory.create_batch_async(size=7, latency=42)

    response = await rest_client.get("/api/proxies", params={"limit": 3})
    assert response.status_code == status.HTTP_200_OK

    proxy_1, proxy_2, proxy_3, proxy_4, proxy_5, proxy_6, proxy_7 = sorted(proxies, key=lambda x: (x.latency, x.id))

    data = response.json()["payload"]["data"]
    counters = response.json()["payload"]["counters"]

    assert len(data) == 3
    assert counters["total"] == 7

    assert_that(data).extracting("id").is_equal_to([proxy_1.id, proxy_2.id, proxy_3.id])

    next_page = response.json()["payload"]["pagination"]["next_page"]
    previous_page = response.json()["payload"]["pagination"]["previous_page"]

    assert next_page is not None
    assert previous_page is None

    response = await rest_client.get(next_page)
    data = response.json()["payload"]["data"]
    assert len(data) == 3
    assert_that(data).extracting("id").is_equal_to([proxy_4.id, proxy_5.id, proxy_6.id])

    next_page = response.json()["payload"]["pagination"]["next_page"]
    previous_page = response.json()["payload"]["pagination"]["previous_page"]

    assert next_page is not None
    assert previous_page is not None

    response = await rest_client.get(next_page)
    data = response.json()["payload"]["data"]
    assert len(data) == 1
    assert_that(data).extracting("id").is_equal_to([proxy_7.id])

    next_page = response.json()["payload"]["pagination"]["next_page"]
    previous_page = response.json()["payload"]["pagination"]["previous_page"]

    assert next_page is None
    assert previous_page is not None


@pytest.mark.parametrize(
    "params, proxy_id",
    [
        pytest.param({"proxy_status": ProxyStatusEnum.enabled}, 7, id="filter by enabled"),
        pytest.param(
            {
                "created_from": (datetime.now(tz=MOSCOW_TZ) - timedelta(days=2)).isoformat(),
                "created_to": (datetime.now(tz=MOSCOW_TZ)).isoformat(),
            },
            42,
            id="from created_from to created_to",
        ),
        pytest.param(
            {"created_to": (datetime.now(tz=MOSCOW_TZ) - timedelta(days=3)).isoformat()}, 1, id="only created_to"
        ),
    ],
)
async def test_get_all_proxies_with_filters(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
    params: dict[str, Any],
    proxy_id: int,
) -> None:
    proxy_factory = await sqlalchemy_model_factory_maker(factory_cls=TelegramProxyFactory, session=db_rollback_session)

    await proxy_factory.create_async(
        id=7, status="enabled", created_at=datetime.now(tz=MOSCOW_TZ).replace(tzinfo=None), latency=42
    )
    await proxy_factory.create_async(
        id=42,
        created_at=datetime.now(tz=MOSCOW_TZ).replace(tzinfo=None) - timedelta(days=1),
        status="disabled",
        latency=42,
    )
    await proxy_factory.create_async(
        id=1,
        created_at=datetime.now(tz=MOSCOW_TZ).replace(tzinfo=None) - timedelta(days=5),
        status="disabled",
        latency=42,
    )

    response = await rest_client.get(
        "/api/proxies",
        params=params,
    )
    assert response.status_code == status.HTTP_200_OK, response.text

    data = response.json()["payload"]["data"]
    counters = response.json()["payload"]["counters"]

    assert len(data) == 1
    assert counters["total"] == 3

    assert_that(data).extracting("id").is_equal_to([proxy_id])


async def test_get_all_proxies_with_best_latency_on_top(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    proxy_factory = await sqlalchemy_model_factory_maker(factory_cls=TelegramProxyFactory, session=db_rollback_session)

    proxy_1 = await proxy_factory.create_async(latency=543, updated_at=None)
    proxy_2 = await proxy_factory.create_async(latency=42, updated_at=datetime.now(tz=MOSCOW_TZ).replace(tzinfo=None))
    proxy_3 = await proxy_factory.create_async(latency=None)

    response = await rest_client.get("/api/proxies")
    assert response.status_code == status.HTTP_200_OK

    data = response.json()["payload"]["data"]
    counters = response.json()["payload"]["counters"]

    assert len(data) == 3
    assert counters["total"] == 3

    assert data == [
        {
            "id": proxy_2.id,
            "url": proxy_2.url,
            "created_at": proxy_2.created_at.isoformat(),
            "updated_at": proxy_2.updated_at.isoformat(),
            "status": proxy_2.status,
            "latency": proxy_2.latency,
        },
        {
            "id": proxy_1.id,
            "url": proxy_1.url,
            "created_at": proxy_1.created_at.isoformat(),
            "updated_at": None,
            "status": proxy_1.status,
            "latency": proxy_1.latency,
        },
        {
            "id": proxy_3.id,
            "url": proxy_3.url,
            "created_at": proxy_3.created_at.isoformat(),
            "updated_at": None,
            "status": proxy_3.status,
            "latency": None,
        },
    ]
