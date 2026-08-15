from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field
from pydantic_core import Url

from app.core.proxies.constants import ProxyStatusEnum


class ProxiesCounters(BaseModel):
    total: Annotated[int, Field(..., ge=0, description="Всего проксей")]


class TelegramProxySerializer(BaseModel):

    id: Annotated[int, Field(..., description="ID прокси")]
    url: Annotated[Url, Field(..., description="Урл прокси")]
    created_at: Annotated[datetime, Field(..., description="Дата создания урла прокси")]
    updated_at: Annotated[datetime | None, Field(..., description="Дата обновления урла прокси")]
    status: Annotated[ProxyStatusEnum, Field(..., description="Статус прокси")]
    latency: Annotated[int | None, Field(..., description="Пинг до прокси в мс")]

    model_config = ConfigDict(from_attributes=True)
