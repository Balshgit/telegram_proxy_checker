from collections.abc import Awaitable, Callable

from polyfactory.factories.sqlalchemy_factory import SQLAlchemyFactory
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.proxies.constants import ProxyStatusEnum
from app.core.proxies.models import TelegramProxy
from app.core.proxies.tasks import cron_update_proxies_in_database_task
from app.di.dependency_injector import Container
from tests.integration.api.proxies.helpers import build_proxy_url, mocked_get_host_latency_by_server
from tests.integration.context import DummyContext
from tests.support.factories.proxies import TelegramProxyFactory

FIRST_PROXY_SERVER = "1.2.3.4"
SECOND_PROXY_SERVER = "5.6.7.8"


async def test_cron_task_updates_all_proxies(
    container: Container,
    db_rollback_session: AsyncSession,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    """Задача, которую дёргает планировщик по интервалу, обновляет прокси так же, как ручной эндпоинт."""
    proxy_factory = await sqlalchemy_model_factory_maker(factory_cls=TelegramProxyFactory, session=db_rollback_session)

    await proxy_factory.create_async(
        name=FIRST_PROXY_SERVER,
        url=build_proxy_url(server=FIRST_PROXY_SERVER),
        status=ProxyStatusEnum.disabled,
        latency=None,
        updated_at=None,
    )
    await proxy_factory.create_async(
        name=SECOND_PROXY_SERVER,
        url=build_proxy_url(server=SECOND_PROXY_SERVER),
        status=ProxyStatusEnum.enabled,
        latency=10,
        updated_at=None,
    )

    latency_by_server: dict[str, int | None] = {FIRST_PROXY_SERVER: 55, SECOND_PROXY_SERVER: None}

    async with mocked_get_host_latency_by_server(latency_by_server) as mocked_latency:
        await cron_update_proxies_in_database_task(context=DummyContext(container=container))

    mocked_latency.assert_awaited_once()
    assert sorted(url.params["server"] for url in mocked_latency.await_args.kwargs["urls"]) == sorted(latency_by_server)

    proxies_in_db = {
        proxy.name: proxy for proxy in (await db_rollback_session.execute(select(TelegramProxy))).scalars().all()
    }

    assert proxies_in_db[FIRST_PROXY_SERVER].latency == 55
    assert proxies_in_db[FIRST_PROXY_SERVER].status == ProxyStatusEnum.enabled
    assert proxies_in_db[FIRST_PROXY_SERVER].updated_at is not None

    assert proxies_in_db[SECOND_PROXY_SERVER].latency is None
    assert proxies_in_db[SECOND_PROXY_SERVER].status == ProxyStatusEnum.disabled
    assert proxies_in_db[SECOND_PROXY_SERVER].updated_at is not None


async def test_cron_task_on_empty_database(
    container: Container,
    db_rollback_session: AsyncSession,
) -> None:
    async with mocked_get_host_latency_by_server() as mocked_latency:
        await cron_update_proxies_in_database_task(context=DummyContext(container=container))

    mocked_latency.assert_awaited_once_with(urls=[])

    assert (await db_rollback_session.execute(select(TelegramProxy))).scalars().all() == []
