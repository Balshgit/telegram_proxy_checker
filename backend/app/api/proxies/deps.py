from datetime import datetime
from typing import Annotated

from fastapi import Query

from app.core.proxies.constants import ProxyStatusEnum
from app.core.proxies.dto import ProxyFilterDTO


async def get_proxy_filters(
    created_from: Annotated[
        datetime | None, Query(..., description="Фильтровать от той даты, когда урлы прокси были создан")
    ] = None,
    created_to: Annotated[
        datetime | None, Query(..., description="Фильтровать до той даты, когда урлы прокси были создан")
    ] = None,
    status: Annotated[ProxyStatusEnum | None, Query(..., description="Фильтр по статусу")] = None,
    name: Annotated[str | None, Query(..., description="Фильтр по имени")] = None,
) -> ProxyFilterDTO:
    return ProxyFilterDTO(
        created_from=created_from,
        created_to=created_to,
        status=status,
        name=name,
    )
