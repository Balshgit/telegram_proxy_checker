from datetime import datetime
from typing import Annotated

from httpx import URL
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_core import Url

from app.api.proxies_sources.constants import SourceName, SourceUrl
from app.core.proxies_sources.constants import (
    ProxySourceStatusEnum,
    ProxyVendorNameEnum,
)


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
    vendor: Annotated[ProxyVendorNameEnum, Field(..., description="Вендор источника")]


class UpdateProxySourceRequestSerializer(BaseModel):
    """Все поля опциональны: `None` означает "поле не меняем"."""

    name: Annotated[SourceName | None, Field(default=None, description="Название источника")]
    url: Annotated[SourceUrl | None, Field(default=None, description="Адрес, откуда забираются прокси")]
    status: Annotated[ProxySourceStatusEnum | None, Field(default=None, description="Статус источника")]
    vendor: Annotated[ProxyVendorNameEnum | None, Field(default=None, description="Вендор источника")]
