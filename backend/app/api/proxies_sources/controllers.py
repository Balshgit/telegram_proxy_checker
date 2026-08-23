from typing import Annotated

from dependency_injector.wiring import inject
from fastapi import APIRouter, Body, Depends, Path, Query
from httpx import URL
from starlette import status

from app.api.base_schemas import OkResponse
from app.api.exceptions import RequestParamValidationError, ResourceNotFoundByIDError
from app.api.proxies_sources.serializers import (
    AddProxySourceRequestSerializer,
    ProxySourceSerializer,
    UpdateProxySourceRequestSerializer,
)
from app.api.responses import build_responses
from app.api.router import TPCAPIRoute
from app.core.constants import ResourceType
from app.core.proxies_sources.constants import ProxySourceStatusEnum
from app.core.proxies_sources.dto import ProxySourceDTO, ProxySourceUpdateDTO
from app.core.proxies_sources.exceptions import ProxySourceNotFoundException
from app.core.proxies_sources.services import ProxySourceService
from app.core.shared.types import Missing
from app.di.dependency_injector import AsyncProvide, Container

router = APIRouter(route_class=TPCAPIRoute)


@router.get(
    "/proxies/sources",
    name="proxies_sources:get_proxies_sources",
    status_code=status.HTTP_200_OK,
    summary="Получение списка источников проксей",
    responses=build_responses(
        status_code=status.HTTP_200_OK,
        response_model=OkResponse[list[ProxySourceSerializer]],
    ),
)
@inject
async def get_proxies_sources(
    proxy_source_service: Annotated[ProxySourceService, Depends(AsyncProvide[Container.services.proxy_source_service])],
    source_status: Annotated[
        ProxySourceStatusEnum | None, Query(..., alias="status", description="Фильтр по статусу источника")
    ] = None,
) -> OkResponse[list[ProxySourceSerializer]]:

    proxies_sources = await proxy_source_service.get_proxies_sources(status=source_status)

    return OkResponse.new(status_code=status.HTTP_200_OK, model=list[ProxySourceSerializer], data=proxies_sources)


@router.post(
    "/proxies/sources",
    name="proxies_sources:add_proxies_source",
    status_code=status.HTTP_201_CREATED,
    summary="Добавление источника проксей",
    responses=build_responses(
        status_code=status.HTTP_201_CREATED,
        response_model=None,
    ),
)
@inject
async def add_proxies_source(
    body: Annotated[AddProxySourceRequestSerializer, Body(..., description="Тело запроса")],
    proxy_source_service: Annotated[ProxySourceService, Depends(AsyncProvide[Container.services.proxy_source_service])],
) -> None:

    await proxy_source_service.add_proxies_source(
        proxy_source_dto=ProxySourceDTO(
            name=body.name,
            url=URL(str(body.url)),
            status=body.status,
            vendor=body.vendor,
        )
    )


@router.patch(
    "/proxies/sources/{source_id}",
    name="proxies_sources:update_proxies_source",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Обновление источника проксей",
    responses=build_responses(
        status_code=status.HTTP_204_NO_CONTENT,
        response_model=None,
        exceptions=(ResourceNotFoundByIDError, RequestParamValidationError),
    ),
)
@inject
async def update_proxies_source(
    source_id: Annotated[int, Path(..., description="ID источника проксей")],
    body: Annotated[UpdateProxySourceRequestSerializer, Body(..., description="Тело запроса")],
    proxy_source_service: Annotated[ProxySourceService, Depends(AsyncProvide[Container.services.proxy_source_service])],
) -> None:

    # `None` в теле означает "поле не меняем", поэтому наружу оно уезжает как `Missing`.
    proxy_source_update_dto = ProxySourceUpdateDTO(
        name=body.name if body.name else Missing,
        url=URL(str(body.url)) if body.url else Missing,
        status=body.status if body.status else Missing,
        vendor=body.vendor if body.vendor else Missing,
    )

    try:
        await proxy_source_service.update_proxies_source(
            proxy_source_id=source_id, proxy_source_update_dto=proxy_source_update_dto
        )
    except ProxySourceNotFoundException as exc:
        raise ResourceNotFoundByIDError(resource_type=ResourceType.proxy_source, resource_id=source_id) from exc


@router.delete(
    "/proxies/sources/{source_id}",
    name="proxies_sources:delete_proxies_source",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удаление источника проксей",
    description="Прокси, собранные из этого источника, остаются в базе и теряют привязку к нему",
    responses=build_responses(
        status_code=status.HTTP_204_NO_CONTENT, response_model=None, exceptions=(RequestParamValidationError,)
    ),
)
@inject
async def delete_proxies_source(
    source_id: Annotated[int, Path(..., description="ID источника проксей")],
    proxy_source_service: Annotated[ProxySourceService, Depends(AsyncProvide[Container.services.proxy_source_service])],
) -> None:

    await proxy_source_service.delete_proxies_source(proxy_source_id=source_id)
