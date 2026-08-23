from typing import Annotated

from pydantic import Field
from starlette import status

from app.api.base_schemas import BaseError, BaseResponse
from app.api.exceptions import BaseAPIException


class NoProxiesAddedError(BaseError):
    pass


class NoProxiesAddedResponse(BaseResponse):
    status: Annotated[int, Field(default=status.HTTP_202_ACCEPTED)]
    error: NoProxiesAddedError


class NoProxiesAddedAPIError(BaseAPIException):
    status_code = status.HTTP_202_ACCEPTED
    model = NoProxiesAddedResponse
    title = "No proxies to add"
