"""create public schema

Revision ID: 0000
Revises:
Create Date: 2026-08-23 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0000"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "public"


def upgrade() -> None:
    op.execute(sa.text(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}"))


def downgrade() -> None:
    # `public` — схема по умолчанию, её удаление снесло бы в том числе `alembic_version`.
    # Откат сознательно ничего не делает.
    pass
