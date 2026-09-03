from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Any

import pytest
from assertpy import assert_that
from httpx import URL, AsyncClient
from polyfactory.factories.sqlalchemy_factory import SQLAlchemyFactory
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.constants import MOSCOW_TZ
from app.core.proxies.constants import ProxyOrderByEnum, ProxyStatusEnum
from tests.support.factories.proxies import TelegramProxyFactory
from tests.support.factories.proxies_sources import TelegramProxiesSourceFactory

FAST_PROXY = "fast"
SLOW_PROXY = "slow"
UNREACHABLE_PROXY = "unreachable"


async def test_get_all_proxies_empty_list(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
) -> None:

    response = await rest_client.get("/api/proxies")
    assert response.status_code == status.HTTP_200_OK

    data = response.json()["payload"]["data"]
    counters = response.json()["payload"]["counters"]
    proxies_share = response.json()["payload"]["proxies_share"]

    assert data == []
    assert counters == {"total": 0, "active": 0}
    assert proxies_share == ""


async def test_get_all_proxies(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    proxy_factory = await sqlalchemy_model_factory_maker(factory_cls=TelegramProxyFactory, session=db_rollback_session)
    proxies_source_factory = await sqlalchemy_model_factory_maker(
        factory_cls=TelegramProxiesSourceFactory, session=db_rollback_session
    )

    source = await proxies_source_factory.create_async()
    source_id, source_name = source.id, source.name

    proxies = await proxy_factory.create_batch_async(size=3, latency=42, source_id=source_id)

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
            "name": proxy_1.name,
            "url": URL("tg://proxy", params=URL(proxy_1.url).params),
            "source_name": source_name,
            "created_at": proxy_1.created_at.isoformat(),
            "updated_at": None,
            "status": proxy_1.status,
            "latency": proxy_1.latency,
        },
        {
            "id": proxy_2.id,
            "name": proxy_2.name,
            "url": URL("tg://proxy", params=URL(proxy_2.url).params),
            "source_name": source_name,
            "created_at": proxy_2.created_at.isoformat(),
            "updated_at": None,
            "status": proxy_2.status,
            "latency": proxy_2.latency,
        },
        {
            "id": proxy_3.id,
            "name": proxy_3.name,
            "url": URL("tg://proxy", params=URL(proxy_3.url).params),
            "source_name": source_name,
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
    proxies_source_factory = await sqlalchemy_model_factory_maker(
        factory_cls=TelegramProxiesSourceFactory, session=db_rollback_session
    )

    source = await proxies_source_factory.create_async()
    source_id, source_name = source.id, source.name

    proxy_1 = await proxy_factory.create_async(latency=543, updated_at=None, source_id=source_id)
    proxy_2 = await proxy_factory.create_async(
        latency=42, updated_at=datetime.now(tz=MOSCOW_TZ).replace(tzinfo=None), source_id=source_id
    )
    proxy_3 = await proxy_factory.create_async(latency=None, source_id=source_id)

    active_proxy_count = len([proxy for proxy in [proxy_1, proxy_2, proxy_3] if proxy.status == "enabled"])

    response = await rest_client.get("/api/proxies")
    assert response.status_code == status.HTTP_200_OK

    data = response.json()["payload"]["data"]
    counters = response.json()["payload"]["counters"]

    assert len(data) == 3
    assert counters == {"total": 3, "active": active_proxy_count}

    assert data == [
        {
            "id": proxy_2.id,
            "name": proxy_2.name,
            "url": URL("tg://proxy", params=URL(proxy_2.url).params),
            "source_name": source_name,
            "created_at": proxy_2.created_at.isoformat(),
            "updated_at": proxy_2.updated_at.isoformat(),
            "status": proxy_2.status,
            "latency": proxy_2.latency,
        },
        {
            "id": proxy_1.id,
            "name": proxy_1.name,
            "url": URL("tg://proxy", params=URL(proxy_1.url).params),
            "source_name": source_name,
            "created_at": proxy_1.created_at.isoformat(),
            "updated_at": None,
            "status": proxy_1.status,
            "latency": proxy_1.latency,
        },
        {
            "id": proxy_3.id,
            "name": proxy_3.name,
            "url": URL("tg://proxy", params=URL(proxy_3.url).params),
            "source_name": source_name,
            "created_at": proxy_3.created_at.isoformat(),
            "updated_at": None,
            "status": proxy_3.status,
            "latency": None,
        },
    ]


async def test_get_proxies_share_for_all_proxies(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    proxy_factory = await sqlalchemy_model_factory_maker(factory_cls=TelegramProxyFactory, session=db_rollback_session)
    proxies_source_factory = await sqlalchemy_model_factory_maker(
        factory_cls=TelegramProxiesSourceFactory, session=db_rollback_session
    )

    source = await proxies_source_factory.create_async()

    proxy_1 = await proxy_factory.create_async(latency=543, updated_at=None, source_id=source.id)
    proxy_2 = await proxy_factory.create_async(
        latency=42, updated_at=datetime.now(tz=MOSCOW_TZ).replace(tzinfo=None), source_id=source.id
    )
    proxy_3 = await proxy_factory.create_async(latency=None, source_id=source.id)

    response = await rest_client.get("/api/proxies")
    assert response.status_code == status.HTTP_200_OK

    proxies_share = response.json()["payload"]["proxies_share"]

    assert proxies_share == "-----\n".join(str(p.tg_proxy_url) for p in (proxy_2, proxy_1, proxy_3))


@pytest.mark.parametrize(
    "params, expected_proxies_order",
    [
        pytest.param({}, [FAST_PROXY, SLOW_PROXY, UNREACHABLE_PROXY], id="latency asc is the default order"),
        pytest.param(
            {"order_by": ProxyOrderByEnum.latency},
            [FAST_PROXY, SLOW_PROXY, UNREACHABLE_PROXY],
            id="latency asc",
        ),
        pytest.param(
            {"order_by": ProxyOrderByEnum.latency_desc},
            [UNREACHABLE_PROXY, SLOW_PROXY, FAST_PROXY],
            id="latency desc",
        ),
        pytest.param(
            {"order_by": ProxyOrderByEnum.created_at},
            [SLOW_PROXY, UNREACHABLE_PROXY, FAST_PROXY],
            id="created_at asc",
        ),
        pytest.param(
            {"order_by": ProxyOrderByEnum.created_at_desc},
            [FAST_PROXY, UNREACHABLE_PROXY, SLOW_PROXY],
            id="created_at desc",
        ),
    ],
)
async def test_get_all_proxies_ordered(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
    params: dict[str, Any],
    expected_proxies_order: list[str],
) -> None:
    """
    Порядок по latency и по created_at специально задан разным, иначе сортировки не отличить друг от друга.

    Прокси без latency (`None`) проверяет дефолтное поведение постгреса:
    ASC отдаёт NULL последними, DESC — первыми.
    """
    proxy_factory = await sqlalchemy_model_factory_maker(factory_cls=TelegramProxyFactory, session=db_rollback_session)

    now = datetime.now(tz=MOSCOW_TZ).replace(tzinfo=None)

    proxies = {
        FAST_PROXY: await proxy_factory.create_async(latency=42, created_at=now),
        SLOW_PROXY: await proxy_factory.create_async(latency=543, created_at=now - timedelta(days=2)),
        UNREACHABLE_PROXY: await proxy_factory.create_async(latency=None, created_at=now - timedelta(days=1)),
    }
    expected_ids = [proxies[proxy_key].id for proxy_key in expected_proxies_order]

    response = await rest_client.get("/api/proxies", params=params)

    assert response.status_code == status.HTTP_200_OK, response.text

    data = response.json()["payload"]["data"]

    assert len(data) == 3
    assert_that(data).extracting("id").is_equal_to(expected_ids)


async def test_get_all_proxies_ordering_is_kept_on_the_next_page(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    """`order_by` должен уезжать в ссылку на следующую страницу, иначе выдача поедет между страницами."""
    proxy_factory = await sqlalchemy_model_factory_maker(factory_cls=TelegramProxyFactory, session=db_rollback_session)

    proxy_1 = await proxy_factory.create_async(latency=1)
    proxy_2 = await proxy_factory.create_async(latency=2)
    proxy_3 = await proxy_factory.create_async(latency=3)
    expected_ids = [proxy_3.id, proxy_2.id, proxy_1.id]

    response = await rest_client.get("/api/proxies", params={"limit": 2, "order_by": ProxyOrderByEnum.latency_desc})

    assert response.status_code == status.HTTP_200_OK, response.text

    data = response.json()["payload"]["data"]
    next_page = response.json()["payload"]["pagination"]["next_page"]

    assert_that(data).extracting("id").is_equal_to(expected_ids[:2])
    assert next_page is not None
    assert f"order_by={ProxyOrderByEnum.latency_desc.value}" in next_page

    response = await rest_client.get(next_page)

    assert response.status_code == status.HTTP_200_OK, response.text

    data = response.json()["payload"]["data"]

    assert_that(data).extracting("id").is_equal_to(expected_ids[2:])


async def test_get_all_proxies_with_unknown_order_by(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
) -> None:

    response = await rest_client.get("/api/proxies", params={"order_by": "unknown"})

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, response.text


async def test_get_raw_proxies_on_empty_database(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
) -> None:

    response = await rest_client.get("/api/proxies/raw")

    assert response.status_code == status.HTTP_200_OK
    assert response.headers["content-type"].startswith("text/plain")
    assert response.text == ""


async def test_get_raw_proxies_all(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    proxy_factory = await sqlalchemy_model_factory_maker(factory_cls=TelegramProxyFactory, session=db_rollback_session)

    proxy_1 = await proxy_factory.create_async(latency=42, status=ProxyStatusEnum.enabled)
    proxy_2 = await proxy_factory.create_async(latency=543, status=ProxyStatusEnum.disabled)
    proxy_3 = await proxy_factory.create_async(latency=None, status=ProxyStatusEnum.enabled)

    response = await rest_client.get("/api/proxies/raw")

    assert response.status_code == status.HTTP_200_OK, response.text
    assert response.headers["content-type"].startswith("text/plain")

    assert response.text == f"{proxy_1.url}\n{proxy_2.url}\n{proxy_3.url}"


async def test_get_raw_proxies_active_only(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    proxy_factory = await sqlalchemy_model_factory_maker(factory_cls=TelegramProxyFactory, session=db_rollback_session)

    active_proxy = await proxy_factory.create_async(latency=42, status=ProxyStatusEnum.enabled)
    await proxy_factory.create_async(latency=543, status=ProxyStatusEnum.disabled)

    response = await rest_client.get("/api/proxies/raw", params={"status": "enabled"})

    assert response.status_code == status.HTTP_200_OK, response.text
    assert response.text == f"{active_proxy.url}"


async def test_get_raw_proxies_with_unknown_filter(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
) -> None:

    response = await rest_client.get("/api/proxies/raw", params={"status": "unknown"})

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, response.text
