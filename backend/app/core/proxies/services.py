from dataclasses import dataclass
from itertools import chain

from sqlakeyset import Page

from app.core.concurrency import run_async
from app.core.pagination import OffsetPagination
from app.core.proxies.constants import SAVE_POSTGRES_CHUNK_SIZE, ProxyOrderByEnum, ProxyStatusEnum
from app.core.proxies.dto import ProxyCountersDTO, ProxyDTO, ProxyFilterDTO, ProxySourceToPingDTO
from app.core.proxies.exceptions import NoProxiesAddedException
from app.core.proxies.models import TelegramProxy
from app.core.proxies.repositories import ProxyRepository
from app.core.proxies.tasks import save_proxies_to_database_task, update_proxies_in_database_task
from app.core.proxies.utils import collect_source_ids, split_duplicated_proxies, to_web_proxy_url
from app.core.proxies_sources.constants import ProxySourceStatusEnum
from app.core.proxies_sources.services import ProxySourceService
from app.infra.gateways.github_gateway import GithubGateway
from app.infra.taskiq.executor import TaskiqTasksExecutor


@dataclass
class ProxyService:
    repository: ProxyRepository
    proxy_source_service: ProxySourceService
    github_gateway: GithubGateway
    taskiq_tasks_executor: TaskiqTasksExecutor

    async def get_all_proxies(
        self,
        filters: ProxyFilterDTO,
        pagination: OffsetPagination,
        order_by: ProxyOrderByEnum = ProxyOrderByEnum.latency,
    ) -> tuple[Page[list[ProxyDTO]], ProxyCountersDTO]:
        proxies_page, counters = await self.repository.get_paginated_proxies(
            filters=filters, pagination=pagination, order_by=order_by
        )
        proxies = [
            ProxyDTO(
                id=proxy.id,
                source_name=proxy.source.name if proxy.source else None,
                created_at=proxy.created_at,
                updated_at=proxy.updated_at,
                url=proxy.tg_proxy_url,
                name=proxy.name,
                source_id=proxy.source_id,
                latency=proxy.latency,
                status=proxy.status,
            )
            for proxy in proxies_page
        ]
        return Page(proxies, proxies_page.paging), counters  # type: ignore[arg-type]

    async def get_proxy(self, proxy_id: int) -> ProxyDTO:
        proxy = await self.repository.get_proxy_by_id(proxy_id=proxy_id, with_source=True)

        return ProxyDTO(
            id=proxy.id,
            source_id=proxy.source_id,
            source_name=proxy.source.name if proxy.source else None,
            created_at=proxy.created_at,
            updated_at=proxy.updated_at,
            url=proxy.tg_proxy_url,
            name=proxy.name,
            latency=proxy.latency,
            status=proxy.status,
        )

    async def get_raw_proxies_urls(self, status: ProxyStatusEnum | None) -> str:
        urls = await self.repository.get_proxies_urls(status=status)
        return "\n".join(url for url in urls)

    async def add_new_proxies(self, sources_ids: set[int] | None = None) -> None:
        # Пустой набор источников означает "собрать со всех включённых": фильтр просто не применяется.
        proxy_sources = await self.proxy_source_service.get_proxies_sources(
            status=ProxySourceStatusEnum.enabled, sources_ids=sources_ids
        )

        coros = [self.github_gateway.get_urls_for_ping(proxy_source=ps) for ps in proxy_sources]

        new_proxies_url_lists = list(chain.from_iterable(await run_async(*coros))) if coros else []

        existing_proxies = await self.repository.get_all_proxies()

        existing_proxies_urls = {to_web_proxy_url(proxy.url) for proxy in existing_proxies}

        new_proxies_to_ping = [
            ProxySourceToPingDTO(source_id=proxy_to_ping.source_id, url=to_web_proxy_url(proxy_to_ping.url))
            for proxy_to_ping in new_proxies_url_lists
        ]

        # Дедупликация идёт по урлу, а не по паре (source_id, url): один и тот же урл,
        # отданный несколькими источниками, должен попасть в базу ровно один раз.
        urls_for_ping = list(
            {
                proxy_to_ping.url: proxy_to_ping
                for proxy_to_ping in new_proxies_to_ping
                if proxy_to_ping.url not in existing_proxies_urls
            }.values()
        )

        if not urls_for_ping:
            raise NoProxiesAddedException()

        proxies_dtos = await self.github_gateway.get_host_latency_for_urls(
            urls_with_source=urls_for_ping[:SAVE_POSTGRES_CHUNK_SIZE]
        )
        async with self.repository.get_transactional_session() as session:
            await self.repository.save_proxies(proxies_dto=proxies_dtos, session=session)
            await self.proxy_source_service.recalculate_counters(
                source_ids=collect_source_ids(proxies_dtos), session=session
            )

        if all_next_proxies := urls_for_ping[SAVE_POSTGRES_CHUNK_SIZE:]:
            await self.taskiq_tasks_executor.run(
                save_proxies_to_database_task,
                params={"source_urls": [su.to_dict() for su in all_next_proxies]},
            )

    async def update_proxy(
        self, proxy_id: int, is_latency_update: bool = False, status: ProxyStatusEnum | None = None
    ) -> TelegramProxy:

        async with self.repository.get_transactional_session() as session:
            proxy = await self.repository.get_proxy_by_id(proxy_id=proxy_id, session=session)
            if not is_latency_update and not status:
                return proxy

            latency = proxy.latency
            proxy_url_with_source = ProxySourceToPingDTO(source_id=proxy.source_id, url=proxy.url)
            if is_latency_update:
                proxy_base_dto = await self.github_gateway.get_host_latency(proxy_url_with_source)
                status = ProxyStatusEnum.enabled if proxy_base_dto.latency is not None else ProxyStatusEnum.disabled
                latency = proxy_base_dto.latency

            await self.repository.update_proxy(proxy, latency=latency, status=status, session=session)
            await self.proxy_source_service.recalculate_counters(
                source_ids={proxy.source_id} if proxy.source_id else None, session=session
            )
            return proxy

    async def delete_all_proxies(self) -> None:
        async with self.repository.get_transactional_session() as session:
            await self.repository.delete_proxies(session=session)
            await self.proxy_source_service.recalculate_counters(session=session)

    async def update_all_proxies(self) -> None:
        # Удаление дублей и обновление оставшихся проксей едут одной транзакцией:
        # иначе упавшее обновление оставило бы базу без уже удалённых дублей.
        async with self.repository.get_transactional_session() as session:
            existing_proxies = await self.repository.get_all_proxies(session=session)

            unique_proxies, duplicated_proxies = split_duplicated_proxies(existing_proxies)

            existing_proxies_urls = [
                ProxySourceToPingDTO(source_id=proxy.source_id, url=proxy.url) for proxy in unique_proxies
            ]
            source_ids_to_recalculate = {proxy.source_id for proxy in duplicated_proxies if proxy.source_id is not None}

            if duplicated_proxies:
                await self.repository.delete_proxies(
                    proxy_ids={proxy.id for proxy in duplicated_proxies}, session=session
                )

            proxies_dtos = await self.github_gateway.get_host_latency_for_urls(
                urls_with_source=existing_proxies_urls[:SAVE_POSTGRES_CHUNK_SIZE]
            )

            if proxies_dtos:
                await self.repository.update_proxies(proxies_dtos, session=session)
                source_ids_to_recalculate |= collect_source_ids(proxies_dtos)

            if source_ids_to_recalculate:
                await self.proxy_source_service.recalculate_counters(
                    source_ids=source_ids_to_recalculate, session=session
                )

        if all_next_existing_proxies := existing_proxies_urls[SAVE_POSTGRES_CHUNK_SIZE:]:
            await self.taskiq_tasks_executor.run(
                update_proxies_in_database_task,
                params={"source_urls": [su.to_dict() for su in all_next_existing_proxies]},
            )

    async def delete_proxy_by_id(self, proxy_id: int) -> None:
        async with self.repository.get_transactional_session() as session:
            # Удаление идемпотентно: `source_id` приходит из `RETURNING`, и его нет, если удалять было нечего.
            source_id = await self.repository.delete_proxy_by_id(proxy_id=proxy_id, session=session)

            if source_id is not None:
                await self.proxy_source_service.recalculate_counters(source_ids={source_id}, session=session)
