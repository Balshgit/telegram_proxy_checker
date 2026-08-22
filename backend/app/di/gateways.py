from dependency_injector import containers, providers

from app.infra.gateways.github_gateway import GithubGateway


class GatewaysContainer(containers.DeclarativeContainer):
    config = providers.Configuration(strict=True)
    infra = providers.DependenciesContainer()
    adapters = providers.DependenciesContainer()

    github_gateway: providers.Singleton[GithubGateway] = providers.Singleton(
        GithubGateway, http_adapter=adapters.github_http_adapter
    )
