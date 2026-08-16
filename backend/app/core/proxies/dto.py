from dataclasses import dataclass
from datetime import datetime

from httpx import URL

from app.core.proxies.constants import ProxyStatusEnum


@dataclass(slots=True, kw_only=True)
class ProxyFilterDTO:
    created_from: datetime | None = None
    created_to: datetime | None = None
    status: ProxyStatusEnum | None = None

    def __post_init__(self) -> None:
        self.created_from = self.created_from.replace(tzinfo=None) if self.created_from else None
        self.created_to = self.created_to.replace(tzinfo=None) if self.created_to else None


@dataclass(slots=True, kw_only=True)
class ProxyBaseDTO:
    url: URL
    latency: int | None = None
    status: ProxyStatusEnum


@dataclass(slots=True, kw_only=True)
class ProxyDTO(ProxyBaseDTO):
    id: int
    created_at: datetime | None
    updated_at: datetime | None = None


@dataclass(slots=True, kw_only=True)
class ProxyServerDTO:
    host: str | None = None
    port: int | None = None


@dataclass(slots=True, kw_only=True)
class ProxyCountersDTO:
    total: int = 0
    active: int = 0
