from collections.abc import Callable
from typing import Any

from fastapi.datastructures import DefaultPlaceholder
from fastapi.routing import APIRoute


class TPCAPIRoute(APIRoute):
    """This class omits default response_field kwargs cause of performance optimization"""

    def __init__(
        self,
        path: str,
        endpoint: Callable[..., Any],
        **kwargs: Any,
    ) -> None:
        response_model = kwargs.pop("response_model", None)
        if isinstance(response_model, DefaultPlaceholder):
            super().__init__(path=path, endpoint=endpoint, response_model=None, **kwargs)
        else:
            super().__init__(path=path, endpoint=endpoint, response_model=response_model, **kwargs)
