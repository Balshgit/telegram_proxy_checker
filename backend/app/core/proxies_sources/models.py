from __future__ import annotations

from datetime import datetime

from httpx import URL
from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy_utils import ChoiceType

from app.core.proxies_sources.constants import (
    ProxySourceStatusEnum,
    ProxyVendorNameEnum,
)
from app.core.shared.sqlalchemy import get_public_shema
from app.infra.sqlalchemy.base import DBBase


class TelegramProxiesSource(DBBase):

    __tablename__ = "proxies_sources"
    __table_args__ = ({"schema": get_public_shema()},)

    id: Mapped[int] = mapped_column("id", Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column("name", String(200), comment="Displayed source name")
    url: Mapped[URL] = mapped_column("url", String(4000), comment="Proxies source address")
    status: Mapped[ProxySourceStatusEnum] = mapped_column("status", ChoiceType(ProxySourceStatusEnum, impl=String(20)))
    vendor: Mapped[ProxyVendorNameEnum] = mapped_column(
        "vendor", ChoiceType(ProxyVendorNameEnum, impl=String(50)), comment="Source vendor"
    )
    created_at: Mapped[datetime] = mapped_column("created_at", DateTime, default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column("updated_at", DateTime)
    proxies_count: Mapped[int] = mapped_column(
        "proxies_count",
        Integer,
        server_default="0",
        default=0,
        comment="All proxies count from this source",
    )
    active_proxies_count: Mapped[int] = mapped_column(
        "active_proxies_count",
        Integer,
        server_default="0",
        default=0,
        comment="Active proxies count from this source",
    )
