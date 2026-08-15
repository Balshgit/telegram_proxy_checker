from dataclasses import dataclass

from httpx import URL
from sqlakeyset import Page

from app.core.concurrency import run_async
from app.core.pagination import OffsetPagination
from app.core.proxies.constants import SAVE_POSTGRES_CHUNK_SIZE, ProxyStatusEnum
from app.core.proxies.dto import ProxyBaseDTO, ProxyFilterDTO
from app.core.proxies.models import TelegramProxy
from app.core.proxies.repositories import ProxyRepository
from app.core.proxies.tasks import save_proxies_to_database_task
from app.infra.gateways.github_gateway import GithubGateway
from app.infra.taskiq.executor import TaskiqTasksExecutor


@dataclass
class ProxyService:
    repository: ProxyRepository
    github_gateway: GithubGateway
    taskiq_tasks_executor: TaskiqTasksExecutor

    async def get_all_proxies(
        self, filters: ProxyFilterDTO, pagination: OffsetPagination
    ) -> tuple[Page[list[TelegramProxy]], int]:
        return await self.repository.get_paginated_proxies(filters=filters, pagination=pagination)

    async def save_proxies(self) -> list[TelegramProxy]:
        urls_for_ping = await self.github_gateway.get_urls_for_ping()

        proxies_dtos = await self.get_host_latency_for_urls(urls=urls_for_ping[:SAVE_POSTGRES_CHUNK_SIZE])
        proxies = await self.repository.save_proxies(proxies_dto=proxies_dtos)

        await self.taskiq_tasks_executor.run(
            save_proxies_to_database_task,
            params={"urls": list(map(str, urls_for_ping[SAVE_POSTGRES_CHUNK_SIZE:]))},
        )
        return proxies

    async def update_proxy(
        self, proxy_id: int, is_latency_update: bool = False, status: ProxyStatusEnum | None = None
    ) -> TelegramProxy:

        async with self.repository.get_transactional_session() as session:
            proxy = await self.repository.get_proxy_by_id(proxy_id=proxy_id, session=session)
            if not is_latency_update and not status:
                return proxy

            latency = proxy.latency
            if is_latency_update:
                proxy_base_dto = await self.github_gateway.get_host_latency(proxy.url)
                status = ProxyStatusEnum.enabled if proxy_base_dto.latency is not None else ProxyStatusEnum.disabled
                latency = proxy_base_dto.latency

            await self.repository.update_proxy(proxy, latency=latency, status=status, session=session)
            return proxy

    async def get_host_latency_for_urls(self, urls: list[URL]) -> tuple[ProxyBaseDTO]:
        tasks = [self.github_gateway.get_host_latency(url) for url in urls]
        return await run_async(*tasks)

    async def delete_all_proxies(self) -> None:
        await self.repository.delete_all_proxies()
