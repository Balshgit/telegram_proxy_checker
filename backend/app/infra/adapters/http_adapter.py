from http import HTTPMethod
from types import TracebackType
from typing import Any, Self, cast

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_fixed,
)

from app.core.shared.ctx_vars import get_ctx_request_id_or_generate_new
from app.core.shared.types import Missing

_DEFAULT_TIMEOUT = httpx.Timeout(read=2, connect=2, write=2, pool=0.5)


class BaseHttpAdapter:
    def __init__(
        self,
        *,
        host: str,
        max_retries_count: int = 2,
        retry_delay: float = 1,
        max_connections: int = 200,
        max_keepalive_connections: int = 20,
        keepalive_expiry: float = 5.0,
        verify: bool = False,
        default_httpx_timeout: httpx.Timeout = _DEFAULT_TIMEOUT,
        **kwargs: Any,
    ) -> None:
        self._base_url = host
        self._client_params = {
            "base_url": host,
            "limits": httpx.Limits(
                max_connections=max_connections,
                max_keepalive_connections=max_keepalive_connections,
                keepalive_expiry=keepalive_expiry,
            ),
            "verify": verify,
            **kwargs,
        }
        self._default_retrying = AsyncRetrying(
            stop=stop_after_attempt(max_retries_count),
            wait=wait_fixed(retry_delay),
            reraise=True,
            retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
        )
        self.default_httpx_timeout = default_httpx_timeout
        self._client: httpx.AsyncClient = httpx.AsyncClient(**self._client_params)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self._client.aclose()

    async def send_request_and_raise_for_status(
        self,
        url: str,
        *,
        method: HTTPMethod = HTTPMethod.GET,
        params: dict[Any, Any] | None = None,
        headers: dict[Any, Any] | None = None,
        json: dict[Any, Any] | None = None,
        max_retries_count: int | object = Missing,
        retry_delay: float | object = Missing,
        **kwargs: Any,
    ) -> httpx.Response:
        response = await self._send_request(
            url=url,
            method=method,
            params=params,
            headers=headers,
            json=json,
            max_retries_count=max_retries_count,
            retry_delay=retry_delay,
            **kwargs,
        )
        response.raise_for_status()
        return response

    async def _send_request(
        self,
        url: str,
        *,
        method: HTTPMethod = HTTPMethod.GET,
        params: dict[Any, Any] | None = None,
        headers: dict[Any, Any] | None = None,
        json: dict[Any, Any] | None = None,
        max_retries_count: int | object = Missing,
        retry_delay: float | object = Missing,
        **kwargs: Any,
    ) -> httpx.Response:
        extensions = {}
        if "extensions" in kwargs:
            extensions = kwargs.pop("extensions")

        if "timeout" not in extensions:
            extensions["timeout"] = self.default_httpx_timeout.as_dict()

        headers = self._add_request_headers(headers=headers)
        request = self._client.build_request(
            method=method,
            url=url,
            headers=headers,
            params=params,
            json=json,
            extensions=extensions,
            **kwargs,
        )
        retrying = self._get_retrying_or_default(max_retries_count=max_retries_count, retry_delay=retry_delay)
        wrapped_coro = retrying.wraps(self._do_request)
        return await wrapped_coro(request)

    async def _do_request(self, request: httpx.Request) -> httpx.Response:
        try:
            return await self._client.send(request)
        except Exception:  # noqa: BLE001
            # fake response with status code 100 in case request not success
            return httpx.Response(status_code=100, request=request)

    def _get_retrying_or_default(self, max_retries_count: int | object, retry_delay: float | object) -> AsyncRetrying:
        if max_retries_count is Missing or retry_delay is Missing:
            return self._default_retrying
        max_retries_count, retry_delay = cast(int, max_retries_count), cast(float, retry_delay)
        return AsyncRetrying(
            stop=stop_after_attempt(max_retries_count),
            wait=wait_fixed(retry_delay),
            reraise=True,
            retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
        )

    @staticmethod
    def _add_request_headers(headers: dict[Any, Any] | None = None) -> dict[str, Any] | None:
        headers = headers or {}
        if request_id := get_ctx_request_id_or_generate_new():
            headers["X-Request-Id"] = request_id

        return headers if headers else None

    @property
    def _client_name(self) -> str:
        return self.__class__.__name__
