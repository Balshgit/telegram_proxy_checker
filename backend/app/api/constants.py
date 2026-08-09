from enum import Enum
from typing import Literal, TypedDict

REQUEST_ID_HEADER_NAME = "X-Request-Id"


class HeaderDescription(TypedDict):
    description: str
    # Refer to https://swagger.io/docs/specification/v3_0/data-models/data-types/
    type: Literal["string", "integer", "number", "boolean", "array", "object"]


class APIVersionEnum(str, Enum):  # noqa: UP042
    V1 = "1"
    V2 = "2"


# ──────────────────────────────────────────────────────────────
#  Content-Type для генерируемых файлов (отчёты)
# ──────────────────────────────────────────────────────────────

PDF_MEDIA_TYPE = "application/pdf"
XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
