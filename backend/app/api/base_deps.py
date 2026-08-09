from typing import Annotated

from fastapi import Query, Request
from pydantic.types import NaiveDatetime
from sqlakeyset import InvalidPage

from app.api.exceptions import RequestParamValidationError
from app.core.pagination import CursorPagination, OffsetPagination


async def get_cursor_pagination(
    request: Request,
    limit: int = Query(default=10, le=100, gt=0, description="Лимит, максимальное значение: 100"),
    before: str | None = Query(
        None,
        description=(
            "Значение в base64 для вывода предыдущей страницы. Можно получить из тела ответа в параметре "
            "***pagination.previous_page***. Если передаем before, то нельзя передавать after в одном запросе."
        ),
    ),
    after: str | None = Query(
        None,
        description=(
            "Значение в base64 для вывода следующей страницы. Можно получить из тела ответа в параметре"
            " ***pagination.next_page***. Если передаем after, то нельзя передавать before в одном запросе."
        ),
    ),
) -> CursorPagination:
    try:
        page = CursorPagination(limit=limit, before=before, after=after, request_url=request.url)
    except InvalidPage as exc:
        raise RequestParamValidationError(detail="Malformed cursor information") from exc
    return page


async def get_offset_pagination(
    request: Request,
    offset: int = Query(default=0, ge=0, description="Пропустить первые в выдаче N объектов до этого значения"),
    limit: int = Query(
        default=10,
        ge=1,
        le=100,
        description="Верхний лимит объектов в выдаче, максимальное значение 100",
    ),
) -> OffsetPagination:
    """Default offset pagination"""
    return OffsetPagination(limit=limit, offset=offset, request_url=request.url)


async def get_since_and_until(
    since: Annotated[
        NaiveDatetime | None,
        Query(description="Отфильтровать данные после даты в iso формате", examples=["2024-01-01"]),
    ] = None,
    until: Annotated[
        NaiveDatetime | None,
        Query(description="Отфильтровать данные до даты в iso формате", examples=["2024-01-01"]),
    ] = None,
) -> dict[str, NaiveDatetime | None]:
    if since is not None and until is not None and since > until:
        raise RequestParamValidationError(detail="since > until")
    return {"since": since, "until": until}
