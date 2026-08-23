"""create proxies table

Revision ID: 0001
Revises: 0000
Create Date: 2026-08-23 00:01:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = "0000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "public"


def upgrade() -> None:
    op.create_table(
        "proxies",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False, comment="Proxy name"),
        sa.Column("url", sa.String(length=4000), nullable=False, comment="Proxy address"),
        sa.Column("source_id", sa.Integer(), nullable=True, comment="Proxy source id"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("latency", sa.Integer(), nullable=True, comment="Latency to proxy"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "source_id", name="One url from one source"),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("proxies", schema=SCHEMA)
