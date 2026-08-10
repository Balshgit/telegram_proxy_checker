from dataclasses import dataclass

from sqlakeyset import Page

from app.core.pagination import OffsetPagination
from app.core.proxies.dto import ProxyFilterDTO
from app.core.proxies.models import TelegramProxy
from app.core.proxies.repositories import ProxyRepository


@dataclass
class ProxyService:
    repository: ProxyRepository

    async def get_all_proxies(
        self, filters: ProxyFilterDTO, pagination: OffsetPagination
    ) -> tuple[Page[list[TelegramProxy]], int]:
        return await self.repository.get_paginated_proxies(filters=filters, pagination=pagination)
