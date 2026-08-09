from collections.abc import AsyncGenerator
from contextlib import AbstractAsyncContextManager
from typing import Any, TypeVar

AsyncContextManagerT = TypeVar("AsyncContextManagerT", bound=AbstractAsyncContextManager[Any])


async def initialize_context(  # noqa: UP047
    context_manager: AsyncContextManagerT,
) -> AsyncGenerator[AsyncContextManagerT]:
    async with context_manager:
        yield context_manager
