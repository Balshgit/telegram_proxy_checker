"""add proxies.last_active_at

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-13 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "public"


def upgrade() -> None:
    # Время заполняется только когда прокси помечают активной, поэтому колонка nullable
    # и без server_default: NULL здесь значит "активной ещё не была".
    # Объявление совпадает с моделью один в один, иначе следующий autogenerate увидит различие.
    op.add_column("proxies", sa.Column("last_active_at", sa.DateTime(), nullable=True), schema=SCHEMA)


def downgrade() -> None:
    op.drop_column("proxies", "last_active_at", schema=SCHEMA)
