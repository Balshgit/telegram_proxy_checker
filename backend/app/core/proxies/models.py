from __future__ import annotations

from datetime import datetime

from httpx import URL
from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.orm.relationships import foreign, remote
from sqlalchemy_utils import ChoiceType

from app.core.proxies.constants import TELEGRAM_PROXY_APP_HOST, TELEGRAM_PROXY_APP_SCHEME, ProxyStatusEnum
from app.core.proxies_sources.models import TelegramProxiesSource
from app.core.shared.sqlalchemy import get_public_shema
from app.infra.sqlalchemy.base import DBBase


class TelegramProxy(DBBase):

    __tablename__ = "proxies"
    __table_args__ = (
        UniqueConstraint("id", "source_id", name="One url from one source"),
        {"schema": get_public_shema()},
    )

    id: Mapped[int] = mapped_column("id", Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column("name", String(200), comment="Proxy name")
    url: Mapped[URL] = mapped_column("url", String(4000), comment="Proxy address")
    source_id: Mapped[int | None] = mapped_column(
        "source_id",
        ForeignKey(TelegramProxiesSource.id, ondelete="SET NULL", name="proxy_source_ref"),
        comment="Proxy source id",
    )
    created_at: Mapped[datetime] = mapped_column("created_at", DateTime, default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column("updated_at", DateTime)
    status: Mapped[ProxyStatusEnum] = mapped_column("status", ChoiceType(ProxyStatusEnum, impl=String(20)))
    latency: Mapped[int | None] = mapped_column("latency", Integer, comment="Latency to proxy")

    source: Mapped[TelegramProxiesSource] = relationship(
        TelegramProxiesSource,
        primaryjoin=foreign(source_id) == remote(TelegramProxiesSource.id),
        lazy="raise",
        uselist=False,
        viewonly=True,
        backref="proxies",
    )

    @property
    def tg_proxy_url(self) -> URL:
        return URL(scheme=TELEGRAM_PROXY_APP_SCHEME, host=TELEGRAM_PROXY_APP_HOST, params=URL(self.url).params)
