from dependency_injector import containers, providers

from app.infra.adapters.in_memory_cache_adapter import TPCTLRUCache, init_prc_in_memory_cache


class AdaptersContainer(containers.DeclarativeContainer):
    config = providers.Configuration(strict=True)

    prc_in_memory_cache: providers.Resource[TPCTLRUCache] = providers.Resource(init_prc_in_memory_cache)
