from datetime import datetime
from typing import Any
from urllib.parse import urlencode

from httpx import URL
from polyfactory.factories.sqlalchemy_factory import SQLAlchemyFactory

from app.core.proxies.constants import ProxyStatusEnum
from app.core.proxies.models import TelegramProxy
from app.core.proxies_sources.constants import ProxySourceStatusEnum
from app.core.proxies_sources.models import TelegramProxiesSource
from tests.support.factories.proxies_sources import TelegramProxiesSourceFactory
from tests.support.factories.setup.async_persistence import FlushOnlyAsyncPersistence
from tests.support.factories.setup.factory_setup import factory_random_choice, setup_factory


class TelegramProxyFactory(SQLAlchemyFactory[TelegramProxy]):
    #: `source_id` — внешний ключ на `proxies_sources`, случайное число от polyfactory уронило бы
    #: вставку по `proxy_source_ref`. В `build()` он остаётся пустым, в `create_async` /
    #: `create_batch_async` подставляется id настоящего источника.
    __set_foreign_keys__ = False

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

    @classmethod
    async def create_default_source(cls) -> TelegramProxiesSource:
        """
        Создаёт настоящий источник в базе и отдаёт его.

        Фабрика источников настраивается на ту же сессию, что и фабрика проксей,
        иначе запись уедет мимо тестовой транзакции.

        Источник создаётся включённым: если тест дополнительно опрашивает github
        (`ProxyService.add_new_proxies`), передавайте `source_id` явно, иначе сервис
        сходит и за этим источником тоже.
        """
        persistence = cls.__async_persistence__

        if not isinstance(persistence, FlushOnlyAsyncPersistence):
            raise TypeError(f"{cls.__name__} должна настраиваться через `setup_factory`")

        source_factory = setup_factory(TelegramProxiesSourceFactory, persistence.session)
        return await source_factory.create_async(status=ProxySourceStatusEnum.enabled)

    @classmethod
    async def create_async(cls, **kwargs: Any) -> TelegramProxy:
        if "source_id" not in kwargs:
            kwargs["source_id"] = (await cls.create_default_source()).id
        return await super().create_async(**kwargs)

    @classmethod
    async def create_batch_async(cls, size: int, **kwargs: Any) -> list[TelegramProxy]:
        if "source_id" not in kwargs:
            kwargs["source_id"] = (await cls.create_default_source()).id
        return await super().create_batch_async(size=size, **kwargs)
