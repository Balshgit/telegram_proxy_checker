from dataclasses import dataclass

from httpx import URL
from sqlakeyset import Page

from app.core.pagination import OffsetPagination
from app.core.proxies.constants import TELEGRAM_PROXY_APP_HOST, TELEGRAM_PROXY_APP_SCHEME
from app.core.proxies.dto import ProxyDTO, ProxyFilterDTO
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
        proxies = [
            ProxyDTO(
                url=URL(scheme=TELEGRAM_PROXY_APP_SCHEME, host=TELEGRAM_PROXY_APP_HOST, params=proxy.url.params),
                latency=proxy.latency,
                status=proxy.status,
            )
            for proxy in pinged_proxies
        ]

        return await self.repository.save_proxies(proxies)

    async def delete_all_proxies(self) -> None:
        await self.repository.delete_all_proxies()
