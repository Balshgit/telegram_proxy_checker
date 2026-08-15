from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy_utils import ChoiceType

from app.core.proxies.constants import ProxyStatusEnum
from app.core.shared.sqlalchemy import get_public_shema
from app.infra.sqlalchemy.base import DBBase


class TelegramProxy(DBBase):

    __tablename__ = "proxies"
    __table_args__ = ({"schema": get_public_shema()},)

    id: Mapped[int] = mapped_column("id", Integer, primary_key=True, autoincrement=True)
    url: Mapped[str] = mapped_column("url", String, comment="Proxy address")
    created_at: Mapped[datetime] = mapped_column("created_at", DateTime, default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column("updated_at", DateTime)
    status: Mapped[ProxyStatusEnum] = mapped_column("status", ChoiceType(ProxyStatusEnum, impl=String(20)))
    ping: Mapped[int | None] = mapped_column("ping", Integer, comment="Ping to proxy")
