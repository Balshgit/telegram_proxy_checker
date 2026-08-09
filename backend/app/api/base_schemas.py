from collections.abc import Callable
from typing import Annotated, Any, Generic, TypeAlias, TypeVar

from fastapi import status
from pydantic import BaseModel, ConfigDict, Field, model_serializer

from app.core.pagination import OffsetPaging, URLBase64CursorPaging

_Model = TypeVar("_Model")
_CountersModel = TypeVar("_CountersModel")
GenericResponse: TypeAlias = BaseModel  # noqa: UP040


class CountersResponse(BaseModel):
    all: Annotated[int, Field(..., ge=0, description="Полный счётчик всех сущностей")]


class UnsetType(BaseModel):
    def __repr__(self) -> str:
        return "Unset"


Unset = UnsetType()


class DataResponse(GenericResponse, Generic[_Model]):  # noqa: UP046
    data: Annotated[_Model, Field(..., title="data")]


class ErrorMeta(BaseModel):
    message: Annotated[
        str | None,
        Field(
            title="User-friendly description", examples=["Слишком короткое значение: минимум 15 символов (сейчас: 10)."]
        ),
    ] = None

    @model_serializer(mode="wrap")
    def _serialize_with_message_key_always_present(
        self, serialization_handler: Callable[[Any], dict[str, Any]]
    ) -> dict[str, Any]:
        """Guarantees message is None even if exclude_none=True."""
        serialized_value = serialization_handler(self)
        serialized_value["message"] = self.message
        return serialized_value


class BaseError(BaseModel):
    type: Annotated[str | None, Field(title="The name of the class of the error")] = None
    title: Annotated[
        str | None,
        Field(
            title="A short, human-readable summary of the problem that does not change from occurence to occurence",
        ),
    ] = None
    detail: Annotated[
        str | None,
        Field(title="А human-readable explanation specific to this occurrence of the problem"),
    ] = None
    instance: Annotated[
        Any | None,
        Field(title="Identifier for this specific occurrence of the problem"),
    ] = None
    meta: Annotated[
        ErrorMeta,
        Field(default_factory=ErrorMeta, title="Additional information"),
    ]

    @model_serializer(mode="wrap")
    def _serialize_with_meta_key_always_present(
        self,
        serialization_handler: Callable[[Any], dict[str, Any]],
    ) -> dict[str, Any]:
        serialized_value = serialization_handler(self)

        if "meta" not in serialized_value:
            serialized_value["meta"] = self.meta.model_dump(
                exclude_none=False,
                exclude_unset=False,
                exclude_defaults=False,
            )

        return serialized_value


class OkResponse(GenericResponse, Generic[_Model]):  # noqa: UP046
    status: Annotated[int, Field(..., title="Status code of request.", examples=[status.HTTP_200_OK])]
    error: Annotated[dict[Any, Any] | BaseError | None, Field(title="Errors")] = None
    payload: Annotated[DataResponse[_Model], Field(title="Payload data.")]

    @classmethod
    def new(
        cls,
        *,
        status_code: int,
        model: type[_Model] | list[type[_Model]] | Any,
        data: _Model | Any,
    ) -> OkResponse[_Model]:
        return cls[model](status=status_code, payload=DataResponse[model](data=data))  # type: ignore

    model_config = ConfigDict(json_schema_extra={"description": ""})


class BaseResponse(BaseModel):
    status: Annotated[int, Field(..., title="Status code of request.", examples=[status.HTTP_200_OK])]
    error: Annotated[dict[Any, Any] | BaseError | None, Field(None, title="Errors")]
    payload: Annotated[Any | None, Field(title="Payload data.", default_factory=dict)]


class BasePaginationSerializer(BaseModel):
    """Пагинация.

    Чтобы перейти на следующую страницу необходимо запросить URI из **pagination.next_page**.
    Для перехода на предыдущую необходимо использовать URI из **pagination.previous_page**.
    Значение **null** в полях **pagination.next_page** или **pagination.previous_page**
    сигнализирует об отсутствии следующей или предыдущей страницы соответственно.
    ```
    {
       "payload" : {
           "pagination": {
               "next_page": /api/arts?after=0NjUzNj&limit=5&o=new,
               "previous_page": null
           },
           "data": [ ... ]
    }
    ```

    Может использоваться курсорная либо оффсетная пагинация.
    ```
    {
       "payload" : {
           "pagination": {
              "next_page": "/api/arts?art_groups=0&limit=1&after=Pmk6Mn5pOjY5OTI2NTU0",
              "previous_page": "/api/arts?art_groups=0&limit=1&before=PGk6Mn5pOjY5OTI2NTU0"
            },
           "data": [ ... ]
    }
    {
       "payload" : {
           "pagination": {
             "next_page": "/api/arts?art_groups=0&limit=1&offset=2",
             "previous_page": "/api/arts?art_groups=0&limit=1&offset=0"
           },
           "data": [ ... ]
    }
    ```

    Для курсорной пагинации важно знать, что при переходах между страницами нужно использовать
    именно те URI следующей (**pagination.next_page**) и предыдущей (**pagination.previous_page**) страниц,
    поскольку значение курсора рассчитывается исходя из параметров
    (размер страницы, фильтры и параметры сортировки) запрошенной страницы.
    Изменение параметров приведет к неконсистентной выдаче или даже ошибке.

    То есть при запросе списка отзывов книг с такими параметрами
    ```
    > GET /api/arts?limit=5&o=new

    < 200 OK
    {
       "payload" : {
           "pagination": {
               "next_page": /api/arts?after=cD0xLjAwOTgyODY0NjUzNjMxMTU%3D&limit=5&o=new,
               "previous_page": null
           },
           "data": [ ... ]
    }
    ```

    следующая страница может быть запрошена только по URI **meta.next**:
    ```
    > GET /api/arts?after=cD0xLjAwOTgyODY0NjUzNjMxMTU%3D&limit=5&o=new

    < 200 OK
    ...
    ```

    Больше о преимуществах и недостатках офсетной и курсорной пагинации можно ознакомиться
    в статье [Evolving API Pagination at Slack](https://slack.engineering/evolving-api-pagination-at-slack-1c1f644f8e12)
    в техблоге Slack или в документации [json:api](https://jsonapi.org/profiles/ethanresnick/cursor-pagination/).
    """

    next_page: Annotated[
        str | None,
        Field(
            None,
            title="Курсор следующей страницы",
            description="url для перехода на следующую страницу",
            examples=["/api/arts?limit=10&after=Pmk6NX5pOjY1NzY0NzUw", "/api/arts?limit=10&offset=10"],
        ),
    ]
    previous_page: Annotated[
        str | None,
        Field(
            None,
            title="Курсор предыдущей страницы",
            description="url для перехода на предыдущую страницу",
            examples=["/api/arts?limit=10&before=PGk6NX5pOjY1OTAyNzM4", "/api/arts?limit=10&offset=0"],
        ),
    ]
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class DataPaginationResponse(GenericResponse, Generic[_Model]):  # noqa: UP046
    pagination: Annotated[BasePaginationSerializer, Field(..., title="pagination")]
    data: Annotated[list[_Model], Field(...)]


class PaginationResponse(GenericResponse, Generic[_Model]):  # noqa: UP046
    """
    Как использовать:

    # serializers.py
    >>> class UserID(BaseModel):
    >>>     user_id: Annotated[int, Field(..., example=12345)]


    # controllers.py
    >>> @router.get("/foo", response_model=PaginationResponse[UserID], status_code=200)
    >>> async def foo_func():
    >>>     page = Page([{"user_id": 123}, {"user_id": 235}])
    >>>     return PaginationResponse.new(
    >>>         status_code=200, model=UserID, pagination=page.paging, data=page,
    >>>     )
    """

    status: Annotated[int, Field(..., title="Status code of request.", examples=[status.HTTP_200_OK])]
    error: Annotated[dict[Any, Any] | BaseError | None, Field(None, title="Errors")]
    payload: Annotated[DataPaginationResponse[_Model], Field(title="Payload data.")]

    @classmethod
    def new(
        cls,
        *,
        status_code: int,
        model: type[_Model] | Any,
        pagination: BasePaginationSerializer | URLBase64CursorPaging | OffsetPaging,
        data: _Model | Any,
    ) -> PaginationResponse[_Model]:
        return cls[model](  # type: ignore
            status=status_code,
            payload=DataPaginationResponse[model](data=data, pagination=pagination),  # type: ignore
        )

    model_config = ConfigDict(json_schema_extra={"description": ""})


class DataPaginationResponseWithCounters(
    DataPaginationResponse[_Model], Generic[_Model, _CountersModel]  # noqa: UP046
):
    counters: Annotated[_CountersModel, Field(...)]


class PaginationResponseWithCounters(PaginationResponse[_Model], Generic[_Model, _CountersModel]):  # noqa: UP046
    payload: Annotated[DataPaginationResponseWithCounters[_Model, _CountersModel], Field(title="Payload data.")]

    @classmethod
    def new(  # type: ignore[override]
        cls,
        *,
        status_code: int,
        model: type[_Model] | Any,
        counters_model: type[_CountersModel] | Any,
        pagination: BasePaginationSerializer | URLBase64CursorPaging | OffsetPaging,
        data: _Model | Any,
        counters: _CountersModel | Any,
    ) -> PaginationResponseWithCounters[_Model, _CountersModel]:
        return cls[model, counters_model](  # type: ignore
            status=status_code,
            payload=DataPaginationResponseWithCounters[model, counters_model](  # type: ignore
                data=data, pagination=pagination, counters=counters
            ),
        )
