from dataclasses import dataclass
from datetime import datetime

from app.core.proxies.constants import ProxyStatusEnum


@dataclass(slots=True, kw_only=True)
class ProxyFilterDTO:
    created_from: datetime | None = None
    created_to: datetime | None = None
    status: ProxyStatusEnum | None = None
