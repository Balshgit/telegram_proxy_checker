from dataclasses import dataclass

from httpx import URL
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import NoResultFound
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.proxies.constants import ProxyStatusEnum
from app.core.proxies.models import TelegramProxy
from app.core.proxies_sources.constants import ProxySourceStatusEnum
from app.core.proxies_sources.dto import ProxySourceDTO, ProxySourceUpdateDTO
from app.core.proxies_sources.exceptions import ProxySourceNotFoundException
from app.core.proxies_sources.models import TelegramProxiesSource
from app.core.repositories import BaseDBRepository


@dataclass
class ProxySourceRepository(BaseDBRepository):

    async def get_proxies_sources(
        self,
        status: ProxySourceStatusEnum | None = None,
        sources_ids: set[int] | None = None,
        session: AsyncSession | None = None,
    ) -> list[ProxySourceDTO]:
        query = select(TelegramProxiesSource).order_by(TelegramProxiesSource.id)

        if status:
            query = query.where(TelegramProxiesSource.status == status)

        if sources_ids:
            query = query.where(TelegramProxiesSource.id.in_(sources_ids))

        result = await self.get_multiple_results(query=query, session=session, as_scalars=True)

        return [self._build_proxy_source_dto(source) for source in result]

    async def get_proxies_source_by_id(
        self, proxy_source_id: int, session: AsyncSession | None = None
    ) -> TelegramProxiesSource:
        query = select(TelegramProxiesSource).where(TelegramProxiesSource.id == proxy_source_id)

        try:
            return await self.get_single_result(query=query, session=session, as_scalar=True)
        except NoResultFound as exc:
            raise ProxySourceNotFoundException(proxy_source_id=proxy_source_id) from exc

    async def add_proxies_source(self, proxy_source_dto: ProxySourceDTO, session: AsyncSession | None = None) -> None:
        # `id` из DTO намеренно игнорируется: его выдаёт последовательность в базе.
        proxy_source = TelegramProxiesSource(
            name=proxy_source_dto.name,
            url=str(proxy_source_dto.url),
            status=proxy_source_dto.status,
            vendor=proxy_source_dto.vendor,
            proxies_count=proxy_source_dto.proxies_count,
            active_proxies_count=proxy_source_dto.active_proxies_count,
            created_at=proxy_source_dto.created_at if proxy_source_dto.created_at else func.now(),
        )

        async with self.session_wrap(session) as wrapped_session:
            wrapped_session.add(proxy_source)

    async def update_proxies_source(
        self,
        proxy_source_id: int,
        proxy_source_update_dto: ProxySourceUpdateDTO,
        session: AsyncSession | None = None,
    ) -> None:

        changed_fields = proxy_source_update_dto.changed_fields()

        if not changed_fields:
            return

        changed_fields.update({TelegramProxiesSource.updated_at.key: func.now()})

        query = (
            update(TelegramProxiesSource).values(**changed_fields).where(TelegramProxiesSource.id == proxy_source_id)
        )

        async with self.session_wrap(session) as wrapped_session:
            await wrapped_session.execute(query)

    async def delete_proxies_source_by_id(self, proxy_source_id: int, session: AsyncSession | None = None) -> None:

        query = delete(TelegramProxiesSource).where(TelegramProxiesSource.id == proxy_source_id)

        async with self.session_wrap(session) as wrapped_session:
            await wrapped_session.execute(query)

    async def recalculate_proxies_sources_counters(
        self, source_ids: set[int] | None = None, session: AsyncSession | None = None
    ) -> None:
        """
        Пересчитывает счётчики проксей у источников.

        Живёт в репозитории источников, а не проксей: пишем мы в `proxies_sources`,
        а таблица `proxies` тут только читается подзапросом.
        """
        if source_ids is not None and not source_ids:
            return

        proxies_count = (
            select(func.count(TelegramProxy.id))
            .where(TelegramProxy.source_id == TelegramProxiesSource.id)
            .correlate(TelegramProxiesSource)
            .scalar_subquery()
        )
        active_proxies_count = (
            select(func.count(TelegramProxy.id))
            .where(
                TelegramProxy.source_id == TelegramProxiesSource.id,
                TelegramProxy.status == ProxyStatusEnum.enabled,
            )
            .correlate(TelegramProxiesSource)
            .scalar_subquery()
        )

        query = (
            update(TelegramProxiesSource)
            .values(
                proxies_count=proxies_count,
                active_proxies_count=active_proxies_count,
                updated_at=func.now(),
            )
            .execution_options(synchronize_session=False)
        )

        if source_ids is not None:
            query = query.where(TelegramProxiesSource.id.in_(list(source_ids)))

        async with self.session_wrap(session) as wrapped_session:
            await wrapped_session.execute(query)

    @staticmethod
    def _build_proxy_source_dto(proxy_source: TelegramProxiesSource) -> ProxySourceDTO:
        return ProxySourceDTO(
            id=proxy_source.id,
            name=proxy_source.name,
            url=URL(proxy_source.url),
            status=proxy_source.status,
            vendor=proxy_source.vendor,
            created_at=proxy_source.created_at,
            updated_at=proxy_source.updated_at,
            proxies_count=proxy_source.proxies_count,
            active_proxies_count=proxy_source.active_proxies_count,
        )
