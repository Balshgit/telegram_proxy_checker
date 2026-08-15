from datetime import datetime

from httpx import URL
from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy_utils import ChoiceType

from app.core.proxies.constants import TELEGRAM_PROXY_APP_HOST, TELEGRAM_PROXY_APP_SCHEME, ProxyStatusEnum
from app.core.shared.sqlalchemy import get_public_shema
from app.infra.sqlalchemy.base import DBBase


class TelegramProxy(DBBase):

    __tablename__ = "proxies"
    __table_args__ = ({"schema": get_public_shema()},)

    id: Mapped[int] = mapped_column("id", Integer, primary_key=True, autoincrement=True)
    url: Mapped[URL] = mapped_column("url", String(4000), comment="Proxy address")
    created_at: Mapped[datetime] = mapped_column("created_at", DateTime, default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column("updated_at", DateTime)
    status: Mapped[ProxyStatusEnum] = mapped_column("status", ChoiceType(ProxyStatusEnum, impl=String(20)))
    latency: Mapped[int | None] = mapped_column("latency", Integer, comment="Latency to proxy")

    @property
    def tg_proxy_url(self) -> URL:
        return URL(scheme=TELEGRAM_PROXY_APP_SCHEME, host=TELEGRAM_PROXY_APP_HOST, params=URL(self.url).params)
