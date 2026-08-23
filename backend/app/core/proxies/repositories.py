from dataclasses import dataclass
from typing import Any

from sqlakeyset import Page
from sqlalchemy import ColumnElement, Integer, cast, delete, func, select, update, values
from sqlalchemy.exc import NoResultFound
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, load_only

from app.core.pagination import OffsetPagination, core_get_page
from app.core.proxies.constants import ProxyOrderByEnum, ProxyStatusEnum
from app.core.proxies.dto import ProxyBaseDTO, ProxyCountersDTO, ProxyFilterDTO
from app.core.proxies.exceptions import ProxyNotFoundException
from app.core.proxies.models import TelegramProxy
from app.core.proxies_sources.models import TelegramProxiesSource
from app.core.repositories import BaseDBRepository


@dataclass
class ProxyRepository(BaseDBRepository):

    async def get_proxy_by_id(
        self, proxy_id: int, with_source: bool = False, session: AsyncSession | None = None
    ) -> TelegramProxy:
        query = select(TelegramProxy).where(TelegramProxy.id == proxy_id)

        if with_source:
            # `TelegramProxy.source` объявлен с `lazy="raise"`, поэтому связку нужно тянуть явно.
            query = query.options(joinedload(TelegramProxy.source).options(load_only(TelegramProxiesSource.name)))

        try:
            return await self.get_single_result(query=query, session=session, as_scalar=True)
        except NoResultFound as exc:
            raise ProxyNotFoundException(proxy_id=proxy_id) from exc

    async def get_all_proxies(self, session: AsyncSession | None = None) -> list[TelegramProxy]:
        query = select(TelegramProxy).options(joinedload(TelegramProxy.source))

        async with self.session_wrap(session) as wrapped_session:
            return await self.get_multiple_results(query=query, session=wrapped_session, as_scalars=True)

    async def get_proxies_urls(
        self, status: ProxyStatusEnum | None = None, session: AsyncSession | None = None
    ) -> list[str]:
        query = select(TelegramProxy.url).order_by(TelegramProxy.latency, TelegramProxy.id)

        if status:
            query = query.where(TelegramProxy.status == status)

        async with self.session_wrap(session) as wrapped_session:
            return await self.get_multiple_results(query=query, session=wrapped_session, as_scalars=True)

    async def get_paginated_proxies(
        self,
        filters: ProxyFilterDTO,
        pagination: OffsetPagination,
        order_by: ProxyOrderByEnum,
        session: AsyncSession | None = None,
    ) -> tuple[Page[list[TelegramProxy]], ProxyCountersDTO]:

        order_by_clause: dict[ProxyOrderByEnum, ColumnElement[Any]] = {
            ProxyOrderByEnum.created_at: TelegramProxy.created_at.asc(),
            ProxyOrderByEnum.created_at_desc: TelegramProxy.created_at.desc(),
            ProxyOrderByEnum.latency: TelegramProxy.latency.asc(),
            ProxyOrderByEnum.latency_desc: TelegramProxy.latency.desc(),
        }

        query = (
            select(TelegramProxy)
            .options(joinedload(TelegramProxy.source).options(load_only(TelegramProxiesSource.name)))
            .order_by(order_by_clause[order_by], TelegramProxy.id)
        )

        total_count_query = select(func.count(TelegramProxy.id))
        active_count_query = total_count_query.where(TelegramProxy.status == ProxyStatusEnum.enabled)

        if filters.created_from:
            query = query.where(TelegramProxy.created_at >= filters.created_from)

        if filters.created_to:
            query = query.where(TelegramProxy.created_at <= filters.created_to)

        if filters.status:
            query = query.where(TelegramProxy.status == filters.status)

        async with self.session_wrap(session) as wrapped_session:
            proxies_page = await core_get_page(
                selectable=query, session=wrapped_session, pagination=pagination, as_model=True
            )
            total_count_result = await wrapped_session.execute(total_count_query)
            active_count_result = await wrapped_session.execute(active_count_query)

        return (
            proxies_page,
            ProxyCountersDTO(total=total_count_result.scalar_one(), active=active_count_result.scalar_one()),
        )

    async def save_proxies(
        self, proxies_dto: list[ProxyBaseDTO], session: AsyncSession | None = None
    ) -> list[TelegramProxy]:

        proxies = [
            TelegramProxy(
                url=str(proxy.url),
                name=proxy.name,
                source_id=proxy.source_id,
                created_at=func.now(),
                status=proxy.status,
                latency=proxy.latency,
            )
            for proxy in proxies_dto
        ]

        async with self.session_wrap(session) as wrapped_session:
            wrapped_session.add_all(proxies)
            await wrapped_session.flush()
        return proxies

    async def delete_proxies(self, proxy_ids: set[int] | None = None, session: AsyncSession | None = None) -> None:
        """Удаляет прокси с переданными id, а без фильтра — все прокси разом."""
        query = delete(TelegramProxy)

        if proxy_ids is not None:
            query = query.where(TelegramProxy.id.in_(proxy_ids))

        async with self.session_wrap(session) as wrapped_session:
            await wrapped_session.execute(query)

    async def update_proxy(
        self,
        proxy: TelegramProxy,
        latency: int | None = None,
        status: ProxyStatusEnum | None = None,
        session: AsyncSession | None = None,
    ) -> TelegramProxy:
        if not latency and not status:
            return proxy

        if latency:
            proxy.latency = latency
        if status:
            proxy.status = status
        proxy.updated_at = func.now()

        async with self.session_wrap(session) as wrapped_session:
            await wrapped_session.flush()
            await wrapped_session.refresh(proxy)
            return proxy

    async def update_proxies(
        self, proxies_dto: list[ProxyBaseDTO], session: AsyncSession | None = None
    ) -> list[TelegramProxy]:

        new_values = values(
            TelegramProxy.name,
            TelegramProxy.latency,
            TelegramProxy.status,
            name="new_proxies_values",
        ).data([(proxy.name, proxy.latency, proxy.status.value) for proxy in proxies_dto])

        query = (
            update(TelegramProxy)
            .where(TelegramProxy.name == new_values.c.name)
            .values(
                latency=cast(new_values.c.latency, Integer),
                status=new_values.c.status,
                updated_at=func.now(),
            )
            .returning(TelegramProxy)
            .execution_options(synchronize_session=False)
        )

        async with self.session_wrap(session) as wrapped_session:
            result = await wrapped_session.execute(query)
            return list(result.scalars().all())

    async def delete_proxy_by_id(self, proxy_id: int, session: AsyncSession | None = None) -> int | None:
        """
        Удаляет прокси по id и отдаёт `source_id` удалённой записи, чтобы пересчитать счётчики источника.

        Возвращает `None`, если прокси не было (удаление идемпотентно) либо она была без источника.
        """
        query = (
            delete(TelegramProxy)
            .where(TelegramProxy.id == proxy_id)
            .returning(TelegramProxy.source_id)
            .execution_options(synchronize_session=False)
        )

        async with self.session_wrap(session) as wrapped_session:
            result = await wrapped_session.execute(query)
            return result.scalars().first()
