from typing import NewType

from app.infra.adapters.database import Database

DatabaseDB = NewType("DatabaseDB", Database)
DatabasePostgresDB = NewType("DatabasePostgresDB", Database)
