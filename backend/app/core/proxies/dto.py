from dataclasses import dataclass
from datetime import datetime
from typing import Any

from httpx import URL

from app.core.proxies.constants import ProxyStatusEnum
from app.core.shared.types import Missing, MissingType


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
    source_id: int | None
    latency: int | None = None
    status: ProxyStatusEnum


@dataclass(slots=True, kw_only=True)
class ProxyDTO(ProxyBaseDTO):
    id: int
    source_name: str | None
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


@dataclass(slots=True, kw_only=True, unsafe_hash=True)
class ProxySourceToPingDTO:
    source_id: int | None | MissingType
    url: URL

    def __post_init__(self) -> None:
        self.source_id = None if self.source_id is Missing else self.source_id
        self.url = URL(self.url) if isinstance(self.url, str) else self.url  # type: ignore[unreachable]

    def to_dict(self) -> dict[str, Any]:
        return {"source_id": self.source_id, "url": str(self.url)}
