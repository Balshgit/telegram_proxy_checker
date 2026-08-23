from collections.abc import Iterable
from typing import cast

from httpx import URL

from app.core.proxies.constants import TELEGRAM_PROXY_WEB_HOST, TELEGRAM_PROXY_WEB_PATH, TELEGRAM_PROXY_WEB_SCHEME
from app.core.proxies.dto import ProxyBaseDTO, ProxySourceToPingDTO
from app.core.proxies.models import TelegramProxy


def collect_source_ids(items: Iterable[ProxyBaseDTO | ProxySourceToPingDTO]) -> set[int]:
    """Собирает id источников, которых коснулась пачка проксей, чтобы пересчитать только их счётчики."""
    return {cast(int, item.source_id) for item in items if item.source_id is not None}


def split_duplicated_proxies(proxies: Iterable[TelegramProxy]) -> tuple[list[TelegramProxy], list[TelegramProxy]]:
    """
    Делит прокси на уникальные по урлу и дубли.

    Дублем считается полное совпадение урла: в уникальных остаётся самая ранняя прокси группы,
    все следующие уезжают на удаление.
    """
    unique_proxies: dict[str, TelegramProxy] = {}
    duplicated_proxies: list[TelegramProxy] = []

    for proxy in sorted(proxies, key=lambda existing_proxy: existing_proxy.id):
        url = str(proxy.url)

        if url in unique_proxies:
            duplicated_proxies.append(proxy)
            continue
        unique_proxies[url] = proxy

    return list(unique_proxies.values()), duplicated_proxies


def to_web_proxy_url(url: URL | str) -> URL:
    """
    Приводит урл прокси к каноничному виду `https://t.me/proxy?...`.

    Источники отдают ссылки и как `tg://proxy?...`, и как `https://t.me/proxy?...`;
    в базе должен лежать только веб-вариант, поэтому от исходного урла берутся только query-параметры.
    """
    return URL(
        scheme=TELEGRAM_PROXY_WEB_SCHEME,
        host=TELEGRAM_PROXY_WEB_HOST,
        path=TELEGRAM_PROXY_WEB_PATH,
        params=URL(url).params,
    )
