from enum import StrEnum, unique

PROXY_PING_TIMEOUT = 3.0
TELEGRAM_PROXY_APP_SCHEME = "tg"
TELEGRAM_PROXY_APP_HOST = "proxy"
SAVE_POSTGRES_CHUNK_SIZE = 200

GITHUB_RAW_BASE_URL = "https://raw.githubusercontent.com"


@unique
class ProxyStatusEnum(StrEnum):
    enabled = "enabled"
    disabled = "disabled"


@unique
class ProxySourceStatusEnum(StrEnum):
    enabled = "enabled"
    disabled = "disabled"


@unique
class ProxyVendorNameEnum(StrEnum):
    external = "external"
    github = "GitHub"


@unique
class ProxyOrderByEnum(StrEnum):
    latency_desc = "latency_desc"
    latency = "latency"
    created_at_desc = "created_at_desc"
    created_at = "created_at"
