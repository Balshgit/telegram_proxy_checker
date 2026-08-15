from datetime import datetime
from urllib.parse import urlencode, urljoin

from httpx import URL
from polyfactory.factories.sqlalchemy_factory import SQLAlchemyFactory

from app.core.proxies.constants import ProxyStatusEnum
from app.core.proxies.models import TelegramProxy
from tests.support.factories.setup.factory_setup import factory_random_choice


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
