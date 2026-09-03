from datetime import datetime
from typing import Annotated, Any

from fastapi import status
from httpx import URL
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_core import Url

from app.api.base_schemas import BaseError, BasePaginationSerializer
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


class TelegramProxyPaginatedSerializers(BaseModel):
    pagination: Annotated[BasePaginationSerializer, Field(..., title="pagination")]
    data: Annotated[list[TelegramProxySerializer], Field(..., description="Список проксей")]
    counters: Annotated[ProxiesCounters, Field(..., description="Счётчики прокси")]
    proxies_share: Annotated[str, Field(..., description="Список проксей для расшаривания")]


class PaginatedTelegramProxyWithCountersSerializer(BaseModel):
    status: Annotated[int, Field(..., title="Status code of request.", examples=[status.HTTP_200_OK])]
    error: Annotated[dict[Any, Any] | BaseError | None, Field(None, title="Errors")]
    payload: Annotated[TelegramProxyPaginatedSerializers, Field(title="Payload data.", default_factory=dict)]


class UpdateProxyRequestSerializer(BaseModel):

    status: Annotated[ProxyStatusEnum | None, Field(default=None, description="Статус прокси")]
    is_latency_update: Annotated[bool, Field(default=False, description="Нужно ли обновить латенси")]


class SaveProxiesRequestSerializer(BaseModel):

    source_ids: Annotated[
        list[int] | None,
        Field(
            default=None,
            description="ID источников, которые нужно опросить. Если не передано опрашиваем все включённые источники",
        ),
    ]
