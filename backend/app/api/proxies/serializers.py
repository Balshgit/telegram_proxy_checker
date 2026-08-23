from datetime import datetime
from typing import Annotated

from httpx import URL
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_core import Url

from app.core.proxies.constants import ProxyStatusEnum


class ProxiesCounters(BaseModel):
    total: Annotated[int, Field(..., ge=0, description="Всего проксей")]
    active: Annotated[int, Field(..., ge=0, description="Всего активных проксей")]

    model_config = ConfigDict(from_attributes=True)


class TelegramProxySerializer(BaseModel):

    id: Annotated[int, Field(..., description="ID прокси")]
    name: Annotated[str, Field(..., description="Имя прокси")]
    url: Annotated[Url, Field(..., description="Урл прокси")]
    source_name: Annotated[str | None, Field(..., description="Название источника прокси")]
    created_at: Annotated[datetime, Field(..., description="Дата создания урла прокси")]
    updated_at: Annotated[datetime | None, Field(..., description="Дата обновления урла прокси")]
    status: Annotated[ProxyStatusEnum, Field(..., description="Статус прокси")]
    latency: Annotated[int | None, Field(..., description="Пинг до прокси в мс")]

    @field_validator("url", mode="before")
    @classmethod
    def url_validator(cls, value: URL) -> str:
        return str(value)

    model_config = ConfigDict(from_attributes=True)


class UpdateProxyRequestSerializer(BaseModel):

    status: Annotated[ProxyStatusEnum | None, Field(default=None, description="Статус прокси")]
    is_latency_update: Annotated[bool, Field(default=False, description="Нужно ли обновить латенси")]
