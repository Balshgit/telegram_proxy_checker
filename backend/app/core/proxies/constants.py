from enum import StrEnum, unique

PROXY_PING_TIMEOUT = 3.0
TELEGRAM_PROXY_APP_SCHEME = "tg"
TELEGRAM_PROXY_APP_HOST = "proxy"
TELEGRAM_PROXY_WEB_SCHEME = "https"
TELEGRAM_PROXY_WEB_HOST = "t.me"
TELEGRAM_PROXY_WEB_PATH = "/proxy"
SAVE_POSTGRES_CHUNK_SIZE = 200


@unique
class ProxyStatusEnum(StrEnum):
    enabled = "enabled"
    disabled = "disabled"


@unique
class ProxyOrderByEnum(StrEnum):
    latency_desc = "latency_desc"
    latency = "latency"
    created_at_desc = "created_at_desc"
    created_at = "created_at"
