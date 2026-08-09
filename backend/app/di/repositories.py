from dependency_injector import containers, providers


class RepositoriesContainer(containers.DeclarativeContainer):
    config = providers.Configuration(strict=True)
    infra = providers.DependenciesContainer()
    adapters = providers.DependenciesContainer()
    gateways = providers.DependenciesContainer()
