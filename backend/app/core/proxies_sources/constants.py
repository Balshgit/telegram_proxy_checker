from enum import StrEnum, unique

GITHUB_RAW_BASE_URL = "https://raw.githubusercontent.com"


@unique
class ProxySourceStatusEnum(StrEnum):
    enabled = "enabled"
    disabled = "disabled"


@unique
class ProxyVendorNameEnum(StrEnum):
    external = "external"
    github = "GitHub"
