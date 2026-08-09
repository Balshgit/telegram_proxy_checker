from collections.abc import Iterator
from dataclasses import dataclass

from loguru import logger

from app.infra.adapters.database import Database
from app.infra.sqlalchemy.typing import DatabasePostgresDB
from settings.config import AppSettings


@dataclass(slots=True)
class DatabaseEngines:
    db: DatabasePostgresDB

    @staticmethod
    def build(*, settings: AppSettings) -> DatabaseEngines:

        uri = settings.DB_SQLALCHEMY_DATABASE_URI
        debug = settings.DB_SQLALCHEMY_LOGS

        db = Database.build(dsn=str(uri), debug=debug)

        return DatabaseEngines(db=db)  # type: ignore[arg-type]

    async def disconnect(self) -> None:
        await self.db.disconnect()

    async def create_all_tables(self) -> None:

        error = await self.db.create_postgres_tables()
        if error:
            logger.critical("invalid ddl schemas", error=repr(error))
        else:
            logger.info("ddl schemas are correct")

    def __iter__(self) -> Iterator[Database]:
        yield self.db
