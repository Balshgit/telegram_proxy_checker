from dataclasses import dataclass

from sqlakeyset import Page
from sqlalchemy import delete, func, select
from sqlalchemy.exc import NoResultFound
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import OffsetPagination, core_get_page
from app.core.proxies.constants import ProxyStatusEnum
from app.core.proxies.dto import ProxyBaseDTO, ProxyCountersDTO, ProxyFilterDTO
from app.core.proxies.exceptions import ProxyNotFoundException
from app.core.proxies.models import TelegramProxy
from app.core.repositories import BaseDBRepository


@dataclass
class ProxyRepository(BaseDBRepository):

    async def get_proxy_by_id(self, proxy_id: int, session: AsyncSession | None = None) -> TelegramProxy:
        query = select(TelegramProxy).where(TelegramProxy.id == proxy_id)

        try:
            return await self.get_single_result(query=query, session=session, as_scalar=True)
        except NoResultFound as exc:
            raise ProxyNotFoundException(proxy_id=proxy_id) from exc

    async def get_all_proxies(self, session: AsyncSession | None = None) -> list[TelegramProxy]:
        query = select(TelegramProxy)

        async with self.session_wrap(session) as wrapped_session:
            return await self.get_multiple_results(query=query, session=wrapped_session)

    async def get_paginated_proxies(
        self,
        filters: ProxyFilterDTO,
        pagination: OffsetPagination,
        session: AsyncSession | None = None,
    ) -> tuple[Page[list[TelegramProxy]], ProxyCountersDTO]:
        query = select(TelegramProxy).order_by(TelegramProxy.latency, TelegramProxy.id)
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
        self, proxies_dto: tuple[ProxyBaseDTO], with_updated_at: bool = False, session: AsyncSession | None = None
    ) -> list[TelegramProxy]:

        updated_at = func.now() if with_updated_at else None

        proxies = [
            TelegramProxy(
                url=str(proxy.url),
                created_at=func.now(),
                status=proxy.status,
                latency=proxy.latency,
                updated_at=proxy.updated_at if proxy.updated_at else updated_at,
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
