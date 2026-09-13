from collections.abc import Awaitable, Callable

from httpx import AsyncClient
from polyfactory.factories.sqlalchemy_factory import SQLAlchemyFactory
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.proxies.constants import ProxyStatusEnum
from app.core.proxies_sources.constants import ProxySourceStatusEnum
from settings.config import AppTestSettings
from tests.integration.api.proxies.helpers import (
    fresh_moment,
    get_database_now,
    get_proxies_ids,
    get_source_by_id,
    stale_moment,
)
from tests.support.factories.proxies import TelegramProxyFactory
from tests.support.factories.proxies_sources import TelegramProxiesSourceFactory

CLEANUP_URL = "/api/proxies/stale"


async def test_delete_stale_proxies_removes_proxies_that_went_silent(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
    test_settings: AppTestSettings,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    """Прокси, чей `last_active_at` старше срока, уезжает из базы, а та, что выходила на связь недавно, остаётся."""
    proxy_factory = await sqlalchemy_model_factory_maker(factory_cls=TelegramProxyFactory, session=db_rollback_session)

    database_now = await get_database_now(db_rollback_session)
    stale_period = test_settings.PROXY_STALE_PERIOD

    silent_proxy = await proxy_factory.create_async(
        status=ProxyStatusEnum.disabled,
        created_at=stale_moment(database_now, stale_period),
        last_active_at=stale_moment(database_now, stale_period),
    )
    recently_active_proxy = await proxy_factory.create_async(
        status=ProxyStatusEnum.enabled,
        created_at=stale_moment(database_now, stale_period),
        last_active_at=fresh_moment(database_now, stale_period),
    )
    silent_proxy_id, recently_active_proxy_id = silent_proxy.id, recently_active_proxy.id

    response = await rest_client.delete(CLEANUP_URL)

    assert response.status_code == status.HTTP_202_ACCEPTED, response.text
    assert response.content == b"null"

    assert await get_proxies_ids(db_rollback_session) == {recently_active_proxy_id}
    assert silent_proxy_id not in await get_proxies_ids(db_rollback_session)


async def test_delete_stale_proxies_removes_never_active_proxies_by_created_at(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
    test_settings: AppTestSettings,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    """У прокси, которая ни разу не была активной, срок считается от даты создания."""
    proxy_factory = await sqlalchemy_model_factory_maker(factory_cls=TelegramProxyFactory, session=db_rollback_session)

    database_now = await get_database_now(db_rollback_session)
    stale_period = test_settings.PROXY_STALE_PERIOD

    old_never_active_proxy = await proxy_factory.create_async(
        status=ProxyStatusEnum.disabled,
        created_at=stale_moment(database_now, stale_period),
        last_active_at=None,
    )
    young_never_active_proxy = await proxy_factory.create_async(
        status=ProxyStatusEnum.disabled,
        created_at=fresh_moment(database_now, stale_period),
        last_active_at=None,
    )
    old_proxy_id, young_proxy_id = old_never_active_proxy.id, young_never_active_proxy.id

    response = await rest_client.delete(CLEANUP_URL)

    assert response.status_code == status.HTTP_202_ACCEPTED, response.text

    proxies_ids_after = await get_proxies_ids(db_rollback_session)

    assert proxies_ids_after == {young_proxy_id}
    assert old_proxy_id not in proxies_ids_after


async def test_delete_stale_proxies_keeps_old_proxy_that_is_still_active(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
    test_settings: AppTestSettings,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    """Давняя дата создания сама по себе не повод удалять: если прокси выходила на связь, она остаётся."""
    proxy_factory = await sqlalchemy_model_factory_maker(factory_cls=TelegramProxyFactory, session=db_rollback_session)

    database_now = await get_database_now(db_rollback_session)
    stale_period = test_settings.PROXY_STALE_PERIOD

    long_lived_proxy = await proxy_factory.create_async(
        status=ProxyStatusEnum.enabled,
        created_at=stale_moment(database_now, stale_period * 10),
        last_active_at=fresh_moment(database_now, stale_period),
    )
    long_lived_proxy_id = long_lived_proxy.id

    response = await rest_client.delete(CLEANUP_URL)

    assert response.status_code == status.HTTP_202_ACCEPTED, response.text

    assert await get_proxies_ids(db_rollback_session) == {long_lived_proxy_id}


async def test_delete_stale_proxies_removes_stale_proxy_without_source(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
    test_settings: AppTestSettings,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    """Прокси без источника удаляется наравне с остальными: `source_id` нужен только для пересчёта счётчиков."""
    proxy_factory = await sqlalchemy_model_factory_maker(factory_cls=TelegramProxyFactory, session=db_rollback_session)

    database_now = await get_database_now(db_rollback_session)
    stale_period = test_settings.PROXY_STALE_PERIOD

    await proxy_factory.create_async(
        source_id=None,
        status=ProxyStatusEnum.disabled,
        created_at=stale_moment(database_now, stale_period),
        last_active_at=None,
    )
    fresh_proxy = await proxy_factory.create_async(
        source_id=None,
        status=ProxyStatusEnum.enabled,
        created_at=fresh_moment(database_now, stale_period),
        last_active_at=fresh_moment(database_now, stale_period),
    )
    fresh_proxy_id = fresh_proxy.id

    response = await rest_client.delete(CLEANUP_URL)

    assert response.status_code == status.HTTP_202_ACCEPTED, response.text

    assert await get_proxies_ids(db_rollback_session) == {fresh_proxy_id}


async def test_delete_stale_proxies_recalculates_counters_of_affected_source(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
    test_settings: AppTestSettings,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    """После удаления счётчики источника показывают то, что реально осталось в базе."""
    proxy_factory = await sqlalchemy_model_factory_maker(factory_cls=TelegramProxyFactory, session=db_rollback_session)
    proxies_source_factory = await sqlalchemy_model_factory_maker(
        factory_cls=TelegramProxiesSourceFactory, session=db_rollback_session
    )

    database_now = await get_database_now(db_rollback_session)
    stale_period = test_settings.PROXY_STALE_PERIOD

    source = await proxies_source_factory.create_async(
        status=ProxySourceStatusEnum.enabled, proxies_count=3, active_proxies_count=2
    )
    source_id = source.id

    await proxy_factory.create_async(
        source_id=source_id,
        status=ProxyStatusEnum.enabled,
        created_at=stale_moment(database_now, stale_period),
        last_active_at=stale_moment(database_now, stale_period),
    )
    await proxy_factory.create_async(
        source_id=source_id,
        status=ProxyStatusEnum.enabled,
        created_at=fresh_moment(database_now, stale_period),
        last_active_at=fresh_moment(database_now, stale_period),
    )
    await proxy_factory.create_async(
        source_id=source_id,
        status=ProxyStatusEnum.disabled,
        created_at=fresh_moment(database_now, stale_period),
        last_active_at=None,
    )

    response = await rest_client.delete(CLEANUP_URL)

    assert response.status_code == status.HTTP_202_ACCEPTED, response.text

    assert len(await get_proxies_ids(db_rollback_session)) == 2

    source_after = await get_source_by_id(db_rollback_session, source_id)

    assert source_after.proxies_count == 2
    assert source_after.active_proxies_count == 1
    assert source_after.updated_at is not None


async def test_delete_stale_proxies_does_not_touch_untouched_source(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
    test_settings: AppTestSettings,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    """Пересчёт идёт точечно: источник, у которого ничего не удалили, остаётся со своими счётчиками."""
    proxy_factory = await sqlalchemy_model_factory_maker(factory_cls=TelegramProxyFactory, session=db_rollback_session)
    proxies_source_factory = await sqlalchemy_model_factory_maker(
        factory_cls=TelegramProxiesSourceFactory, session=db_rollback_session
    )

    database_now = await get_database_now(db_rollback_session)
    stale_period = test_settings.PROXY_STALE_PERIOD

    affected_source = await proxies_source_factory.create_async(
        status=ProxySourceStatusEnum.enabled, proxies_count=5, active_proxies_count=5
    )
    untouched_source = await proxies_source_factory.create_async(
        status=ProxySourceStatusEnum.enabled, proxies_count=42, active_proxies_count=7, updated_at=None
    )
    affected_source_id, untouched_source_id = affected_source.id, untouched_source.id

    await proxy_factory.create_async(
        source_id=affected_source_id,
        status=ProxyStatusEnum.enabled,
        created_at=stale_moment(database_now, stale_period),
        last_active_at=stale_moment(database_now, stale_period),
    )
    survivor = await proxy_factory.create_async(
        source_id=untouched_source_id,
        status=ProxyStatusEnum.enabled,
        created_at=fresh_moment(database_now, stale_period),
        last_active_at=fresh_moment(database_now, stale_period),
    )
    survivor_id = survivor.id

    response = await rest_client.delete(CLEANUP_URL)

    assert response.status_code == status.HTTP_202_ACCEPTED, response.text

    assert await get_proxies_ids(db_rollback_session) == {survivor_id}

    affected_source_after = await get_source_by_id(db_rollback_session, affected_source_id)
    untouched_source_after = await get_source_by_id(db_rollback_session, untouched_source_id)

    assert affected_source_after.proxies_count == 0
    assert affected_source_after.active_proxies_count == 0

    assert untouched_source_after.proxies_count == 42
    assert untouched_source_after.active_proxies_count == 7
    assert untouched_source_after.updated_at is None


async def test_delete_stale_proxies_when_nothing_is_stale(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
    test_settings: AppTestSettings,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    """Если протухших проксей нет, база остаётся нетронутой, а счётчики источника не пересчитываются."""
    proxy_factory = await sqlalchemy_model_factory_maker(factory_cls=TelegramProxyFactory, session=db_rollback_session)
    proxies_source_factory = await sqlalchemy_model_factory_maker(
        factory_cls=TelegramProxiesSourceFactory, session=db_rollback_session
    )

    database_now = await get_database_now(db_rollback_session)
    stale_period = test_settings.PROXY_STALE_PERIOD

    source = await proxies_source_factory.create_async(
        status=ProxySourceStatusEnum.enabled, proxies_count=42, active_proxies_count=7, updated_at=None
    )
    source_id = source.id

    fresh_proxy = await proxy_factory.create_async(
        source_id=source_id,
        status=ProxyStatusEnum.enabled,
        created_at=fresh_moment(database_now, stale_period),
        last_active_at=fresh_moment(database_now, stale_period),
    )
    never_active_proxy = await proxy_factory.create_async(
        source_id=source_id,
        status=ProxyStatusEnum.disabled,
        created_at=fresh_moment(database_now, stale_period),
        last_active_at=None,
    )
    fresh_proxy_id, never_active_proxy_id = fresh_proxy.id, never_active_proxy.id

    response = await rest_client.delete(CLEANUP_URL)

    assert response.status_code == status.HTTP_202_ACCEPTED, response.text
    assert response.content == b"null"

    assert await get_proxies_ids(db_rollback_session) == {fresh_proxy_id, never_active_proxy_id}

    source_after = await get_source_by_id(db_rollback_session, source_id)

    assert source_after.proxies_count == 42
    assert source_after.active_proxies_count == 7
    assert source_after.updated_at is None


async def test_delete_stale_proxies_on_empty_database(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
) -> None:

    response = await rest_client.delete(CLEANUP_URL)

    assert response.status_code == status.HTTP_202_ACCEPTED, response.text
    assert response.content == b"null"

    assert await get_proxies_ids(db_rollback_session) == set()


async def test_delete_stale_proxies_is_idempotent(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
    test_settings: AppTestSettings,
    sqlalchemy_model_factory_maker: Callable[
        [type[SQLAlchemyFactory], AsyncSession], Awaitable[type[SQLAlchemyFactory]]
    ],
) -> None:
    """Повторная очистка отвечает так же и больше ничего не удаляет."""
    proxy_factory = await sqlalchemy_model_factory_maker(factory_cls=TelegramProxyFactory, session=db_rollback_session)

    database_now = await get_database_now(db_rollback_session)
    stale_period = test_settings.PROXY_STALE_PERIOD

    await proxy_factory.create_async(
        status=ProxyStatusEnum.disabled,
        created_at=stale_moment(database_now, stale_period),
        last_active_at=None,
    )
    fresh_proxy = await proxy_factory.create_async(
        status=ProxyStatusEnum.enabled,
        created_at=fresh_moment(database_now, stale_period),
        last_active_at=fresh_moment(database_now, stale_period),
    )
    fresh_proxy_id = fresh_proxy.id

    first_response = await rest_client.delete(CLEANUP_URL)
    proxies_ids_after_first_call = await get_proxies_ids(db_rollback_session)
    second_response = await rest_client.delete(CLEANUP_URL)

    assert first_response.status_code == status.HTTP_202_ACCEPTED, first_response.text
    assert second_response.status_code == first_response.status_code, second_response.text
    assert second_response.content == first_response.content == b"null"

    assert proxies_ids_after_first_call == {fresh_proxy_id}
    assert await get_proxies_ids(db_rollback_session) == {fresh_proxy_id}


async def test_delete_stale_proxies_route_is_not_shadowed_by_a_proxy_route(
    rest_client: AsyncClient,
    db_rollback_session: AsyncSession,
) -> None:
    """`stale` не должен попадать в `/proxies/{proxy_id}`: иначе на нечисловой id прилетело бы 422."""

    response = await rest_client.delete(CLEANUP_URL)

    assert response.status_code != status.HTTP_422_UNPROCESSABLE_CONTENT, response.text
    assert response.status_code == status.HTTP_202_ACCEPTED, response.text
