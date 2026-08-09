from collections.abc import Generator, Sequence
from dataclasses import dataclass
from typing import Any

from sqlakeyset.columns import OC, find_order_key
from sqlakeyset.results import Page, Paging, serialize_bookmark, unserialize_bookmark
from sqlakeyset.serial import InvalidPage
from sqlakeyset.serial.serial import bindecode, binencode
from sqlalchemy import tuple_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select
from sqlalchemy.sql.elements import ClauseList
from sqlalchemy.util import EMPTY_DICT
from starlette.datastructures import URL


@dataclass(slots=True, kw_only=True)
class CursorPagination:
    limit: int = 10
    backwards: bool = False
    page: str | None = None
    before: str | None = None
    after: str | None = None
    request_url: URL | None = None

    def __post_init__(self) -> None:
        if self.before is not None and self.after is not None:
            raise InvalidPage("please specify after OR before in query params")
        page = self.before or self.after
        if page:
            try:
                page = bindecode(page).decode()  # type: ignore[no-untyped-call]
            except (TypeError, ValueError) as exc:
                raise InvalidPage from exc
            page, backwards = unserialize_bookmark(page)  # type: ignore[assignment]
            self.page = page
            self.backwards = backwards


class URLBase64CursorPaging(Paging[Any]):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        request_url = kwargs.pop("request_url", None)
        super().__init__(*args, **kwargs)
        self.request_url: URL | None = request_url

    @staticmethod
    def encode_b64(page: tuple[Any, bool]) -> str:
        return binencode(serialize_bookmark(page).encode("utf-8"))  # type: ignore[no-untyped-call]

    @property
    def next_b64(self) -> str | None:
        return self.encode_b64(self.next) if self.has_next else None

    @property
    def previous_b64(self) -> str | None:
        return self.encode_b64(self.previous) if self.has_previous else None

    @staticmethod
    def build_url(url: URL, key: str, value: str) -> str:
        key_to_remove = "after" if key == "before" else "before"
        url = url.remove_query_params(key_to_remove)
        url = url.include_query_params(**{key: value})
        return url.path + "?" + url.query

    @property
    def next_page(self) -> str | None:
        if self.next_b64 is not None and self.request_url is not None:
            return self.build_url(self.request_url, "after", self.next_b64)
        return None

    @property
    def previous_page(self) -> str | None:
        if self.previous_b64 is not None and self.request_url is not None:
            return self.build_url(self.request_url, "before", self.previous_b64)
        return None


@dataclass(slots=True, kw_only=True)
class OffsetPagination:
    limit: int
    offset: int
    request_url: URL | None = None

    @property
    def is_first_page(self) -> bool:
        return self.offset == 0

    def _get_page_uri(self, offset: int | None) -> str | None:
        if offset is None or offset < 0 or self.request_url is None:
            return None
        url = self.request_url.remove_query_params("offset")
        url = url.include_query_params(**{"offset": offset})  # noqa: PIE804
        return url.path + "?" + url.query

    def build_pages(self, next_offset: int | None) -> tuple[str | None, str | None]:
        next_page = self._get_page_uri(next_offset)
        previous_offset = self.offset - self.limit
        previous_page = self._get_page_uri(previous_offset)
        return previous_page, next_page


class OffsetPaging:
    def __init__(self, *, rows: Sequence[Any], limit: int, offset: int, request_url: URL | None):
        self.limit = limit
        self.offset = offset
        self.request_url = request_url

        self.source_rows = rows
        self.has_next = bool(rows[limit:])

    @property
    def has_previous(self) -> bool:
        return bool(self.offset >= self.limit)

    @property
    def next_offset(self) -> int | None:
        if self.has_next:
            return self.offset + self.limit
        return None

    @property
    def previous_offset(self) -> int | None:
        if self.has_previous:
            return self.offset - self.limit
        return None

    @property
    def next_page(self) -> str | None:
        if self.next_offset is not None and self.request_url is not None:
            return self._build_url(self.request_url, "offset", self.next_offset)
        return None

    @property
    def previous_page(self) -> str | None:
        if self.previous_offset is not None and self.request_url is not None:
            return self._build_url(self.request_url, "offset", self.previous_offset)
        return None

    @property
    def rows(self) -> Sequence[Any]:
        return self.source_rows[: self.limit]

    @staticmethod
    def _build_url(url: URL, key: str, value: int) -> str:
        url = url.remove_query_params("offset")
        url = url.include_query_params(**{key: value})
        return url.path + "?" + url.query


def where_condition_for_page(session: AsyncSession, ordering_columns: list[OC], place: str) -> Any:
    """Construct the SQL condition required to restrict a selectable to the
    desired page.

    :param ordering_columns: The query's ordering columns
    :param place: The starting position for the page
    :returns: An SQLAlchemy expression suitable for use in `.filter` or `.having`.
    Raises:
        InvalidPage: If `place` does not correspond to the given OCs.
    """

    if len(ordering_columns) != len(place):
        raise InvalidPage("Page marker has different column count to query's order clause")

    dialect = session.bind.dialect
    zipped = zip(ordering_columns, place)  # noqa: B905
    swapped = [c.pair_for_comparison(value, dialect) for c, value in zipped]
    row, place_row = zip(*swapped)  # noqa: B905

    if len(row) == 1:
        return row[0] > place_row[0]

    return tuple_(*row) > tuple_(*place_row)


def parse_ob_clause(selectable: Select[Any], backwards: bool) -> list[OC]:
    """Parse the ORDER BY clause of a selectable into a list of :class:`OC`
    instances."""

    def _flatten(cl: ClauseList | Any) -> Generator[ClauseList]:
        if isinstance(cl, ClauseList):
            for subclause in cl.clauses:
                yield from _flatten(subclause)
        elif isinstance(cl, (tuple, list)):
            for xs in cl:
                yield from _flatten(xs)
        else:
            yield cl

    result = [OC(c) for c in _flatten(selectable._order_by_clauses)]  # type: ignore[no-untyped-call]
    if backwards:
        result = [c.reversed for c in result]
    return result


async def core_get_page(
    session: AsyncSession,
    selectable: Select[Any],
    pagination: CursorPagination | OffsetPagination,
    only_ids: bool = False,
    as_dicts: bool = False,
    unique: bool = False,
    as_model: bool = False,
    execution_options: dict[str, Any] | None = None,
) -> Page[Any]:
    """Get a page from an SQLAlchemy Core selectable.

    WARNING! FOR CURSOR PAGINATION AT LEAST ONE FIELD IN ORDERING QUERY MUST BE UNIQUE!
    EXAMPLE: order_by(ArtSlice.rating{not unique field}, ArtSlice.art_id{unique field})

    Args:
        :param selectable: The :class:`Select` to paginate.
        :param session: Database session to execute select query on
        :param pagination: CursorPagination or OffsetPagination object coming from url queries.
        :param only_ids: If True, returns list of ints, not list of tuples. Use it if you select only object ids.
        :param as_model: If True, function returns list of Sqlalchemy models, you must select only one model type!
        :param as_dicts: If True, function returns list of dicts.
        :param unique: If True, functon returns only unique values
        :param execution_options: For provide specific execution options
    Returns:
        The result page.
    """

    if isinstance(pagination, OffsetPagination):
        return await core_get_page_offset(
            session=session,
            selectable=selectable,
            pagination=pagination,
            only_ids=only_ids,
            as_dicts=as_dicts,
            unique=unique,
            as_model=as_model,
            execution_options=execution_options,
        )

    return await core_get_page_cursor(
        session=session,
        selectable=selectable,
        pagination=pagination,
        only_ids=only_ids,
        as_dicts=as_dicts,
        unique=unique,
        as_model=as_model,
        execution_options=execution_options,
    )


async def core_get_page_cursor(
    session: AsyncSession,
    selectable: Select[Any],
    pagination: CursorPagination,
    only_ids: bool = False,
    as_dicts: bool = False,
    unique: bool = False,
    as_model: bool = False,
    execution_options: dict[str, Any] | None = None,
) -> Page[Any]:
    if execution_options is None:
        execution_options = EMPTY_DICT
    """Get a page from an SQLAlchemy Core selectable.

    WARNING! AT LEAST ONE FIELD IN ORDERING QUERY MUST BE UNIQUE!
    EXAMPLE: order_by(ArtSlice.rating{not unique field}, ArtSlice.art_id{unique field})

    Args:
        :param selectable: The :class:`Select` to paginate.
        :param session: Database session to execute select query on
        :param pagination: CursorPagination object coming from url queries.
        :param only_ids: If True, returns list of ints, not list of tuples. Use it if you select only object ids.
        :param as_model: If True, function returns list of Sqlalchemy models, you must select only one model type!
        :param as_dicts: If True, function returns list of dicts.
        :param unique: If True, functon returns only unique values
            :param pagination.place: Keyset representing the place after which to start the page.
            :param pagination.limit: Number of rows per page.
            :param pagination.backwards: If ``True``, reverse pagination direction.
    Returns:
        The result page.
    """

    per_page = pagination.limit
    place = pagination.page
    backwards = pagination.backwards
    # Build a list of ordering columns (ocols) in the form of `MappedOrderColumn` objects.
    order_cols = parse_ob_clause(selectable, backwards)
    mapped_ocols = [find_order_key(ocol, selectable.column_descriptions) for ocol in order_cols]
    request_url = pagination.request_url

    # Update the selectable with the new order_by clauses.
    new_order_by_clauses = [col.ob_clause for col in mapped_ocols]
    selectable = selectable.order_by(None).order_by(*new_order_by_clauses)

    # Add the extra columns required for the ordering.
    extra_columns = [col.extra_column for col in mapped_ocols if col.extra_column is not None]
    selectable = selectable.add_columns(*extra_columns)

    if place:
        # Prepare the condition for selecting a specific page.
        condition = where_condition_for_page(session, order_cols, place)

        # If there is at least one GROUP BY clause, we have an aggregate query.
        # In this case, the paging condition is applied AFTER aggregation. To do so, we must use HAVING and not FILTER.
        if selectable._group_by_clauses:  # noqa: SIM108
            selectable = selectable.having(condition)
        else:
            selectable = selectable.where(condition)

    # Limit the amount of results in the page. The 1 extra is to check if there's a further page.
    selectable = selectable.limit(per_page + 1)

    # Run the selectable and get back the query rows.
    # NOTE: Do not use `.scalars` here, as it might lead to some rows being omitted by the ORM.
    selected = await session.execute(selectable, execution_options=execution_options)
    row_keys = list(selected.keys())
    if unique:  # noqa: SIM108
        rows = selected.unique().all()
    else:
        rows = selected.all()

    # Finally, construct the `Page` object.
    # Trim off the extra columns and return as a correct-as-possible sqlalchemy Row.
    if only_ids:
        out_rows = [row[0] for row in rows]
    elif as_dicts:
        out_rows = [
            dict(
                zip(  # noqa: B905
                    row_keys[: -len(extra_columns) or None],
                    row[: -len(extra_columns) or None],
                ),
            )
            for row in rows
        ]
    elif as_model:
        out_rows = [row[: -len(extra_columns) or None][0] for row in rows]
    else:
        out_rows = rows  # type: ignore[assignment]

    key_rows = [tuple(col.get_from_row(row) for col in mapped_ocols) for row in rows]  # type: ignore[no-untyped-call]
    paging = URLBase64CursorPaging(
        rows=out_rows,
        per_page=per_page,
        backwards=backwards,
        current_place=place,
        places=key_rows,
        request_url=request_url,
    )
    return Page(paging.rows, paging, keys=row_keys[: -len(extra_columns) or None])


async def core_get_page_offset(
    session: AsyncSession,
    selectable: Select[Any],
    pagination: OffsetPagination,
    only_ids: bool = False,
    as_dicts: bool = False,
    unique: bool = False,
    as_model: bool = False,
    execution_options: dict[str, Any] | None = None,
) -> Page[Any]:
    if execution_options is None:
        execution_options = EMPTY_DICT
    """Get a page from an SQLAlchemy Core selectable.

    Args:
        :param selectable: The :class:`Select` to paginate.
        :param session: Database session to execute select query on
        :param pagination: CursorPagination or OffsetPagination object coming from url queries.
        :param only_ids: If True, returns list of ints, not list of tuples. Use it if you select only object ids.
        :param as_model: If True, function returns list of Sqlalchemy models, you must select only one model type!
        :param as_dicts: If True, function returns list of dicts.
        :param unique: If True, functon returns only unique values
    Returns:
        The result page.
    """

    limit = pagination.limit
    offset = pagination.offset

    # Limit the amount of results in the page. The 1 extra is to check if there's a further page.
    selectable = selectable.limit(limit + 1)

    if offset:
        selectable = selectable.offset(offset)

    # Run the selectable and get back the query rows.
    # NOTE: Do not use `.scalars` here, as it might lead to some rows being omitted by the ORM.
    selected = await session.execute(selectable, execution_options=execution_options)
    row_keys = list(selected.keys())
    if unique:  # noqa: SIM108
        rows = selected.unique().all()
    else:
        rows = selected.all()

    # Prepare rows format as requested
    if only_ids:
        out_rows = [row[0] for row in rows]
    elif as_dicts:
        out_rows = [dict(zip(row_keys, row)) for row in rows]  # noqa: B905
    elif as_model:
        out_rows = [row[0] for row in rows]
    else:
        out_rows = rows  # type: ignore[assignment]

    # Construct `Page` object
    paging = OffsetPaging(
        rows=out_rows,
        limit=limit,
        offset=offset,
        request_url=pagination.request_url,
    )
    return Page(paging.rows, paging, keys=row_keys)  # type: ignore[arg-type]
