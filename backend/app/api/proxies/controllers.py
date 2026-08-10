from datetime import datetime
from typing import Annotated

from dependency_injector.wiring import inject
from fastapi import APIRouter, Depends, Query
from starlette import status

from app.api.base_deps import get_offset_pagination
from app.api.base_schemas import PaginationResponseWithCounters
from app.api.proxies.serializers import ProxiesCounters, TelegramProxySerializer
from app.api.responses import build_responses
from app.api.router import TPCAPIRoute
from app.core.pagination import OffsetPagination
from app.core.proxies.constants import ProxyStatusEnum
from app.core.proxies.dto import ProxyFilterDTO
from app.core.proxies.services import ProxyService
from app.di.dependency_injector import AsyncProvide, Container

router = APIRouter(route_class=TPCAPIRoute)


@router.get(
    "/proxies",
    name="proxies:get_paginated_proxies",
    status_code=status.HTTP_200_OK,
    summary="Получение списка проксей",
    responses=build_responses(
        status_code=status.HTTP_200_OK,
        response_model=PaginationResponseWithCounters[TelegramProxySerializer, ProxiesCounters],
    ),
)
@inject
async def get_paginated_proxies(
    proxy_service: Annotated[ProxyService, Depends(AsyncProvide[Container.services.proxy_service])],
    pagination: OffsetPagination = Depends(get_offset_pagination),
    created_from: Annotated[
        datetime | None, Query(..., description="Фильтровать от той даты, когда урлы прокси были создан")
    ] = None,
    created_to: Annotated[
        datetime | None, Query(..., description="Фильтровать до той даты, когда урлы прокси были создан")
    ] = None,
    proxy_status: Annotated[ProxyStatusEnum | None, Query(..., description="Фильтр по статусу")] = None,
) -> PaginationResponseWithCounters[TelegramProxySerializer, ProxiesCounters]:

    filters = ProxyFilterDTO(created_from=created_from, created_to=created_to, status=proxy_status)

    proxies_page, total_count = await proxy_service.get_all_proxies(pagination=pagination, filters=filters)

    return PaginationResponseWithCounters.new(
        status_code=status.HTTP_200_OK,
        model=TelegramProxySerializer,
        data=proxies_page,
        pagination=proxies_page.paging,  # type: ignore[arg-type]
        counters_model=ProxiesCounters,
        counters={"total": total_count},
    )
