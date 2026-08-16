from datetime import datetime
from typing import Annotated

from dependency_injector.wiring import inject
from fastapi import APIRouter, Body, Depends, Path, Query
from fastapi.responses import PlainTextResponse
from starlette import status

from app.api.base_deps import get_offset_pagination
from app.api.base_schemas import OkResponse, PaginationResponseWithCounters
from app.api.constants import PLAIN_TEXT_MEDIA_TYPE
from app.api.exceptions import ResourceNotFoundByIDError
from app.api.proxies.exceptions import NoProxiesAddedAPIError
from app.api.proxies.serializers import ProxiesCounters, TelegramProxySerializer, UpdateProxyRequestSerializer
from app.api.responses import build_responses
from app.api.router import TPCAPIRoute
from app.core.constants import ResourceType
from app.core.pagination import OffsetPagination
from app.core.proxies.constants import ProxyStatusEnum
from app.core.proxies.dto import ProxyFilterDTO
from app.core.proxies.exceptions import NoProxiesAddedException, ProxyNotFoundException
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

    proxies_page, counters = await proxy_service.get_all_proxies(pagination=pagination, filters=filters)

    return PaginationResponseWithCounters.new(
        status_code=status.HTTP_200_OK,
        model=TelegramProxySerializer,
        data=proxies_page,
        pagination=proxies_page.paging,  # type: ignore[arg-type]
        counters_model=ProxiesCounters,
        counters=counters,
    )


@router.get(
    "/proxies/raw",
    name="proxies:get_raw_proxies",
    status_code=status.HTTP_200_OK,
    summary="Выгрузка урлов проксей в сыром виде",
    description="Отдаёт урлы проксей одним текстовым буфером: каждый урл с новой строки",
    response_class=PlainTextResponse,
    responses={
        status.HTTP_200_OK: {
            "description": "Урлы проксей, каждый с новой строки",
            "content": {
                PLAIN_TEXT_MEDIA_TYPE: {
                    "schema": {"type": "string"},
                    "example": (
                        "https://proxy.lodkirmm.ru?server=1.2.3.4&port=443&secret=ee1337\n"
                        "https://ad1.arixo.shop?server=5.6.7.8&port=443&secret=ee7331"
                    ),
                }
            },
        }
    },
)
@inject
async def get_raw_proxies(
    proxy_service: Annotated[ProxyService, Depends(AsyncProvide[Container.services.proxy_service])],
    proxy_status: Annotated[
        ProxyStatusEnum | None, Query(..., alias="status", description="Какие прокси выгружать")
    ] = None,
) -> PlainTextResponse:

    raw_proxies = await proxy_service.get_raw_proxies_urls(status=proxy_status)

    return PlainTextResponse(content=raw_proxies, status_code=status.HTTP_200_OK)


@router.post(
    "/proxies",
    name="proxies:save_proxies",
    status_code=status.HTTP_200_OK,
    summary="Сохранение проксей",
    responses=build_responses(
        status_code=status.HTTP_200_OK,
        response_model=OkResponse[list[TelegramProxySerializer]],
        exceptions=(NoProxiesAddedAPIError,),
    ),
)
@inject
async def save_proxies(
    proxy_service: Annotated[ProxyService, Depends(AsyncProvide[Container.services.proxy_service])],
) -> OkResponse[list[TelegramProxySerializer]]:

    try:
        proxies = await proxy_service.add_new_proxies()
    except NoProxiesAddedException as exc:
        raise NoProxiesAddedAPIError() from exc
    return OkResponse.new(status_code=status.HTTP_200_OK, model=list[TelegramProxySerializer], data=proxies)


@router.delete(
    "/proxies",
    name="proxies:delete_all_proxies",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Удаление всех проксей из базы",
    responses=build_responses(status_code=status.HTTP_202_ACCEPTED, response_model=None),
)
@inject
async def delete_all_proxies(
    proxy_service: Annotated[ProxyService, Depends(AsyncProvide[Container.services.proxy_service])],
) -> None:

    await proxy_service.delete_all_proxies()


@router.patch(
    "/proxies/{proxy_id}",
    name="proxies:update_a_proxy",
    status_code=status.HTTP_200_OK,
    summary="Обновление прокси",
    responses=build_responses(
        status_code=status.HTTP_200_OK,
        response_model=OkResponse[TelegramProxySerializer],
        exceptions=(ResourceNotFoundByIDError,),
    ),
)
@inject
async def update_a_proxy(
    proxy_id: Annotated[int, Path(..., description="Id прокси")],
    body: Annotated[UpdateProxyRequestSerializer, Body(..., description="Тело запроса")],
    proxy_service: Annotated[ProxyService, Depends(AsyncProvide[Container.services.proxy_service])],
) -> OkResponse[TelegramProxySerializer]:

    try:
        proxy = await proxy_service.update_proxy(
            proxy_id=proxy_id, is_latency_update=body.is_latency_update, status=body.status
        )
    except ProxyNotFoundException as exc:
        raise ResourceNotFoundByIDError(resource_type=ResourceType.proxy, resource_id=proxy_id) from exc

    return OkResponse.new(status_code=status.HTTP_200_OK, model=TelegramProxySerializer, data=proxy)


@router.post(
    "/proxies/status",
    name="proxies:update_all_proxies",
    status_code=status.HTTP_200_OK,
    summary="Обновление статуса и латенси у всех проксей",
    responses=build_responses(
        status_code=status.HTTP_200_OK,
        response_model=None,
    ),
)
@inject
async def update_all_proxies(
    proxy_service: Annotated[ProxyService, Depends(AsyncProvide[Container.services.proxy_service])],
) -> None:
    await proxy_service.update_all_proxies()
