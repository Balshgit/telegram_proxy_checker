from enum import StrEnum, unique

GITHUB_RAW_BASE_URL = "https://raw.githubusercontent.com"
WAIT_BEFORE_COLLECT_PROXIES_SECONDS = 5


@unique
class ProxySourceStatusEnum(StrEnum):
    enabled = "enabled"
    disabled = "disabled"


@unique
class ProxyVendorNameEnum(StrEnum):
    external = "external"
    github = "GitHub"
