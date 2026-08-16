from collections.abc import Awaitable, Callable

from httpx import URL, AsyncClient
from polyfactory.factories.sqlalchemy_factory import SQLAlchemyFactory
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.proxies.constants import ProxyStatusEnum
from app.core.proxies.models import TelegramProxy
from tests.integration.api.proxies.helpers import MISSING_PROXY_ID, mocked_get_host_latency
from tests.support.factories.proxies import TelegramProxyFactory


async def test_update_a_proxy_status(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    proxy_factory = await sqlalchemy_model_factory_maker(factory_cls=TelegramProxyFactory, session=db_rollback_session)

    proxy = await proxy_factory.create_async(status=ProxyStatusEnum.disabled, latency=100, updated_at=None)
    proxy_id, proxy_name, proxy_url = proxy.id, proxy.name, proxy.url

    response = await rest_client.patch(f"/api/proxies/{proxy_id}", json={"status": ProxyStatusEnum.enabled})

    assert response.status_code == status.HTTP_200_OK, response.text

    updated_proxy = (
        await db_rollback_session.execute(select(TelegramProxy).where(TelegramProxy.id == proxy_id))
    ).scalar_one()

    assert updated_proxy.status == ProxyStatusEnum.enabled
    assert updated_proxy.latency == 100
    assert updated_proxy.updated_at is not None

    data = response.json()["payload"]["data"]

    assert data == {
        "id": proxy_id,
        "name": proxy_name,
        "url": URL("tg://proxy", params=URL(proxy_url).params),
        "created_at": updated_proxy.created_at.isoformat(),
        "updated_at": updated_proxy.updated_at.isoformat(),
        "status": ProxyStatusEnum.enabled,
        "latency": 100,
    }


async def test_update_a_proxy_latency(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    proxy_factory = await sqlalchemy_model_factory_maker(factory_cls=TelegramProxyFactory, session=db_rollback_session)

    proxy = await proxy_factory.create_async(status=ProxyStatusEnum.disabled, latency=None, updated_at=None)
    proxy_id, proxy_name, proxy_url = proxy.id, proxy.name, proxy.url

    async with mocked_get_host_latency(default_latency=777) as mocked_latency:
        response = await rest_client.patch(f"/api/proxies/{proxy_id}", json={"is_latency_update": True})

    assert response.status_code == status.HTTP_200_OK, response.text

    mocked_latency.assert_awaited_once_with(proxy_url)

    updated_proxy = (
        await db_rollback_session.execute(select(TelegramProxy).where(TelegramProxy.id == proxy_id))
    ).scalar_one()

    assert updated_proxy.latency == 777
    assert updated_proxy.status == ProxyStatusEnum.enabled
    assert updated_proxy.updated_at is not None

    data = response.json()["payload"]["data"]

    assert data == {
        "id": proxy_id,
        "name": proxy_name,
        "url": URL("tg://proxy", params=URL(proxy_url).params),
        "created_at": updated_proxy.created_at.isoformat(),
        "updated_at": updated_proxy.updated_at.isoformat(),
        "status": ProxyStatusEnum.enabled,
        "latency": 777,
    }


async def test_update_a_proxy_latency_when_proxy_is_unreachable(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    proxy_factory = await sqlalchemy_model_factory_maker(factory_cls=TelegramProxyFactory, session=db_rollback_session)

    proxy = await proxy_factory.create_async(status=ProxyStatusEnum.enabled, latency=100, updated_at=None)
    proxy_id, proxy_url = proxy.id, proxy.url

    async with mocked_get_host_latency(default_latency=None) as mocked_latency:
        response = await rest_client.patch(f"/api/proxies/{proxy_id}", json={"is_latency_update": True})

    assert response.status_code == status.HTTP_200_OK, response.text

    mocked_latency.assert_awaited_once_with(proxy_url)

    updated_proxy = (
        await db_rollback_session.execute(select(TelegramProxy).where(TelegramProxy.id == proxy_id))
    ).scalar_one()

    assert updated_proxy.status == ProxyStatusEnum.disabled
    assert updated_proxy.updated_at is not None
    # ProxyRepository.update_proxy присваивает latency только под `if latency`,
    # поэтому у недоступной прокси (latency=None) в базе остаётся прежнее значение.
    assert updated_proxy.latency == 100

    data = response.json()["payload"]["data"]

    assert data["status"] == ProxyStatusEnum.disabled
    assert data["latency"] == 100


async def test_update_a_proxy_without_any_changes(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    proxy_factory = await sqlalchemy_model_factory_maker(factory_cls=TelegramProxyFactory, session=db_rollback_session)

    proxy = await proxy_factory.create_async(status=ProxyStatusEnum.disabled, latency=100, updated_at=None)
    proxy_id = proxy.id

    response = await rest_client.patch(f"/api/proxies/{proxy_id}", json={})

    assert response.status_code == status.HTTP_200_OK, response.text

    updated_proxy = (
        await db_rollback_session.execute(select(TelegramProxy).where(TelegramProxy.id == proxy_id))
    ).scalar_one()

    assert updated_proxy.status == ProxyStatusEnum.disabled
    assert updated_proxy.latency == 100
    assert updated_proxy.updated_at is None

    data = response.json()["payload"]["data"]

    assert data["status"] == ProxyStatusEnum.disabled
    assert data["latency"] == 100
    assert data["updated_at"] is None


async def test_update_a_proxy_not_found(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
) -> None:

    response = await rest_client.patch(f"/api/proxies/{MISSING_PROXY_ID}", json={"status": ProxyStatusEnum.enabled})

    assert response.status_code == status.HTTP_404_NOT_FOUND, response.text

    assert response.json()["error"] == {
        "type": "ResourceNotFoundByID",
        "title": "Resource not found",
        "detail": f"Could not find proxy with {MISSING_PROXY_ID} as an identifier",
        "meta": {"message": None},
        "resource_type": "proxy",
        "resource_id": MISSING_PROXY_ID,
    }

    proxies_in_db = (await db_rollback_session.execute(select(TelegramProxy))).scalars().all()

    assert proxies_in_db == []


async def test_update_a_proxy_with_unknown_status(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    proxy_factory = await sqlalchemy_model_factory_maker(factory_cls=TelegramProxyFactory, session=db_rollback_session)

    proxy = await proxy_factory.create_async(status=ProxyStatusEnum.disabled, latency=100, updated_at=None)
    proxy_id = proxy.id

    response = await rest_client.patch(f"/api/proxies/{proxy_id}", json={"status": "unknown"})

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, response.text

    not_updated_proxy = (
        await db_rollback_session.execute(select(TelegramProxy).where(TelegramProxy.id == proxy_id))
    ).scalar_one()

    assert not_updated_proxy.status == ProxyStatusEnum.disabled
    assert not_updated_proxy.updated_at is None
