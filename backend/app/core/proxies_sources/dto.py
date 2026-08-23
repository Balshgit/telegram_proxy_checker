from dataclasses import dataclass, field, fields
from datetime import datetime
from typing import Any

from httpx import URL

from app.core.proxies_sources.constants import ProxySourceStatusEnum, ProxyVendorNameEnum
from app.core.shared.types import Missing, MissingType


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
    active_proxies_count: int = 0


@dataclass(slots=True, kw_only=True)
class ProxySourceUpdateDTO:
    """
    Частичное обновление источника: `Missing` означает "поле не пришло в запросе".

    `None` для этих полей — валидное значение с точки зрения питона, но не для базы,
    поэтому "не передано" отличается от "передано" именно сентинелом, а не `None`.
    """

    name: str | MissingType = field(default=Missing)
    url: URL | MissingType = field(default=Missing)
    status: ProxySourceStatusEnum | MissingType = field(default=Missing)
    vendor: ProxyVendorNameEnum | MissingType = field(default=Missing)

    def changed_fields(self) -> dict[str, Any]:
        """Отдаёт только те поля, что реально пришли в запросе, уже в виде, пригодном для модели."""
        changed: dict[str, Any] = {}
        for dataclass_field in fields(self):
            value = getattr(self, dataclass_field.name)
            if value is Missing:
                continue
            changed[dataclass_field.name] = str(value) if dataclass_field.name == "url" else value
        return changed
