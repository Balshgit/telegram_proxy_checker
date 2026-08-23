from dependency_injector import containers, providers

from app.core.proxies.repositories import ProxyRepository
from app.core.proxies_sources.repositories import ProxySourceRepository


class RepositoriesContainer(containers.DeclarativeContainer):
    config = providers.Configuration(strict=True)
    infra = providers.DependenciesContainer()
    adapters = providers.DependenciesContainer()
    gateways = providers.DependenciesContainer()

    proxy_repository: providers.Singleton[ProxyRepository] = providers.Singleton(
        ProxyRepository,
        db=infra.database_engines.provided.db,
    )
    proxy_source_repository: providers.Singleton[ProxySourceRepository] = providers.Singleton(
        ProxySourceRepository,
        db=infra.database_engines.provided.db,
    )
