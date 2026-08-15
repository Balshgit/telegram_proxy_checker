from datetime import datetime

from polyfactory.factories.sqlalchemy_factory import SQLAlchemyFactory

from app.core.proxies.constants import ProxyStatusEnum
from app.core.proxies.models import TelegramProxy
from tests.support.factories.setup.factory_setup import factory_random_choice


class TelegramProxyFactory(SQLAlchemyFactory[TelegramProxy]):
    status: ProxyStatusEnum = factory_random_choice(list(ProxyStatusEnum))

    @classmethod
    def url(cls) -> str:
        return cls.__faker__.url()

    @classmethod
    def updated_at(cls) -> datetime | None:
        return None
