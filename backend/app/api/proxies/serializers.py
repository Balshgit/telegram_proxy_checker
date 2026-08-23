from datetime import datetime
from typing import Annotated

from httpx import URL
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator
from pydantic_core import Url

from app.core.proxies.constants import ProxySourceStatusEnum, ProxyStatusEnum, ProxyVendorNameEnum

SOURCE_NAME_MAX_LENGTH = 200
SOURCE_URL_MAX_LENGTH = 4000

#: Ограничения навешаны на сам тип, а не на `Field` рядом с `| None`: на nullable-схеме
#: pydantic не может применить их напрямую и подменяет валидатор.
SourceName = Annotated[str, Field(min_length=1, max_length=SOURCE_NAME_MAX_LENGTH)]
SourceUrl = Annotated[HttpUrl, Field(max_length=SOURCE_URL_MAX_LENGTH)]


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


class SaveProxiesRequestSerializer(BaseModel):

    source_ids: Annotated[
        list[int] | None,
        Field(
            default=None,
            description="ID источников, которые нужно опросить. Если не передано опрашиваем все включённые источники",
        ),
    ]


class ProxySourceSerializer(BaseModel):

    id: Annotated[int, Field(..., description="ID источника")]
    name: Annotated[str, Field(..., description="Название источника")]
    url: Annotated[Url, Field(..., description="Адрес, откуда забираются прокси")]
    status: Annotated[ProxySourceStatusEnum, Field(..., description="Статус источника")]
    vendor: Annotated[ProxyVendorNameEnum, Field(..., description="Вендор источника")]
    created_at: Annotated[datetime, Field(..., description="Дата создания источника")]
    updated_at: Annotated[datetime | None, Field(..., description="Дата обновления источника")]
    proxies_count: Annotated[int, Field(..., ge=0, description="Всего проксей из этого источника")]
    active_proxies_count: Annotated[int, Field(..., ge=0, description="Активных проксей из этого источника")]

    @field_validator("url", mode="before")
    @classmethod
    def url_validator(cls, value: URL) -> str:
        return str(value)

    model_config = ConfigDict(from_attributes=True)


class AddProxySourceRequestSerializer(BaseModel):

    name: Annotated[SourceName, Field(..., description="Название источника")]
    url: Annotated[SourceUrl, Field(..., description="Адрес, откуда забираются прокси")]
    status: Annotated[
        ProxySourceStatusEnum, Field(default=ProxySourceStatusEnum.enabled, description="Статус источника")
    ]
    vendor: Annotated[ProxyVendorNameEnum, Field(default=ProxyVendorNameEnum.github, description="Вендор источника")]


class UpdateProxySourceRequestSerializer(BaseModel):
    """Все поля опциональны: `None` означает "поле не меняем"."""

    name: Annotated[SourceName | None, Field(default=None, description="Название источника")]
    url: Annotated[SourceUrl | None, Field(default=None, description="Адрес, откуда забираются прокси")]
    status: Annotated[ProxySourceStatusEnum | None, Field(default=None, description="Статус источника")]
    vendor: Annotated[ProxyVendorNameEnum | None, Field(default=None, description="Вендор источника")]
