from collections.abc import Awaitable, Callable
from datetime import datetime

from httpx import URL, AsyncClient
from polyfactory.factories.sqlalchemy_factory import SQLAlchemyFactory
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.constants import MOSCOW_TZ
from app.core.proxies.constants import ProxyStatusEnum
from tests.integration.api.proxies.helpers import MISSING_PROXY_ID
from tests.support.factories.proxies import TelegramProxiesSourceFactory, TelegramProxyFactory


async def test_get_a_proxy(
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

    updated_at = datetime.now(tz=MOSCOW_TZ).replace(tzinfo=None)

    proxy = await proxy_factory.create_async(
        source_id=source_id, latency=42, status=ProxyStatusEnum.enabled, updated_at=updated_at
    )
    # Соседняя прокси нужна, чтобы эндпоинт отдавал именно запрошенную запись, а не первую попавшуюся.
    await proxy_factory.create_async(source_id=source_id, latency=1, status=ProxyStatusEnum.disabled)

    response = await rest_client.get(f"/api/proxies/{proxy.id}")

    assert response.status_code == status.HTTP_200_OK, response.text

    data = response.json()["payload"]["data"]

    assert data == {
        "id": proxy.id,
        "name": proxy.name,
        "url": URL("tg://proxy", params=URL(proxy.url).params),
        "source_name": source_name,
        "created_at": proxy.created_at.isoformat(),
        "updated_at": updated_at.isoformat(),
        "status": ProxyStatusEnum.enabled,
        "latency": 42,
    }


async def test_get_a_proxy_without_source(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    """Прокси без источника отдаётся с пустыми `source_id` / `source_name`, а не падает на связке."""
    proxy_factory = await sqlalchemy_model_factory_maker(factory_cls=TelegramProxyFactory, session=db_rollback_session)

    proxy = await proxy_factory.create_async(
        source_id=None, latency=None, status=ProxyStatusEnum.disabled, updated_at=None
    )

    response = await rest_client.get(f"/api/proxies/{proxy.id}")

    assert response.status_code == status.HTTP_200_OK, response.text

    data = response.json()["payload"]["data"]

    assert data == {
        "id": proxy.id,
        "name": proxy.name,
        "url": URL("tg://proxy", params=URL(proxy.url).params),
        "source_name": None,
        "created_at": proxy.created_at.isoformat(),
        "updated_at": None,
        "status": ProxyStatusEnum.disabled,
        "latency": None,
    }


async def test_get_a_proxy_not_found(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
) -> None:

    response = await rest_client.get(f"/api/proxies/{MISSING_PROXY_ID}")

    assert response.status_code == status.HTTP_404_NOT_FOUND, response.text

    assert response.json()["error"] == {
        "type": "ResourceNotFoundByID",
        "title": "Resource not found",
        "detail": f"Could not find proxy with {MISSING_PROXY_ID} as an identifier",
        "meta": {"message": None},
        "resource_type": "proxy",
        "resource_id": MISSING_PROXY_ID,
    }


async def test_get_a_proxy_with_non_numeric_id(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
) -> None:

    response = await rest_client.get("/api/proxies/not-a-number")

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, response.text
