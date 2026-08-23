"""seed default proxies sources

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-23 00:02:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "public"

# `ChoiceType` хранит в БД именно `.value` члена enum.
# Значения продублированы здесь намеренно: миграция описывает состояние БД на момент выпуска
# и не должна меняться вслед за кодом.
SOURCE_STATUS_ENABLED = "enabled"  # ProxySourceStatusEnum.enabled
SOURCE_VENDOR_GITHUB = "GitHub"  # ProxyVendorNameEnum.github

DEFAULT_SOURCES = (
    {
        "name": "kort0881",
        "url": "https://raw.githubusercontent.com/kort0881/telegram-proxy-collector/main/proxy_all.txt",
    },
    {
        "name": "SoliSpirit",
        "url": "https://raw.githubusercontent.com/SoliSpirit/mtproto/refs/heads/master/all_proxies.txt",
    },
)

proxies_sources = sa.table(
    "proxies_sources",
    sa.column("name", sa.String),
    sa.column("url", sa.String),
    sa.column("status", sa.String),
    sa.column("vendor", sa.String),
    sa.column("proxies_count", sa.Integer),
    sa.column("active_proxies_count", sa.Integer),
    sa.column("created_at", sa.DateTime),
    schema=SCHEMA,
)


def upgrade() -> None:
    op.execute(
        proxies_sources.insert().values(
            [
                {
                    "name": source["name"],
                    "url": source["url"],
                    "status": SOURCE_STATUS_ENABLED,
                    "vendor": SOURCE_VENDOR_GITHUB,
                    "proxies_count": 0,
                    "active_proxies_count": 0,
                    "created_at": sa.func.now(),
                }
                for source in DEFAULT_SOURCES
            ]
        )
    )


def downgrade() -> None:
    urls = [source["url"] for source in DEFAULT_SOURCES]
    op.execute(proxies_sources.delete().where(proxies_sources.c.url.in_(urls)))
