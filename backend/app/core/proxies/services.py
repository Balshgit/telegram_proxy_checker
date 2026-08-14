from dataclasses import dataclass

from httpx import QueryParams
from sqlakeyset import Page

from app.core.pagination import OffsetPagination
from app.core.proxies.dto import ProxyDTO, ProxyFilterDTO, ProxyServerDTO
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

    async def save_proxies(self) -> list[ProxyDTO]:
        proxies = await self.github_gateway.get_proxies_list()

        proxies_dtos = [ProxyDTO(url=str(proxy)) for proxy in proxies]

    @staticmethod
    def _get_params_from_proxy(params: QueryParams) -> ProxyServerDTO:
        return ProxyServerDTO(host=params.get("host"), port=params.get("port"))
