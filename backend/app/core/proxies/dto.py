from dataclasses import dataclass, field
from datetime import datetime

from httpx import URL

from app.core.proxies.constants import ProxySourceStatusEnum, ProxyStatusEnum, ProxyVendorNameEnum
from app.core.types import Missing, MissingType


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
    name: str
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


@dataclass(slots=True, kw_only=True)
class ProxySourceDTO:
    id: int | MissingType = field(default=Missing)
    name: str
    url: URL
    status: ProxySourceStatusEnum
    vendor: ProxyVendorNameEnum
    created_at: datetime | None = None
    updated_at: datetime | None = None
    proxies_count: int = 0
