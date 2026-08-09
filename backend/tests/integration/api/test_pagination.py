from typing import Annotated, Any

import pytest
from fastapi import Depends, FastAPI
from httpx import AsyncClient
from starlette import status

from app.api.base_deps import get_cursor_pagination, get_offset_pagination
from app.core.pagination import CursorPagination, OffsetPagination


@pytest.mark.parametrize("params", [{"before": 123}, {"before": "PGa", "after": "PGa"}])
async def test_pagination_wrong_cursor(
    params: dict[str, int | str],
    fastapi_app: FastAPI,
    rest_client: AsyncClient,
) -> None:
    route = "/test-cursor-pagination-incorrect-params"
    query_params = {"limit": 1}
    query_params.update(params)

    @fastapi_app.get(route, status_code=status.HTTP_200_OK)
    def test_cursor_pagination_are_incorrect_params(
        pagination: Annotated[CursorPagination, Depends(get_cursor_pagination)],
    ) -> None:
        assert pagination.limit == 10

    response = await rest_client.get(route, params=query_params)

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "detail": "Malformed cursor information",
            "title": "Validation error because of request parameters",
            "type": "ParamValidationError",
            "meta": {"message": None},
        },
        "status": 422,
    }
    replaced_pagination_route = next(
        filter(lambda r: getattr(r, "path", None) == route, fastapi_app.routes)  # type: ignore[arg-type, attr-defined]
    )
    fastapi_app.routes.remove(replaced_pagination_route)


@pytest.mark.parametrize(
    "query_params, error_descriptions",
    [
        pytest.param(
            {"limit": 42, "offset": "PGa"},
            [
                {
                    "loc": ["query", "offset"],
                    "msg": "Input should be a valid integer, unable to parse string as an integer",
                    "type": "int_parsing",
                },
            ],
            id="incorrect offset",
        ),
        pytest.param(
            {"limit": "PGa", "offset": 42},
            [
                {
                    "loc": ["query", "limit"],
                    "msg": "Input should be a valid integer, unable to parse string as an integer",
                    "type": "int_parsing",
                },
            ],
            id="incorrect limit",
        ),
        pytest.param(
            {"limit": "PGa", "offset": "PGa"},
            [
                {
                    "loc": ["query", "limit"],
                    "msg": "Input should be a valid integer, unable to parse string as an integer",
                    "type": "int_parsing",
                },
                {
                    "loc": ["query", "offset"],
                    "msg": "Input should be a valid integer, unable to parse string as an integer",
                    "type": "int_parsing",
                },
            ],
            id="incorrect offset and limit",
        ),
    ],
)
async def test_pagination_wrong_offset(
    fastapi_app: FastAPI,
    rest_client: AsyncClient,
    query_params: dict[str, int | str],
    error_descriptions: list[dict[str, Any]],
) -> None:
    route = "/test-offset-pagination-incorrect-params"

    @fastapi_app.get(route, status_code=status.HTTP_200_OK)
    def test_offset_pagination_incorrect_params(
        pagination: Annotated[OffsetPagination, Depends(get_offset_pagination)],
    ) -> None:
        assert pagination.limit == 10

    response = await rest_client.get(route, params=query_params)

    assert response.status_code == 422
    payload = response.json()
    payload["error"]["error_descriptions"].sort(key=lambda e: e["loc"][1])
    assert payload == {
        "error": {
            "detail": "Received a validation error while interpreting request "
            "parameters. See error_descriptions for details",
            "error_descriptions": error_descriptions,
            "title": "Validation error because of request parameters",
            "type": "ParamValidationError",
            "meta": {"message": None},
        },
        "status": 422,
    }
    replaced_pagination_route = next(
        filter(lambda r: getattr(r, "path", None) == route, fastapi_app.routes)  # type: ignore[arg-type, attr-defined]
    )
    fastapi_app.routes.remove(replaced_pagination_route)
