"""create proxies_sources table

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-23 00:01:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "public"


def upgrade() -> None:
    op.create_table(
        "proxies_sources",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False, comment="Displayed source name"),
        sa.Column("url", sa.String(length=4000), nullable=False, comment="Proxies source address"),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("vendor", sa.String(length=50), nullable=False, comment="Source vendor"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("proxies_count", sa.Integer(), nullable=False, comment="Proxies from this source"),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("proxies_sources", schema=SCHEMA)
