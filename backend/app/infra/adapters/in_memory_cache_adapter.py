import math
import time
from collections.abc import Callable
from datetime import timedelta
from typing import Any

from cachetools import TLRUCache


class TPCTLRUCache(TLRUCache[Any, Any]):
    def __init__(
        self,
        maxsize: float,
        ttl: int,
        timer: Callable[[], float] = time.monotonic,
        getsizeof: Callable[[Any], float] | None = None,
    ) -> None:
        def _my_ttu(_key: Any, value: Any, now: float) -> float:
            return now + (ttl - now % ttl)

        super().__init__(maxsize, _my_ttu, timer=timer, getsizeof=getsizeof)

    @staticmethod
    def stringified_cache_key(method_name: str, *args: Any, **kwargs: Any) -> str:
        return f"method_name:{method_name}:" + ":".join([str(i) for i in list(args) + list(kwargs.values())])


def init_prc_in_memory_cache(ttl: int = timedelta(minutes=10).seconds) -> TPCTLRUCache:
    return TPCTLRUCache(maxsize=math.inf, ttl=ttl, timer=time.time)
