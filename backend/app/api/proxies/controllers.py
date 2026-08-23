from datetime import datetime
from typing import Annotated

from dependency_injector.wiring import inject
from fastapi import APIRouter, Body, Depends, Path, Query
from fastapi.responses import PlainTextResponse
from httpx import URL
from starlette import status

from app.api.base_deps import get_offset_pagination
from app.api.base_schemas import OkResponse, PaginationResponseWithCounters
from app.api.constants import PLAIN_TEXT_MEDIA_TYPE
from app.api.exceptions import ResourceNotFoundByIDError
from app.api.proxies.exceptions import NoProxiesAddedAPIError
from app.api.proxies.serializers import (
    AddProxySourceRequestSerializer,
    ProxiesCounters,
    ProxySourceSerializer,
    SaveProxiesRequestSerializer,
    TelegramProxySerializer,
    UpdateProxyRequestSerializer,
    UpdateProxySourceRequestSerializer,
)
from app.api.responses import build_responses
from app.api.router import TPCAPIRoute
from app.core.constants import ResourceType
from app.core.pagination import OffsetPagination
from app.core.proxies.constants import ProxyOrderByEnum, ProxySourceStatusEnum, ProxyStatusEnum
from app.core.proxies.dto import ProxyFilterDTO, ProxySourceDTO, ProxySourceUpdateDTO
from app.core.proxies.exceptions import NoProxiesAddedException, ProxyNotFoundException, ProxySourceNotFoundException
from app.core.proxies.services import ProxyService
from app.core.shared.types import Missing
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
    pagination: Annotated[OffsetPagination, Depends(get_offset_pagination)],
    order_by: Annotated[ProxyOrderByEnum, Query(..., description="Сортировать прокси")] = ProxyOrderByEnum.latency,
    created_from: Annotated[
        datetime | None, Query(..., description="Фильтровать от той даты, когда урлы прокси были создан")
    ] = None,
    created_to: Annotated[
        datetime | None, Query(..., description="Фильтровать до той даты, когда урлы прокси были создан")
    ] = None,
    proxy_status: Annotated[ProxyStatusEnum | None, Query(..., description="Фильтр по статусу")] = None,
) -> PaginationResponseWithCounters[TelegramProxySerializer, ProxiesCounters]:

    filters = ProxyFilterDTO(created_from=created_from, created_to=created_to, status=proxy_status)

    proxies_page, counters = await proxy_service.get_all_proxies(
        pagination=pagination, filters=filters, order_by=order_by
    )

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


@router.get(
    "/proxies/sources",
    name="proxies:get_proxies_sources",
    status_code=status.HTTP_200_OK,
    summary="Получение списка источников проксей",
    responses=build_responses(
        status_code=status.HTTP_200_OK,
        response_model=OkResponse[list[ProxySourceSerializer]],
    ),
)
@inject
async def get_proxies_sources(
    proxy_service: Annotated[ProxyService, Depends(AsyncProvide[Container.services.proxy_service])],
    source_status: Annotated[
        ProxySourceStatusEnum | None, Query(..., alias="status", description="Фильтр по статусу источника")
    ] = None,
) -> OkResponse[list[ProxySourceSerializer]]:

    proxies_sources = await proxy_service.get_proxies_sources(status=source_status)

    return OkResponse.new(
        status_code=status.HTTP_200_OK,
        model=list[ProxySourceSerializer],
        data=[ProxySourceSerializer.model_validate(source) for source in proxies_sources],
    )


@router.post(
    "/proxies/sources",
    name="proxies:add_proxies_source",
    status_code=status.HTTP_201_CREATED,
    summary="Добавление источника проксей",
    responses=build_responses(
        status_code=status.HTTP_201_CREATED,
        response_model=OkResponse[ProxySourceSerializer],
    ),
)
@inject
async def add_proxies_source(
    body: Annotated[AddProxySourceRequestSerializer, Body(..., description="Тело запроса")],
    proxy_service: Annotated[ProxyService, Depends(AsyncProvide[Container.services.proxy_service])],
) -> OkResponse[ProxySourceSerializer]:

    proxy_source = await proxy_service.add_proxies_source(
        proxy_source_dto=ProxySourceDTO(
            name=body.name,
            url=URL(str(body.url)),
            status=body.status,
            vendor=body.vendor,
        )
    )

    return OkResponse.new(
        status_code=status.HTTP_201_CREATED,
        model=ProxySourceSerializer,
        data=ProxySourceSerializer.model_validate(proxy_source),
    )


@router.patch(
    "/proxies/sources/{source_id}",
    name="proxies:update_proxies_source",
    status_code=status.HTTP_200_OK,
    summary="Обновление источника проксей",
    responses=build_responses(
        status_code=status.HTTP_200_OK,
        response_model=OkResponse[ProxySourceSerializer],
        exceptions=(ResourceNotFoundByIDError,),
    ),
)
@inject
async def update_proxies_source(
    source_id: Annotated[int, Path(..., description="ID источника проксей")],
    body: Annotated[UpdateProxySourceRequestSerializer, Body(..., description="Тело запроса")],
    proxy_service: Annotated[ProxyService, Depends(AsyncProvide[Container.services.proxy_service])],
) -> OkResponse[ProxySourceSerializer]:

    # `None` в теле означает "поле не меняем", поэтому наружу оно уезжает как `Missing`.
    proxy_source_update_dto = ProxySourceUpdateDTO(
        name=body.name if body.name is not None else Missing,
        url=URL(str(body.url)) if body.url is not None else Missing,
        status=body.status if body.status is not None else Missing,
        vendor=body.vendor if body.vendor is not None else Missing,
    )

    try:
        proxy_source = await proxy_service.update_proxies_source(
            proxy_source_id=source_id, proxy_source_update_dto=proxy_source_update_dto
        )
    except ProxySourceNotFoundException as exc:
        raise ResourceNotFoundByIDError(resource_type=ResourceType.proxy_source, resource_id=source_id) from exc

    return OkResponse.new(
        status_code=status.HTTP_200_OK,
        model=ProxySourceSerializer,
        data=ProxySourceSerializer.model_validate(proxy_source),
    )


@router.delete(
    "/proxies/sources/{source_id}",
    name="proxies:delete_proxies_source",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удаление источника проксей",
    description="Прокси, собранные из этого источника, остаются в базе и теряют привязку к нему",
    responses=build_responses(status_code=status.HTTP_204_NO_CONTENT, response_model=None),
)
@inject
async def delete_proxies_source(
    source_id: Annotated[int, Path(..., description="ID источника проксей")],
    proxy_service: Annotated[ProxyService, Depends(AsyncProvide[Container.services.proxy_service])],
) -> None:

    await proxy_service.delete_proxies_source(proxy_source_id=source_id)


@router.get(
    "/proxies/{proxy_id}",
    name="proxies:get_a_proxy",
    status_code=status.HTTP_200_OK,
    summary="Получение детальной информации по одной прокси",
    responses=build_responses(
        status_code=status.HTTP_200_OK,
        response_model=OkResponse[TelegramProxySerializer],
        exceptions=(ResourceNotFoundByIDError,),
    ),
)
@inject
async def get_a_proxy(
    proxy_id: Annotated[int, Path(..., description="ID прокси")],
    proxy_service: Annotated[ProxyService, Depends(AsyncProvide[Container.services.proxy_service])],
) -> OkResponse[TelegramProxySerializer]:

    try:
        proxy = await proxy_service.get_proxy(proxy_id=proxy_id)
    except ProxyNotFoundException as exc:
        raise ResourceNotFoundByIDError(resource_type=ResourceType.proxy, resource_id=proxy_id) from exc

    return OkResponse.new(
        status_code=status.HTTP_200_OK,
        model=TelegramProxySerializer,
        data=TelegramProxySerializer.model_validate(proxy),
    )


@router.post(
    "/proxies",
    name="proxies:save_proxies",
    status_code=status.HTTP_201_CREATED,
    summary="Сохранение проксей",
    description=(
        "Собирает прокси из включённых источников. Если `source_ids` не передан или пуст — "
        "обходятся все включённые источники"
    ),
    responses=build_responses(
        status_code=status.HTTP_201_CREATED,
        response_model=None,
        exceptions=(NoProxiesAddedAPIError,),
    ),
)
@inject
async def save_proxies(
    proxy_service: Annotated[ProxyService, Depends(AsyncProvide[Container.services.proxy_service])],
    body: Annotated[SaveProxiesRequestSerializer | None, Body(description="Тело запроса")] = None,
) -> None:

    sources_ids = set(body.source_ids) if body and body.source_ids else None

    try:
        await proxy_service.add_new_proxies(sources_ids=sources_ids)
    except NoProxiesAddedException as exc:
        raise NoProxiesAddedAPIError() from exc


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


@router.delete(
    "/proxies/{proxy_id}",
    name="proxies:delete_a_proxy",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удаление одной прокси из базы",
    responses=build_responses(status_code=status.HTTP_204_NO_CONTENT, response_model=None),
)
@inject
async def delete_a_proxy(
    proxy_id: Annotated[int, Path(..., description="ID прокси для удаления")],
    proxy_service: Annotated[ProxyService, Depends(AsyncProvide[Container.services.proxy_service])],
) -> None:

    await proxy_service.delete_proxy_by_id(proxy_id=proxy_id)


@router.patch(
    "/proxies/{proxy_id}",
    name="proxies:update_a_proxy",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Обновление прокси",
    responses=build_responses(
        status_code=status.HTTP_202_ACCEPTED,
        response_model=None,
        exceptions=(ResourceNotFoundByIDError,),
    ),
)
@inject
async def update_a_proxy(
    proxy_id: Annotated[int, Path(..., description="Id прокси")],
    body: Annotated[UpdateProxyRequestSerializer, Body(..., description="Тело запроса")],
    proxy_service: Annotated[ProxyService, Depends(AsyncProvide[Container.services.proxy_service])],
) -> None:

    try:
        await proxy_service.update_proxy(
            proxy_id=proxy_id, is_latency_update=body.is_latency_update, status=body.status
        )
    except ProxyNotFoundException as exc:
        raise ResourceNotFoundByIDError(resource_type=ResourceType.proxy, resource_id=proxy_id) from exc


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
