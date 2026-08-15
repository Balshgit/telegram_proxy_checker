import typing
from itertools import batched

from httpx import URL
from taskiq import Context, TaskiqDepends

from app.core.proxies.constants import SAVE_POSTGRES_CHUNK_SIZE
from app.core.shared.utils import log_taskiq_decorator

if typing.TYPE_CHECKING:
    from app.core.proxies.repositories import ProxyRepository
    from app.core.proxies.services import ProxyService


@log_taskiq_decorator
async def save_proxies_to_database_task(context: typing.Annotated[Context, TaskiqDepends()], urls: list[str]) -> None:
    if not urls:
        return

    proxy_service: ProxyService = context.state.container.services.proxy_service()
    proxy_repository: ProxyRepository = context.state.container.repositories.proxy_repository()

    for urls_chunk in batched(urls, SAVE_POSTGRES_CHUNK_SIZE):  # noqa: B911
        urls_for_ping = [URL(url) for url in urls_chunk]
        proxies = await proxy_service.get_host_latency_for_urls(urls=urls_for_ping)
        await proxy_repository.save_proxies(proxies_dto=proxies)
