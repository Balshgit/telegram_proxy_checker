from dataclasses import dataclass
from itertools import chain

from httpx import URL
from sqlakeyset import Page

from app.core.concurrency import run_async
from app.core.pagination import OffsetPagination
from app.core.proxies.constants import SAVE_POSTGRES_CHUNK_SIZE, ProxyOrderByEnum, ProxyStatusEnum
from app.core.proxies.dto import ProxyCountersDTO, ProxyFilterDTO
from app.core.proxies.exceptions import NoProxiesAddedException
from app.core.proxies.models import TelegramProxy
from app.core.proxies.repositories import ProxyRepository
from app.core.proxies.tasks import save_proxies_to_database_task, update_proxies_in_database_task
from app.infra.gateways.github_gateway import GithubGateway
from app.infra.taskiq.executor import TaskiqTasksExecutor


@dataclass
class ProxyService:
    repository: ProxyRepository
    github_gateway: GithubGateway
    taskiq_tasks_executor: TaskiqTasksExecutor

    async def get_all_proxies(
        self,
        filters: ProxyFilterDTO,
        pagination: OffsetPagination,
        order_by: ProxyOrderByEnum = ProxyOrderByEnum.latency,
    ) -> tuple[Page[list[TelegramProxy]], ProxyCountersDTO]:
        return await self.repository.get_paginated_proxies(filters=filters, pagination=pagination, order_by=order_by)

    async def get_raw_proxies_urls(self, status: ProxyStatusEnum | None) -> str:
        urls = await self.repository.get_proxies_urls(status=status)
        return "\n".join(url for url in urls)

    async def add_new_proxies(self) -> list[TelegramProxy]:
        proxy_sources = await self.repository.get_all_proxies_sources()

        coros = [self.github_gateway.get_urls_for_ping(proxy_source=str(source.url)) for source in proxy_sources]
        new_proxies_urls = chain(await run_async(*coros))

        existing_proxies = await self.repository.get_all_proxies()
        existing_proxies_urls = {URL(proxy.url) for proxy in existing_proxies}

        urls_for_ping = list(set(new_proxies_urls).difference(existing_proxies_urls))

        if not urls_for_ping:
            raise NoProxiesAddedException()

        proxies_dtos = await self.github_gateway.get_host_latency_for_urls(
            urls=urls_for_ping[:SAVE_POSTGRES_CHUNK_SIZE]
        )
        proxies = await self.repository.save_proxies(proxies_dto=proxies_dtos)

        if all_next_proxies := urls_for_ping[SAVE_POSTGRES_CHUNK_SIZE:]:
            await self.taskiq_tasks_executor.run(
                save_proxies_to_database_task,
                params={"urls": list(map(str, all_next_proxies))},
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

    async def delete_all_proxies(self) -> None:
        await self.repository.delete_all_proxies()

    async def update_all_proxies(self) -> None:
        existing_proxies = await self.repository.get_all_proxies()
        existing_proxies_urls = [URL(proxy.url) for proxy in existing_proxies]

        proxies_dtos = await self.github_gateway.get_host_latency_for_urls(
            urls=existing_proxies_urls[:SAVE_POSTGRES_CHUNK_SIZE]
        )

        if not proxies_dtos:
            return

        await self.repository.update_proxies(proxies_dtos)

        if all_next_existing_proxies := existing_proxies_urls[SAVE_POSTGRES_CHUNK_SIZE:]:
            await self.taskiq_tasks_executor.run(
                update_proxies_in_database_task,
                params={"urls": list(map(str, all_next_existing_proxies))},
            )

    async def delete_proxy_by_id(self, proxy_id: int) -> None:
        await self.repository.delete_proxy_by_id(proxy_id=proxy_id)
