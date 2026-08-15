from dependency_injector import containers, providers

from app.infra.adapters.http_adapter import BaseHttpAdapter
from app.infra.adapters.in_memory_cache_adapter import TPCTLRUCache, init_prc_in_memory_cache


class AdaptersContainer(containers.DeclarativeContainer):
    config = providers.Configuration(strict=True)

    prc_in_memory_cache: providers.Resource[TPCTLRUCache] = providers.Resource(init_prc_in_memory_cache)

    github_adapter: providers.Singleton[BaseHttpAdapter] = providers.Singleton(
        BaseHttpAdapter, host="https://raw.githubusercontent.com"
    )
