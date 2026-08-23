from collections.abc import Iterable
from typing import cast

from app.core.proxies.dto import ProxyBaseDTO, ProxySourceToPingDTO


def collect_source_ids(items: Iterable[ProxyBaseDTO | ProxySourceToPingDTO]) -> set[int]:
    """Собирает id источников, которых коснулась пачка проксей, чтобы пересчитать только их счётчики."""
    return {cast(int, item.source_id) for item in items if item.source_id is not None}
