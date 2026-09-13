from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta

from httpx import URL, AsyncClient
from polyfactory.factories.sqlalchemy_factory import SQLAlchemyFactory
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.constants import MOSCOW_TZ
from app.core.proxies.constants import ProxyStatusEnum
from app.core.proxies.dto import ProxySourceToPingDTO
from app.core.proxies.models import TelegramProxy
from app.core.proxies_sources.constants import ProxySourceStatusEnum
from tests.integration.api.proxies.helpers import (
    MISSING_PROXY_ID,
    build_proxy_url,
    get_proxies_by_id,
    mocked_get_host_latency,
)
from tests.support.factories.proxies import TelegramProxyFactory
from tests.support.factories.proxies_sources import TelegramProxiesSourceFactory

PROXY_SERVER = "1.2.3.4"

#: Прежнее время активности прокси. Заведомо старое: весь тест идёт в одной транзакции,
#: а `func.now()` в постгресе — это её начало, поэтому «сдвинулось ли время вперёд»
#: можно проверить только относительно даты, выставленной руками.
WAS_ACTIVE_AT = datetime.now(tz=MOSCOW_TZ).replace(tzinfo=None) - timedelta(days=3)


async def test_update_a_proxy_status(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    proxy_factory = await sqlalchemy_model_factory_maker(factory_cls=TelegramProxyFactory, session=db_rollback_session)

    proxy = await proxy_factory.create_async(status=ProxyStatusEnum.disabled, latency=100, updated_at=None)
    proxy_id, proxy_name, proxy_url, source_id = proxy.id, proxy.name, proxy.url, proxy.source_id

    response = await rest_client.patch(f"/api/proxies/{proxy_id}", json={"status": ProxyStatusEnum.enabled})

    assert response.status_code == status.HTTP_202_ACCEPTED, response.text
    assert response.content == b"null"

    updated_proxy = (
        await db_rollback_session.execute(select(TelegramProxy).where(TelegramProxy.id == proxy_id))
    ).scalar_one()

    assert updated_proxy.status == ProxyStatusEnum.enabled
    assert updated_proxy.latency == 100
    assert updated_proxy.updated_at is not None
    assert updated_proxy.source_id == source_id
    # Обновление статуса не должно трогать неизменяемые поля прокси.
    assert updated_proxy.name == proxy_name
    assert updated_proxy.url == proxy_url


async def test_update_a_proxy_latency(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    proxy_factory = await sqlalchemy_model_factory_maker(factory_cls=TelegramProxyFactory, session=db_rollback_session)

    proxy = await proxy_factory.create_async(status=ProxyStatusEnum.disabled, latency=None, updated_at=None)
    proxy_id, proxy_name, proxy_url, source_id = proxy.id, proxy.name, proxy.url, proxy.source_id

    async with mocked_get_host_latency(default_latency=777) as mocked_latency:
        response = await rest_client.patch(f"/api/proxies/{proxy_id}", json={"is_latency_update": True})

    assert response.status_code == status.HTTP_202_ACCEPTED, response.text
    assert response.content == b"null"

    # На пинг уезжает пара (source_id, url), а не голый урл.
    mocked_latency.assert_awaited_once_with(ProxySourceToPingDTO(source_id=source_id, url=URL(proxy_url)))

    updated_proxy = (
        await db_rollback_session.execute(select(TelegramProxy).where(TelegramProxy.id == proxy_id))
    ).scalar_one()

    assert updated_proxy.latency == 777
    assert updated_proxy.status == ProxyStatusEnum.enabled
    assert updated_proxy.updated_at is not None
    assert updated_proxy.source_id == source_id
    assert updated_proxy.name == proxy_name
    assert updated_proxy.url == proxy_url


async def test_update_a_proxy_latency_sends_its_source_to_gateway(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    """Обновляем одну прокси — в гейтвей уходит источник именно этой прокси, а не соседней."""
    proxy_factory = await sqlalchemy_model_factory_maker(factory_cls=TelegramProxyFactory, session=db_rollback_session)
    proxies_source_factory = await sqlalchemy_model_factory_maker(
        factory_cls=TelegramProxiesSourceFactory, session=db_rollback_session
    )

    target_source = await proxies_source_factory.create_async(status=ProxySourceStatusEnum.enabled)
    another_source = await proxies_source_factory.create_async(status=ProxySourceStatusEnum.enabled)
    target_source_id, another_source_id = target_source.id, another_source.id

    proxy_url = build_proxy_url(server=PROXY_SERVER)

    proxy = await proxy_factory.create_async(
        name=PROXY_SERVER,
        url=proxy_url,
        source_id=target_source_id,
        status=ProxyStatusEnum.disabled,
        latency=None,
        updated_at=None,
    )
    another_proxy = await proxy_factory.create_async(
        source_id=another_source_id,
        status=ProxyStatusEnum.disabled,
        latency=None,
        updated_at=None,
    )
    proxy_id, another_proxy_id = proxy.id, another_proxy.id

    async with mocked_get_host_latency(default_latency=777) as mocked_latency:
        response = await rest_client.patch(f"/api/proxies/{proxy_id}", json={"is_latency_update": True})

    assert response.status_code == status.HTTP_202_ACCEPTED, response.text

    mocked_latency.assert_awaited_once_with(ProxySourceToPingDTO(source_id=target_source_id, url=URL(proxy_url)))

    proxies_in_db = {
        proxy_in_db.id: proxy_in_db
        for proxy_in_db in (await db_rollback_session.execute(select(TelegramProxy))).scalars().all()
    }

    assert proxies_in_db[proxy_id].source_id == target_source_id
    assert proxies_in_db[proxy_id].latency == 777
    assert proxies_in_db[proxy_id].updated_at is not None

    assert proxies_in_db[another_proxy_id].source_id == another_source_id
    assert proxies_in_db[another_proxy_id].latency is None
    assert proxies_in_db[another_proxy_id].updated_at is None


async def test_update_a_proxy_latency_without_source(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    """У прокси без источника в гейтвей уезжает `source_id=None`, и в базе он таким и остаётся."""
    proxy_factory = await sqlalchemy_model_factory_maker(factory_cls=TelegramProxyFactory, session=db_rollback_session)

    proxy_url = build_proxy_url(server=PROXY_SERVER)

    proxy = await proxy_factory.create_async(
        name=PROXY_SERVER,
        url=proxy_url,
        source_id=None,
        status=ProxyStatusEnum.disabled,
        latency=None,
        updated_at=None,
    )
    proxy_id = proxy.id

    async with mocked_get_host_latency(default_latency=321) as mocked_latency:
        response = await rest_client.patch(f"/api/proxies/{proxy_id}", json={"is_latency_update": True})

    assert response.status_code == status.HTTP_202_ACCEPTED, response.text

    mocked_latency.assert_awaited_once_with(ProxySourceToPingDTO(source_id=None, url=URL(proxy_url)))

    updated_proxy = (
        await db_rollback_session.execute(select(TelegramProxy).where(TelegramProxy.id == proxy_id))
    ).scalar_one()

    assert updated_proxy.source_id is None
    assert updated_proxy.latency == 321
    assert updated_proxy.status == ProxyStatusEnum.enabled


async def test_update_a_proxy_latency_when_proxy_is_unreachable(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    proxy_factory = await sqlalchemy_model_factory_maker(factory_cls=TelegramProxyFactory, session=db_rollback_session)

    proxy = await proxy_factory.create_async(status=ProxyStatusEnum.enabled, latency=100, updated_at=None)
    proxy_id, proxy_url, source_id = proxy.id, proxy.url, proxy.source_id

    async with mocked_get_host_latency(default_latency=None) as mocked_latency:
        response = await rest_client.patch(f"/api/proxies/{proxy_id}", json={"is_latency_update": True})

    assert response.status_code == status.HTTP_202_ACCEPTED, response.text
    assert response.content == b"null"

    mocked_latency.assert_awaited_once_with(ProxySourceToPingDTO(source_id=source_id, url=URL(proxy_url)))

    updated_proxy = (
        await db_rollback_session.execute(select(TelegramProxy).where(TelegramProxy.id == proxy_id))
    ).scalar_one()

    assert updated_proxy.status == ProxyStatusEnum.disabled
    assert updated_proxy.updated_at is not None
    # ProxyRepository.update_proxy присваивает latency только под `if latency`,
    # поэтому у недоступной прокси (latency=None) в базе остаётся прежнее значение.
    assert updated_proxy.latency == 100
    assert updated_proxy.source_id == source_id


async def test_update_a_proxy_without_any_changes(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    proxy_factory = await sqlalchemy_model_factory_maker(factory_cls=TelegramProxyFactory, session=db_rollback_session)

    proxy = await proxy_factory.create_async(
        status=ProxyStatusEnum.disabled, latency=100, updated_at=None, last_active_at=WAS_ACTIVE_AT
    )
    proxy_id, source_id = proxy.id, proxy.source_id

    response = await rest_client.patch(f"/api/proxies/{proxy_id}", json={})

    assert response.status_code == status.HTTP_202_ACCEPTED, response.text
    assert response.content == b"null"

    updated_proxy = (
        await db_rollback_session.execute(select(TelegramProxy).where(TelegramProxy.id == proxy_id))
    ).scalar_one()

    assert updated_proxy.status == ProxyStatusEnum.disabled
    assert updated_proxy.latency == 100
    assert updated_proxy.updated_at is None
    assert updated_proxy.last_active_at == WAS_ACTIVE_AT
    assert updated_proxy.source_id == source_id


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
    proxy_id, source_id = proxy.id, proxy.source_id

    response = await rest_client.patch(f"/api/proxies/{proxy_id}", json={"status": "unknown"})

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, response.text

    not_updated_proxy = (
        await db_rollback_session.execute(select(TelegramProxy).where(TelegramProxy.id == proxy_id))
    ).scalar_one()

    assert not_updated_proxy.status == ProxyStatusEnum.disabled
    assert not_updated_proxy.updated_at is None
    assert not_updated_proxy.source_id == source_id


async def test_update_a_proxy_to_enabled_stamps_last_active_at(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    """
    Пометили прокси активной — база проставила время активности.

    Время сверяем с `updated_at`, а не с питоновским `datetime.now()`: оба поля получают
    `func.now()` в одном UPDATE, а постгрес вычисляет `now()` один раз на запрос. Так тест
    заодно ловит подмену источника времени на питоновский.
    """
    proxy_factory = await sqlalchemy_model_factory_maker(factory_cls=TelegramProxyFactory, session=db_rollback_session)

    proxy = await proxy_factory.create_async(
        status=ProxyStatusEnum.disabled, latency=100, updated_at=None, last_active_at=None
    )
    proxy_id = proxy.id

    response = await rest_client.patch(f"/api/proxies/{proxy_id}", json={"status": ProxyStatusEnum.enabled})

    assert response.status_code == status.HTTP_202_ACCEPTED, response.text

    updated_proxy = (await get_proxies_by_id(db_rollback_session))[proxy_id]

    assert updated_proxy.status == ProxyStatusEnum.enabled
    assert updated_proxy.last_active_at is not None
    assert updated_proxy.last_active_at == updated_proxy.updated_at


async def test_update_a_proxy_to_disabled_does_not_stamp_last_active_at(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    """Время активности проставляется только на активный статус, `updated_at` — на любой."""
    proxy_factory = await sqlalchemy_model_factory_maker(factory_cls=TelegramProxyFactory, session=db_rollback_session)

    proxy = await proxy_factory.create_async(
        status=ProxyStatusEnum.enabled, latency=100, updated_at=None, last_active_at=None
    )
    proxy_id = proxy.id

    response = await rest_client.patch(f"/api/proxies/{proxy_id}", json={"status": ProxyStatusEnum.disabled})

    assert response.status_code == status.HTTP_202_ACCEPTED, response.text

    updated_proxy = (await get_proxies_by_id(db_rollback_session))[proxy_id]

    assert updated_proxy.status == ProxyStatusEnum.disabled
    assert updated_proxy.updated_at is not None
    assert updated_proxy.last_active_at is None


async def test_update_a_proxy_to_disabled_keeps_previous_last_active_at(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    """Прокси отвалилась — прежнее время активности не затирается: это история, а не текущий статус."""
    proxy_factory = await sqlalchemy_model_factory_maker(factory_cls=TelegramProxyFactory, session=db_rollback_session)

    proxy = await proxy_factory.create_async(
        status=ProxyStatusEnum.enabled, latency=100, updated_at=None, last_active_at=WAS_ACTIVE_AT
    )
    proxy_id = proxy.id

    response = await rest_client.patch(f"/api/proxies/{proxy_id}", json={"status": ProxyStatusEnum.disabled})

    assert response.status_code == status.HTTP_202_ACCEPTED, response.text

    updated_proxy = (await get_proxies_by_id(db_rollback_session))[proxy_id]

    assert updated_proxy.status == ProxyStatusEnum.disabled
    assert updated_proxy.last_active_at == WAS_ACTIVE_AT


async def test_update_a_proxy_to_enabled_moves_last_active_at_forward(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    """Прокси и была активной — время активности всё равно сдвигается: она активна прямо сейчас."""
    proxy_factory = await sqlalchemy_model_factory_maker(factory_cls=TelegramProxyFactory, session=db_rollback_session)

    proxy = await proxy_factory.create_async(
        status=ProxyStatusEnum.enabled, latency=100, updated_at=None, last_active_at=WAS_ACTIVE_AT
    )
    proxy_id = proxy.id

    response = await rest_client.patch(f"/api/proxies/{proxy_id}", json={"status": ProxyStatusEnum.enabled})

    assert response.status_code == status.HTTP_202_ACCEPTED, response.text

    updated_proxy = (await get_proxies_by_id(db_rollback_session))[proxy_id]

    assert updated_proxy.last_active_at is not None
    assert updated_proxy.last_active_at > WAS_ACTIVE_AT


async def test_update_a_proxy_latency_stamps_last_active_at_when_proxy_answers(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    """Статус после перепинга выводится из ответа прокси, и активный статус тянет за собой время."""
    proxy_factory = await sqlalchemy_model_factory_maker(factory_cls=TelegramProxyFactory, session=db_rollback_session)

    proxy = await proxy_factory.create_async(
        status=ProxyStatusEnum.disabled, latency=None, updated_at=None, last_active_at=None
    )
    proxy_id = proxy.id

    async with mocked_get_host_latency(default_latency=777):
        response = await rest_client.patch(f"/api/proxies/{proxy_id}", json={"is_latency_update": True})

    assert response.status_code == status.HTTP_202_ACCEPTED, response.text

    updated_proxy = (await get_proxies_by_id(db_rollback_session))[proxy_id]

    assert updated_proxy.status == ProxyStatusEnum.enabled
    assert updated_proxy.last_active_at is not None
    assert updated_proxy.last_active_at == updated_proxy.updated_at


async def test_update_a_proxy_latency_keeps_last_active_at_when_proxy_is_unreachable(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    proxy_factory = await sqlalchemy_model_factory_maker(factory_cls=TelegramProxyFactory, session=db_rollback_session)

    proxy = await proxy_factory.create_async(
        status=ProxyStatusEnum.enabled, latency=100, updated_at=None, last_active_at=WAS_ACTIVE_AT
    )
    proxy_id = proxy.id

    async with mocked_get_host_latency(default_latency=None):
        response = await rest_client.patch(f"/api/proxies/{proxy_id}", json={"is_latency_update": True})

    assert response.status_code == status.HTTP_202_ACCEPTED, response.text

    updated_proxy = (await get_proxies_by_id(db_rollback_session))[proxy_id]

    assert updated_proxy.status == ProxyStatusEnum.disabled
    assert updated_proxy.last_active_at == WAS_ACTIVE_AT
