from dependency_injector import containers, providers

from app.core.proxies.services import ProxyService
from app.core.proxies_sources.services import ProxySourceService
from app.core.shared.timezone import SystemClock


class ServicesContainer(containers.DeclarativeContainer):
    config = providers.Configuration(strict=True)
    clock = providers.Singleton(SystemClock, utc_delta=config.TIME_ZONE)
    repositories = providers.DependenciesContainer()
    infra = providers.DependenciesContainer()
    gateways = providers.DependenciesContainer()

    proxy_source_service: providers.Singleton[ProxySourceService] = providers.Singleton(
        ProxySourceService,
        repository=repositories.proxy_source_repository,
    )

    proxy_service: providers.Singleton[ProxyService] = providers.Singleton(
        ProxyService,
        repository=repositories.proxy_repository,
        proxy_source_service=proxy_source_service,
        github_gateway=gateways.github_gateway,
        taskiq_tasks_executor=infra.taskiq_tasks_executor,
    )
