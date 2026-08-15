import typing

from httpx import URL
from taskiq import Context, TaskiqDepends

from app.core.shared.utils import log_taskiq_decorator

if typing.TYPE_CHECKING:
    from app.core.proxies.repositories import ProxyRepository
    from app.core.proxies.services import ProxyService


@log_taskiq_decorator
async def save_proxies_to_database_task(context: typing.Annotated[Context, TaskiqDepends()], urls: list[str]) -> None:
    proxy_service: ProxyService = context.state.container.services.proxy_service()
    proxy_repository: ProxyRepository = context.state.container.repositories.proxy_repository()

    urls_for_ping = [URL(url) for url in urls]
    proxies = await proxy_service.get_host_latency_for_urls(urls=urls_for_ping)
    await proxy_repository.save_proxies(proxies)
