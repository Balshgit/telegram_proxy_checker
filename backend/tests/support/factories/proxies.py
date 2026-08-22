from datetime import datetime
from urllib.parse import urlencode

from httpx import URL
from polyfactory.factories.sqlalchemy_factory import SQLAlchemyFactory

from app.core.proxies.constants import GITHUB_RAW_BASE_URL, ProxySourceStatusEnum, ProxyStatusEnum, ProxyVendorNameEnum
from app.core.proxies.models import TelegramProxiesSource, TelegramProxy
from tests.support.factories.setup.factory_setup import factory_random_choice


class TelegramProxiesSourceFactory(SQLAlchemyFactory[TelegramProxiesSource]):
    status: ProxySourceStatusEnum = factory_random_choice(list(ProxySourceStatusEnum))
    vendor: ProxyVendorNameEnum = factory_random_choice(list(ProxyVendorNameEnum))
    proxies_count: int = 0

    @classmethod
    def url(cls) -> str:
        return f"{GITHUB_RAW_BASE_URL}/{cls.__faker__.uuid4()}"

    @classmethod
    def updated_at(cls) -> datetime | None:
        return None


class TelegramProxyFactory(SQLAlchemyFactory[TelegramProxy]):
    status: ProxyStatusEnum = factory_random_choice(list(ProxyStatusEnum))

    @classmethod
    def url(cls) -> str:
        params = {
            "server": cls.__faker__.hostname(),
            "port": cls.__faker__.random_int(min=1, max=9999),
            "secret": cls.__faker__.uuid4(),
        }
        return str(URL(cls.__faker__.url(), params=urlencode(params)))

    @classmethod
    def updated_at(cls) -> datetime | None:
        return None
