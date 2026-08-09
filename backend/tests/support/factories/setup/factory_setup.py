from collections.abc import Sequence
from typing import TypeVar

from faker import Faker
from polyfactory.factories.sqlalchemy_factory import SQLAlchemyFactory
from polyfactory.persistence import AsyncPersistenceProtocol
from sqlalchemy.ext.asyncio import AsyncSession

from tests.application import local_debug_settings
from tests.support.factories.setup.async_persistence import FlushOnlyAsyncPersistence

T = TypeVar("T")


def setup_factory[T](factory: type[SQLAlchemyFactory[T]], session: AsyncSession) -> type[SQLAlchemyFactory[T]]:
    persistence: AsyncPersistenceProtocol[T] = FlushOnlyAsyncPersistence[T](
        session=session, debug=local_debug_settings.DEBUG
    )
    factory.__async_persistence__ = persistence
    factory.__set_primary_key__ = False
    factory.__set_relationships__ = False
    factory.__faker__ = Faker(locale="ru_RU")
    return factory


ChoiceT = TypeVar("ChoiceT")


def factory_random_choice[ChoiceT](choices: Sequence[ChoiceT]) -> ChoiceT:
    return SQLAlchemyFactory.__random__.choice(choices)


faker_instance = Faker()
