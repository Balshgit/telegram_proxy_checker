from enum import StrEnum

PROXY_PING_TIMEOUT = 3.0
TELEGRAM_PROXY_APP_SCHEME = "tg"
TELEGRAM_PROXY_APP_HOST = "proxy"


class ProxyStatusEnum(StrEnum):
    enabled = "enabled"
    disabled = "disabled"
