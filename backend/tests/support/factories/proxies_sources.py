from datetime import datetime

from polyfactory.factories.sqlalchemy_factory import SQLAlchemyFactory

from app.core.proxies_sources.constants import GITHUB_RAW_BASE_URL, ProxySourceStatusEnum, ProxyVendorNameEnum
from app.core.proxies_sources.models import TelegramProxiesSource
from tests.support.factories.setup.factory_setup import factory_random_choice


class TelegramProxiesSourceFactory(SQLAlchemyFactory[TelegramProxiesSource]):
    status: ProxySourceStatusEnum = factory_random_choice(list(ProxySourceStatusEnum))
    vendor: ProxyVendorNameEnum = factory_random_choice(list(ProxyVendorNameEnum))
    #: Счётчики считает сама база (`recalculate_proxies_sources_counters`), а API отдаёт их с `ge=0`:
    #: случайное (в том числе отрицательное) число от polyfactory уронило бы сериализацию.
    proxies_count: int = 0
    active_proxies_count: int = 0

    @classmethod
    def url(cls) -> str:
        return f"{GITHUB_RAW_BASE_URL}/{cls.__faker__.uuid4()}"

    @classmethod
    def updated_at(cls) -> datetime | None:
        return None
