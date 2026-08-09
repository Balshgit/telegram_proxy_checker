from dependency_injector import containers, providers

from app.core.shared.timezone import SystemClock


class ServicesContainer(containers.DeclarativeContainer):
    config = providers.Configuration(strict=True)
    clock = providers.Singleton(SystemClock, utc_delta=config.TIME_ZONE)
    repositories = providers.DependenciesContainer()
    infra = providers.DependenciesContainer()
    gateways = providers.DependenciesContainer()
