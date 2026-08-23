from dataclasses import dataclass
from typing import Any

from httpx import URL
from sqlakeyset import Page
from sqlalchemy import ColumnElement, Integer, cast, delete, func, select, update, values
from sqlalchemy.exc import NoResultFound
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.pagination import OffsetPagination, core_get_page
from app.core.proxies.constants import ProxyOrderByEnum, ProxySourceStatusEnum, ProxyStatusEnum
from app.core.proxies.dto import ProxyBaseDTO, ProxyCountersDTO, ProxyFilterDTO, ProxySourceDTO
from app.core.proxies.exceptions import ProxyNotFoundException
from app.core.proxies.models import TelegramProxiesSource, TelegramProxy
from app.core.repositories import BaseDBRepository
from app.core.types import Missing


@dataclass
class ProxyRepository(BaseDBRepository):

    async def get_proxy_by_id(self, proxy_id: int, session: AsyncSession | None = None) -> TelegramProxy:
        query = select(TelegramProxy).where(TelegramProxy.id == proxy_id)

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

        query = select(TelegramProxy).order_by(order_by_clause[order_by], TelegramProxy.id)

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

    async def delete_all_proxies(self, session: AsyncSession | None = None) -> None:
        query = delete(TelegramProxy)

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

    async def delete_proxy_by_id(self, proxy_id: int, session: AsyncSession | None = None) -> None:
        query = delete(TelegramProxy).where(TelegramProxy.id == proxy_id)

        async with self.session_wrap(session) as wrapped_session:
            await wrapped_session.execute(query)

    async def get_all_proxies_sources(
        self, status: ProxySourceStatusEnum | None = None, session: AsyncSession | None = None
    ) -> list[ProxySourceDTO]:
        query = select(TelegramProxiesSource)

        if status:
            query = query.where(TelegramProxiesSource.status == status)

        result = await self.get_multiple_results(query=query, session=session, as_scalars=True)

        return [
            ProxySourceDTO(
                id=source.id,
                name=source.name,
                url=URL(source.url),
                status=source.status,
                vendor=source.vendor,
                created_at=source.created_at,
                updated_at=source.updated_at,
                proxies_count=source.proxies_count,
            )
            for source in result
        ]

    async def add_proxies_source(self, proxy_source_dto: ProxySourceDTO, session: AsyncSession | None = None) -> None:

        kwargs = {}
        if proxy_source_dto.id is not Missing:
            kwargs["id"] = proxy_source_dto.id

        proxy_source = TelegramProxiesSource(
            name=proxy_source_dto.name,
            url=str(proxy_source_dto.url),
            status=proxy_source_dto.status,
            vendor=proxy_source_dto.vendor,
            proxies_count=proxy_source_dto.proxies_count,
            created_at=proxy_source_dto.created_at if proxy_source_dto.created_at else func.now(),
            **kwargs,
        )

        async with self.session_wrap(session) as wrapped_session:
            wrapped_session.add(proxy_source)

    async def update_proxies_source(
        self, proxy_source_dto: ProxySourceDTO, session: AsyncSession | None = None
    ) -> None:

        if proxy_source_dto.id is not Missing:
            return

        kwargs = {}
        if proxy_source_dto.id is not Missing:
            kwargs["created_at"] = proxy_source_dto.created_at

        proxy_source = TelegramProxiesSource(
            id=proxy_source_dto.id,
            name=proxy_source_dto.name,
            url=str(proxy_source_dto.url),
            status=proxy_source_dto.status,
            vendor=proxy_source_dto.vendor,
            proxies_count=proxy_source_dto.proxies_count,
            updated_at=proxy_source_dto.updated_at if proxy_source_dto.updated_at else func.now(),
            **kwargs,
        )

        async with self.session_wrap(session) as wrapped_session:
            await wrapped_session.refresh(proxy_source)

    async def delete_proxies_source_by_id(self, proxy_source_id: int, session: AsyncSession | None = None) -> None:

        query = delete(TelegramProxiesSource).where(TelegramProxiesSource.id == proxy_source_id)

        async with self.session_wrap(session) as wrapped_session:
            await wrapped_session.execute(query)
