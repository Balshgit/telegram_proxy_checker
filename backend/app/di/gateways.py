from dependency_injector import containers, providers


class GatewaysContainer(containers.DeclarativeContainer):
    config = providers.Configuration(strict=True)
    infra = providers.DependenciesContainer()
    adapters = providers.DependenciesContainer()
