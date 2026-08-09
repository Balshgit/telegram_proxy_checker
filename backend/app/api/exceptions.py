from collections import defaultdict
from enum import Enum
from itertools import groupby
from typing import Annotated, Any, Union

from fastapi import status
from fastapi.exceptions import RequestValidationError
from fastapi.requests import Request
from fastapi.responses import Response
from loguru import logger
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.base_schemas import BaseError, BaseResponse
from app.api.constants import REQUEST_ID_HEADER_NAME, APIVersionEnum
from app.core.constants import ResourceType
from app.core.shared.ctx_vars import get_ctx_request_id_or_generate_new


class BaseAPIException(Exception):
    _content_type: str = "application/json"
    model: type[BaseResponse] = BaseResponse
    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    title: str | None = None
    type: str | None = None
    detail: str | None = None
    instance: str | None = None
    headers: dict[str, str] | None = None

    def __init__(self, **ctx: Any) -> None:
        self.__dict__ = ctx

    def get_response_data(self) -> BaseResponse:
        return self.model(  # type: ignore[call-arg]
            status=self.status_code,
            error=self.model.model_fields["error"].annotation(  # type: ignore[misc]
                type=self._get_type_error(),
                detail=self.detail,
                title=self.title,
                instance=self.instance,
            ),
        )

    def _get_type_error(self) -> str:
        return self.model.model_fields["error"].annotation.__name__  # type: ignore[union-attr]

    @classmethod
    def example(cls) -> dict[str, Any] | None:
        if isinstance(cls.model.model_config.get("json_schema_extra"), dict):
            return cls.model.model_config["json_schema_extra"].get("example")  # type: ignore[union-attr, return-value]
        return None

    @classmethod
    def response(cls) -> dict[str, Any]:
        result: dict[str, Any] = {"model": cls.model}
        json_schema_extra = cls.model.model_config.get("json_schema_extra")
        if json_schema_extra is not None:
            result["content"] = {cls._content_type: json_schema_extra}
        return result


class InternalServerError(BaseError):
    pass


class InternalServerErrorResponse(BaseResponse):
    error: InternalServerError
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": 500,
                "error": {
                    "type": "InternalServerError",
                    "title": "Server encountered an unexpected error that prevented it from fulfilling the request",
                    "detail": "error when adding LitAgent",
                },
            },
        }
    )


class ValidationErrorDescription(BaseModel):
    loc: list[Annotated[str, BeforeValidator(lambda x: str(x))]] = Field(  # noqa: PLW0108
        title="The location of the error", examples=['["path","art_id"]']
    )
    msg: str = Field(title="Human-readable description", examples=["value is not a valid integer"])
    type: str = Field(title="Machine-readable description", examples=["type_error.integer"])


class ParamValidationError(BaseError):
    error_descriptions: list[ValidationErrorDescription] | None = Field(None, title="List of validation errors ")


class ParamValidationErrorResponse(BaseResponse):
    error: ParamValidationError
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": 422,
                "error": {
                    "type": "ParamValidationError",
                    "title": "Validation error because of request parameters",
                    "detail": "Received a validation error while interpreting request parameters. "
                    "See error_descriptions for details",
                    "error_descriptions": [
                        {
                            "loc": ["path", "art_id"],
                            "msg": "value is not a valid integer",
                            "type": "type_error.integer",
                        },
                    ],
                },
            },
        }
    )


class RequestParamValidationError(BaseAPIException):
    model = ParamValidationErrorResponse
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    title = "Validation error because of request parameters"
    detail = "Received a validation error while interpreting request parameters. See error_descriptions for details"

    def get_response_data(self) -> BaseResponse:
        return self.model(  # type: ignore[call-arg]
            status=self.status_code,
            error=self.model.model_fields["error"].annotation(  # type: ignore[misc]
                type=self._get_type_error(),
                title=self.title,
                detail=self.detail,
                instance=self.instance,
            ),
        )


class ResourceNotFoundByID(BaseError):
    resource_type: ResourceType | None = Field(None, title="Type of the resource the server could not find")
    resource_id: Any | None = Field(None, title="Identifier of the resource the server could not find")


class ResourceNotFoundByIDResponse(BaseResponse):
    error: ResourceNotFoundByID
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": 404,
                "error": {
                    "type": "ResourceNotFoundByID",
                    "title": "Resource not found",
                    "detail": "Could not find collections with [123] as an identifier",
                    "resource_type": "collections",
                    "resource_id": [
                        123,
                    ],
                },
            },
        }
    )


class Conflict(BaseError):
    resource_type: ResourceType | None = Field(None, title="Type of the resource the server could not add")
    resource_id: Any | None = Field(None, title="Identifier of the resource the server could not add")


class ConflictResponse(BaseResponse):
    error: Conflict
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": 409,
                "error": {
                    "type": "Conflict",
                    "title": "Resource is already registered",
                    "detail": "Could not add collections with [123] as an identifier",
                    "resource_type": "collections",
                    "resource_id": [
                        123,
                    ],
                },
            },
        }
    )


class UnknownEndpoint(BaseError):
    pass


class PermissionMissing(BaseError):
    pass


class BadEndpointUsage(BaseError):
    pass


class UnknownEndpointResponse(BaseResponse):
    error: UnknownEndpoint
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": 404,
                "error": {
                    "type": "UnknownEndpoint",
                    "title": "Requested endpoint does not exist",
                },
            },
        }
    )


class PermissionMissingResponse(BaseResponse):
    error: PermissionMissing
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": 403,
                "error": {
                    "type": "PermissionMissing",
                    "title": "Permission required for this endpoint is missing",
                },
            },
        }
    )


class BadEndpointUsageResponse(BaseResponse):
    error: BadEndpointUsage
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": 400,
                "error": {
                    "type": "BadEndpointUsage",
                    "title": "Endpoint was used in the wrong way",
                    "detail": "User cannot add like to their own review",
                },
            },
        }
    )


class GatewayTimeoutResponse(BaseResponse):
    error: BadEndpointUsage
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": 504,
                "error": {
                    "type": "GatewayTimeout",
                    "title": "Gateway timeout. Try to retry request",
                },
            },
        }
    )


class ResourceNotFoundByIDError(BaseAPIException):
    model = ResourceNotFoundByIDResponse
    status_code = status.HTTP_404_NOT_FOUND
    detail: str = "Could not find {resource_type} with {resource_id} as an identifier"
    title: str = "Resource not found"
    resource_id: int | str
    resource_type: ResourceType

    def get_response_data(self) -> BaseResponse:
        detail_args = _prepare_detail_args(self.__dict__)
        return self.model(  # type: ignore[call-arg]
            status=self.status_code,
            error=self.model.model_fields["error"].annotation(  # type: ignore[misc]
                type=self._get_type_error(),
                title=self.title,
                detail=self.detail.format(**detail_args),
                instance=self.instance,
                resource_type=self.resource_type,
                resource_id=self.resource_id,
            ),
        )


class ConflictError(BaseAPIException):
    model = ConflictResponse
    status_code = status.HTTP_409_CONFLICT
    detail: str = "Could not add {resource_type} with {resource_id} as an identifier"
    title: str = "Resource was not added"
    resource_id: int | str
    resource_type: ResourceType


class UnknownEndpointError(BaseAPIException):
    model = UnknownEndpointResponse
    status_code = status.HTTP_404_NOT_FOUND
    title: str = "Requested endpoint does not exist"

    def get_response_data(self) -> BaseResponse:
        return self.model(  # type: ignore[call-arg]
            status=self.status_code,
            error=self.model.model_fields["error"].annotation(  # type: ignore[misc]
                type=self._get_type_error(),
                title=self.title,
                detail=self.detail,
            ),
        )


class BadEndpointUsageError(BaseAPIException):
    model = BadEndpointUsageResponse
    status_code = status.HTTP_400_BAD_REQUEST
    title: str = "Endpoint was used in the wrong way"

    def get_response_data(self) -> BaseResponse:
        return self.model(  # type: ignore[call-arg]
            status=self.status_code,
            error=self.model.model_fields["error"].annotation(  # type: ignore[misc]
                type=self._get_type_error(),
                title=self.title,
                detail=self.detail,
            ),
        )


class ServerAPIError(BaseAPIException):
    model = InternalServerErrorResponse
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    title: str = "Something went wrong on the server, but we know about it"


class GatewayTimeoutError(BaseAPIException):
    model = BadEndpointUsageResponse
    status_code = status.HTTP_504_GATEWAY_TIMEOUT
    title: str = "Gateway timeout. Try to retry request"

    def get_response_data(self) -> BaseResponse:
        return self.model(  # type: ignore[call-arg]
            status=self.status_code,
            error=self.model.model_fields["error"].annotation(  # type: ignore[misc]
                type=self._get_type_error(),
                title=self.title,
                detail=self.detail,
            ),
        )


class PermissionMissingError(BaseAPIException):
    model = PermissionMissingResponse
    status_code = status.HTTP_403_FORBIDDEN
    title: str = "Permission required for this endpoint is missing"

    def get_response_data(self) -> BaseResponse:
        return self.model(  # type: ignore[call-arg]
            status=self.status_code,
            error=self.model.model_fields["error"].annotation(  # type: ignore[misc]
                type=self._get_type_error(), title=self.title, detail=self.detail
            ),
        )


def _get_request_id_header() -> dict[str, str]:
    request_id = get_ctx_request_id_or_generate_new()
    return {REQUEST_ID_HEADER_NAME: request_id}


async def on_api_exception(_: Request, exception: BaseAPIException) -> Response:
    content = exception.get_response_data().model_dump(
        mode="json",
        exclude_none=True,
        exclude_unset=True,
        exclude_defaults=True,
    )
    return Response(
        status_code=exception.status_code,
        content=content,
        headers=exception.headers | _get_request_id_header() if exception.headers else _get_request_id_header(),
    )


async def generic_http_exception_handler(request: Request, exception: StarletteHTTPException) -> Response:
    corresponding_api_exceptions: dict[int, BaseAPIException] = {
        UnknownEndpointError.status_code: UnknownEndpointError(),
        PermissionMissingError.status_code: PermissionMissingError(),
    }
    api_exception = corresponding_api_exceptions.get(exception.status_code)

    if api_exception:
        return await on_api_exception(request, api_exception)
    else:  # noqa: RET505
        return Response(
            status_code=exception.status_code,
            headers=(
                exception.headers | _get_request_id_header()  # type: ignore[operator]
                if exception.headers
                else _get_request_id_header()
            ),
            content=BaseResponse(status=exception.status_code).model_dump(  # type: ignore[call-arg]
                exclude_none=True,
                exclude_unset=True,
                exclude_defaults=True,
            ),
        )


async def internal_server_error_handler(_request: Request, _exception: Exception) -> Response:
    error = InternalServerError(title="Что-то пошло не так!", type="InternalServerError")  # type: ignore[call-arg]
    response = InternalServerErrorResponse(status=500, error=error).model_dump(  # type: ignore[call-arg]
        exclude_unset=True
    )
    request_id = _get_request_id_header()
    try:
        logger.info(
            "unhandled exception",
            request_id=request_id.get(REQUEST_ID_HEADER_NAME, ""),
            error_class=_exception.__class__,
            error_details=str(_exception),
            method=_request.method,
            url=_request.url,
            headers=_request.headers,
            query_params=dict(_request.query_params),
            state=_request.state._state,
        )
    except Exception:  # noqa: BLE001
        logger.info("unhandled exception", error=_exception.__class__, scope=_request.scope)
    return Response(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=response, headers=request_id)


async def validation_exception_handler(_: Request, exc: RequestValidationError) -> Response:
    error_descriptions = []
    for error in exc.errors():
        if isinstance(error, dict):
            error_descriptions.append(ValidationErrorDescription(**error))
            continue
        error_descriptions.append(
            ValidationErrorDescription(
                loc=error.loc_tuple(),
                msg=str(error.exc),
                type=error.exc.__class__.__name__,
            )
        )

    response_data = RequestParamValidationError().get_response_data()
    response_data.error.error_descriptions = error_descriptions  # type: ignore
    return Response(
        status_code=response_data.status,
        content=response_data.model_dump(exclude_none=True, exclude_unset=True, exclude_defaults=True),
        headers=_get_request_id_header(),
    )


def include_exception_responses(*args: type[BaseAPIException]) -> dict[Any, Any]:
    responses: dict[int, dict[Any, Any]] = {}
    sorted_args = sorted(args, key=lambda e: e.status_code)

    for status_code, errs_iter in groupby(sorted_args, lambda e: e.status_code):
        errs = list(errs_iter)
        status_code = errs[0].status_code  # noqa: PLW2901
        if len(errs) == 1:
            responses.update({status_code: errs[0].response()})
        else:
            content: dict[Any, Any] = defaultdict(lambda: defaultdict(dict))
            for err in errs:
                content[err._content_type]["examples"].update({err.__name__: {"value": err.example()}})
            responses.update(
                {
                    status_code: {
                        "model": Union[tuple(err.model for err in errs)],  # noqa: UP007
                        "content": dict(content),
                    }
                }
            )

    return responses


class TooManyRequests(BaseError):
    pass


class TooManyRequestsErrorResponse(BaseResponse):
    error: TooManyRequests
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": 429,
                "error": {
                    "type": "TooManyRequests",
                    "title": "Too many requests",
                    "detail": "Try later",
                },
            },
        }
    )


class TooManyRequestsError(BaseAPIException):
    model = TooManyRequestsErrorResponse
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    detail: str = "Try later"
    title: str = "Too many requests"

    def get_response_data(self) -> BaseResponse:
        detail_args = _prepare_detail_args(self.__dict__)
        return self.model(  # type: ignore[call-arg]
            status=self.status_code,
            error=self.model.model_fields["error"].annotation(  # type: ignore[misc]
                type=self._get_type_error(),
                title=self.title,
                detail=self.detail.format(**detail_args),
            ),
        )


class Unauthorized(BaseError):
    pass


class UnauthorizedErrorResponse(BaseResponse):
    error: Unauthorized
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": 401,
                "error": {
                    "type": "Unauthorized",
                    "title": "Incorrect login or password",
                },
            },
        }
    )


class UnauthorizedErrorAPIException(BaseAPIException):
    model = UnauthorizedErrorResponse
    status_code = status.HTTP_401_UNAUTHORIZED
    title = "Incorrect user data"


class UnknownAPIVersionError(BaseError):
    requested_api_version: APIVersionEnum | None = Field(None, title="API version requested")
    available_api_versions: list[APIVersionEnum] | None = Field(None, title="Available API versions for endpoint")


class UnknownAPIVersionResponse(BaseResponse):
    error: UnknownAPIVersionError
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": 404,
                "error": {
                    "type": "UnknownAPIVersionError",
                    "title": "Unknown API version",
                    "detail": "Unknown API version with 123 as an identifier. Available versions: [v1]",
                    "requested_api_version": "collections",
                    "available_api_versions": ["v1"],
                },
            },
        }
    )


class UnknownAPIVersionAPIException(BaseAPIException):
    model = UnknownAPIVersionResponse
    status_code = status.HTTP_404_NOT_FOUND
    detail: str = (
        "Unknown API version with {requested_api_version} as an identifier. "
        "Available versions: {available_api_versions}"
    )
    title: str = "Unknown API version"
    requested_api_version: APIVersionEnum
    available_api_versions: list[APIVersionEnum]

    def get_response_data(self) -> BaseResponse:
        detail_args = _prepare_detail_args(self.__dict__)
        return self.model(  # type: ignore[call-arg]
            status=self.status_code,
            error=self.model.model_fields["error"].annotation(  # type: ignore[misc]
                type=self._get_type_error(),
                title=self.title,
                detail=self.detail.format(**detail_args),
                instance=self.instance,
                requested_api_version=self.requested_api_version,
                available_api_versions=self.available_api_versions,
            ),
        )


def _prepare_detail_args(arguments: dict[str, Any]) -> dict[str, Any]:
    for key, value in arguments.items():
        if isinstance(value, Enum):
            arguments[key] = value.value
    return arguments
