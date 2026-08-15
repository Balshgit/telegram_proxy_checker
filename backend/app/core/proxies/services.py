from dataclasses import dataclass

from sqlakeyset import Page

from app.core.pagination import OffsetPagination
from app.core.proxies.dto import ProxyFilterDTO
from app.core.proxies.models import TelegramProxy
from app.core.proxies.repositories import ProxyRepository
from app.infra.gateways.github_gateway import GithubGateway


@dataclass
class ProxyService:
    repository: ProxyRepository
    github_gateway: GithubGateway

    async def get_all_proxies(
        self, filters: ProxyFilterDTO, pagination: OffsetPagination
    ) -> tuple[Page[list[TelegramProxy]], int]:
        return await self.repository.get_paginated_proxies(filters=filters, pagination=pagination)

    async def save_proxies(self) -> list[TelegramProxy]:
        pinged_proxies = await self.github_gateway.ping_proxies()
        return await self.repository.save_proxies(pinged_proxies)

    async def delete_all_proxies(self) -> None:
        await self.repository.delete_all_proxies()
