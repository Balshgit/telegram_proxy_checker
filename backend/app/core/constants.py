from enum import StrEnum
from zoneinfo import ZoneInfo

import httpx

MOSCOW_TZ = ZoneInfo("Europe/Moscow")

MAX_UNSIGNED_INT = 4294967295
MAX_UNSIGNED_BIGINT = 18_446_744_073_709_551_615

MAX_SIGNED_INT = 2147483647

AUTH_TIMEOUT = httpx.Timeout(read=2.5, connect=2.5, write=2.5, pool=2.5)


class ResourceType(StrEnum):
    url = "url"
    proxy = "proxy"
    proxy_source = "proxy_source"
