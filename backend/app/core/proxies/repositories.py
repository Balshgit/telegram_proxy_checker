from dataclasses import dataclass

from sqlakeyset import Page
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.concurrency import run_async
from app.core.pagination import OffsetPagination, core_get_page
from app.core.proxies.dto import ProxyFilterDTO
from app.core.proxies.models import TelegramProxy
from app.core.repositories import BaseDBRepository


@dataclass
class ProxyRepository(BaseDBRepository):

    async def get_paginated_proxies(
        self,
        filters: ProxyFilterDTO,
        pagination: OffsetPagination,
        session: AsyncSession | None = None,
    ) -> tuple[Page[list[TelegramProxy]], int]:
        query = (
            select(TelegramProxy).where(TelegramProxy.ping.is_not(None)).order_by(TelegramProxy.ping, TelegramProxy.id)
        )
        count_query = select(func.count(TelegramProxy.id)).where(TelegramProxy.ping.is_not(None))

        if filters.created_from:
            query = query.where(TelegramProxy.created_at >= filters.created_from)

        if filters.created_to:
            query = query.where(TelegramProxy.created_at <= filters.created_to)

        if filters.status:
            query = query.where(TelegramProxy.status == filters.status)

        async with self.session_wrap(session) as wrapped_session:
            proxies_page, total_count_result = await run_async(
                core_get_page(selectable=query, session=wrapped_session, pagination=pagination, as_model=True),
                wrapped_session.execute(count_query),
            )

        return proxies_page, total_count_result.scalar_one()
