from dependency_injector import containers, providers

from app.core.proxies.constants import PROXY_PING_TIMEOUT
from app.infra.gateways.github_gateway import GithubGateway
from app.infra.gateways.mtproto_checker import MTProxyChecker


class GatewaysContainer(containers.DeclarativeContainer):
    config = providers.Configuration(strict=True)
    infra = providers.DependenciesContainer()
    adapters = providers.DependenciesContainer()

    mtproxy_checker: providers.Singleton[MTProxyChecker] = providers.Singleton(
        MTProxyChecker, timeout=PROXY_PING_TIMEOUT
    )

    github_gateway: providers.Singleton[GithubGateway] = providers.Singleton(
        GithubGateway, github_http_adapter=adapters.github_http_adapter, mtproxy_checker=mtproxy_checker
    )
