from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.proxies_sources.constants import ProxySourceStatusEnum
from app.core.proxies_sources.dto import ProxySourceDTO, ProxySourceUpdateDTO
from app.core.proxies_sources.repositories import ProxySourceRepository


@dataclass
class ProxySourceService:
    repository: ProxySourceRepository

    async def get_proxies_sources(
        self,
        status: ProxySourceStatusEnum | None = None,
        sources_ids: set[int] | None = None,
        session: AsyncSession | None = None,
    ) -> list[ProxySourceDTO]:
        return await self.repository.get_proxies_sources(status=status, sources_ids=sources_ids, session=session)

    async def add_proxies_source(self, proxy_source_dto: ProxySourceDTO) -> None:
        async with self.repository.get_transactional_session() as session:
            await self.repository.add_proxies_source(proxy_source_dto=proxy_source_dto, session=session)

    async def update_proxies_source(self, proxy_source_id: int, proxy_source_update_dto: ProxySourceUpdateDTO) -> None:
        async with self.repository.get_transactional_session() as session:
            proxy_source = await self.repository.get_proxies_source_by_id(
                proxy_source_id=proxy_source_id, session=session
            )
            await self.repository.update_proxies_source(
                proxy_source_id=proxy_source.id, proxy_source_update_dto=proxy_source_update_dto, session=session
            )

    async def delete_proxies_source(self, proxy_source_id: int) -> None:
        async with self.repository.get_transactional_session() as session:
            await self.repository.delete_proxies_source_by_id(proxy_source_id=proxy_source_id, session=session)

    async def recalculate_counters(
        self, source_ids: set[int] | None = None, session: AsyncSession | None = None
    ) -> None:
        """
        Пересчёт счётчиков у источников.

        `session` обязателен для вызовов из соседних доменов: пересчёт должен уехать
        в ту же транзакцию, в которой прокси были сохранены или удалены.
        """
        await self.repository.recalculate_proxies_sources_counters(source_ids=source_ids, session=session)
