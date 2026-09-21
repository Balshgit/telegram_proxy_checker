from enum import StrEnum, unique

PROXY_PING_TIMEOUT = 10.0
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
    last_active_at_desc = "last_active_at_desc"
    last_active_at = "last_active_at"


@unique
class ProxyCheckError(StrEnum):
    bad_secret = "bad_secret"
    connect_failed = "connect_failed"
    tls_rejected = "tls_rejected"  # в ответ на ClientHello пришёл не ServerHello: не тот секрет или не MTProxy
    tls_bad_hmac = "tls_bad_hmac"  # ServerHello пришёл, но подписан не нашим секретом
    no_answer = "no_answer"  # прокси закрыла соединение, не дождавшись ответа Telegram
    bad_answer = "bad_answer"  # пришло что-то, но не resPQ на наш запрос
    timeout = "timeout"  # прокси молчит: обычно так MTProxy реагирует на неверный секрет


@unique
class SecretMode(StrEnum):
    plain = "plain"
    padded = "dd"
    fake_tls = "ee"
