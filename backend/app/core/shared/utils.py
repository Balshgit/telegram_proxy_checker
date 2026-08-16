import functools
from collections.abc import Callable
from typing import Any

from loguru import logger


def log_taskiq_decorator(func: Callable[..., Any]) -> Callable[..., Any]:
    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Callable[..., Any]:
        logger.info(f"starting {func.__name__} task")
        result = await func(*args, **kwargs)
        logger.info(f"stoping {func.__name__} task")
        return result

    return wrapper
