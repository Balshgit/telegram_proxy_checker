from http import HTTPStatus
from typing import Annotated

from dependency_injector.wiring import inject
from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger
from sqlalchemy import literal, select
from starlette.responses import JSONResponse

from app.api.router import TPCAPIRoute
from app.di.dependency_injector import AsyncProvide, Container
from app.infra.sqlalchemy.engines import DatabaseEngines

router = APIRouter(route_class=TPCAPIRoute)


@router.get(
    "/healthcheck",
    name="system:healthcheck",
    status_code=HTTPStatus.OK,
    summary="Healthcheck",
)
async def healthcheck() -> JSONResponse:
    return JSONResponse(content=None, status_code=status.HTTP_200_OK)


@router.get(
    "/readiness-check",
    name="system:readiness-check",
    status_code=HTTPStatus.OK,
    summary="Readiness check",
)
@inject
async def readiness_check(
    database_engines: Annotated[DatabaseEngines, Depends(AsyncProvide[Container.infra.database_engines])],
) -> JSONResponse:

    query = select(literal("1").label("status"))
    try:
        async with database_engines.db.session() as session:
            result = await session.execute(query)
            result.scalar_one()
    except Exception as exc:
        logger.error(exc)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE) from exc

    return JSONResponse(content=None, status_code=status.HTTP_200_OK)
