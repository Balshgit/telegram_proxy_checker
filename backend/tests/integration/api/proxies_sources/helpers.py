from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.proxies_sources.models import TelegramProxiesSource

MISSING_PROXY_SOURCE_ID = 888_888

NEW_SOURCE_NAME = "my-collector"
NEW_SOURCE_URL = "https://raw.githubusercontent.com/owner/repo/main/proxies.txt"

UPDATED_SOURCE_NAME = "renamed-collector"
UPDATED_SOURCE_URL = "https://raw.githubusercontent.com/owner/repo/main/renamed.txt"


async def get_proxies_sources_by_id(session: AsyncSession) -> dict[int, TelegramProxiesSource]:
    """
    Все источники из базы, разложенные по `id`.

    `populate_existing` обязателен: объекты, созданные фабрикой или эндпоинтом, остаются
    в identity map, и без перечитывания тест проверял бы кэш сессии, а не базу.
    """
    query = select(TelegramProxiesSource).execution_options(populate_existing=True)
    sources = (await session.execute(query)).scalars().all()
    return {source.id: source for source in sources}
