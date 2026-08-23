import asyncio
import pkgutil
from importlib import import_module
from logging.config import fileConfig
from pathlib import Path
from typing import Any

from alembic import context
from sqlalchemy import Connection, MetaData, pool
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy_utils import ChoiceType

from app.core.shared.sqlalchemy import DatabaseSchema, get_public_shema
from app.infra.sqlalchemy.base import DBBase
from settings.config import load_app_settings

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

VERSION_TABLE = "alembic_version"
VERSION_TABLE_SCHEMA = get_public_shema()

CORE_PACKAGE = "app.core"
MODELS_MODULE_NAME = "models"


def load_all_models() -> None:
    """
    Импортирует все модули и пакеты `models` внутри `app/core`.

    `DBBase.metadata` заполняется только импортированными модулями, поэтому без этого
    `--autogenerate` не увидит новые таблицы. Ручной список моделей поддерживать не нужно:
    достаточно положить модель в `app/core/<домен>/models.py` или `app/core/<домен>/models/`.
    """
    # app/infra/migrations/env.py -> app/core
    core_dir = Path(__file__).resolve().parent.parent.parent / "core"

    def _reraise(name: str) -> None:
        # По умолчанию walk_packages молча глотает ImportError: сломанный пакет тихо выпал бы
        # из metadata, а `--autogenerate` сгенерировал бы DROP TABLE.
        raise ImportError(f"failed to import package {name} while collecting models")

    for module in pkgutil.walk_packages(path=[str(core_dir)], prefix=f"{CORE_PACKAGE}.", onerror=_reraise):
        if MODELS_MODULE_NAME in module.name.split("."):
            import_module(module.name)


load_all_models()

target_metadata: MetaData = DBBase.metadata


def _database_url() -> str:
    return str(load_app_settings().DB_SQLALCHEMY_DATABASE_URI)


def _include_object(_object: Any, _name: str | None, type_: str, _reflected: bool, _compare_to: Any) -> bool:
    """Не трогаем таблицы вне схем, которыми управляет приложение."""
    if type_ == "table":
        schema = getattr(_object, "schema", None)
        return schema is None or schema in {member.value for member in DatabaseSchema}
    return True


def _render_item(type_: str, obj: Any, autogen_context: Any) -> str | bool:
    """`ChoiceType` из sqlalchemy_utils рендерим как его impl, чтобы миграции не тянули лишний импорт."""
    if type_ == "type" and isinstance(obj, ChoiceType):
        autogen_context.imports.add("import sqlalchemy as sa")
        length = getattr(obj.impl, "length", None)
        return f"sa.String(length={length})" if length else "sa.String()"
    return False


def _configure(connection: Connection | None = None, url: str | None = None) -> None:
    context.configure(
        connection=connection,
        url=url,
        target_metadata=target_metadata,
        version_table=VERSION_TABLE,
        version_table_schema=VERSION_TABLE_SCHEMA,
        include_schemas=True,
        include_object=_include_object,
        render_item=_render_item,
        compare_type=True,
        compare_server_default=True,
        render_as_batch=False,
        literal_binds=url is not None,
        dialect_opts={"paramstyle": "named"},
    )


def run_migrations_offline() -> None:
    """Генерация SQL без подключения к БД (`alembic upgrade head --sql`)."""
    _configure(url=_database_url())

    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection: Connection) -> None:
    _configure(connection=connection)

    with context.begin_transaction():
        context.run_migrations()


async def _run_async_migrations() -> None:
    # `%` в пароле/имени БД ломает интерполяцию configparser, поэтому экранируем.
    config.set_main_option("sqlalchemy.url", _database_url().replace("%", "%%"))

    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(_do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(_run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
