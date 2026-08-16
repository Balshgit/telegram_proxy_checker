from collections.abc import AsyncGenerator, Mapping
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import respx
from httpx import URL, Response
from respx import MockRouter

from app.api.constants import PLAIN_TEXT_MEDIA_TYPE
from app.core.proxies.constants import ProxyStatusEnum
from app.core.proxies.dto import ProxyBaseDTO
from app.infra.gateways.github_gateway import GithubGateway

GITHUB_PROXIES_ROUTE_NAME = "github_get_proxies"

PROXY_URL_BASE = "https://proxy.example.com"
PROXY_SECRET = "ee1337"
MISSING_PROXY_ID = 999_999


def build_proxy_url(server: str, port: int = 443, secret: str = PROXY_SECRET) -> str:
    """
    Строит урл прокси с параметрами server/port/secret ровно так, как их ждёт приложение.

    `name` у прокси в базе должен совпадать с параметром `server`, иначе массовое обновление
    (`ProxyRepository.update_proxies`) не найдёт запись: оно джойнится по `TelegramProxy.name`.
    """
    return str(URL(PROXY_URL_BASE, params={"server": server, "port": port, "secret": secret}))


@asynccontextmanager
async def mocked_github_get_proxies(raw_proxies: str) -> AsyncGenerator[MockRouter]:
    """
    Мокает HTTP-запрос в github за списком проксей.

    ВАЖНО: respx на выходе из контекста делает router.reset() и чистит `calls`,
    поэтому все проверки вида `mock.calls.call_count` должны быть ВНУТРИ `async with`.
    """
    async with respx.mock(
        assert_all_mocked=True,
        base_url="https://raw.githubusercontent.com",
    ) as respx_mock:
        github_get_proxies = respx_mock.get(
            "/SoliSpirit/mtproto/refs/heads/master/all_proxies.txt", name=GITHUB_PROXIES_ROUTE_NAME
        )
        github_get_proxies.return_value = Response(
            status_code=200, headers={"Content-Type": PLAIN_TEXT_MEDIA_TYPE}, content=raw_proxies
        )
        yield respx_mock


def _build_proxy_dto(url: URL, latency: int | None) -> ProxyBaseDTO:
    return ProxyBaseDTO(
        url=url,
        name=url.params.get("server", ""),
        latency=latency,
        status=ProxyStatusEnum.enabled if latency is not None else ProxyStatusEnum.disabled,
    )


@asynccontextmanager
async def mocked_get_host_latency_for_urls(
    latency_by_url: dict[str, int | None] | None = None,
    default_latency: int | None = 100,
) -> AsyncGenerator[AsyncMock]:
    """
    Мокает GithubGateway.get_host_latency_for_urls, чтобы не ходить в сеть (asyncio.open_connection).

    :param latency_by_url: мапа {str(url): latency}. latency=None -> ProxyStatusEnum.disabled.
    :param default_latency: latency для урлов, которых нет в мапе.

    Возвращает AsyncMock: у него можно смотреть await_count / await_args (`kwargs["urls"]`) и .return_value.

    Порядок урлов в сервисе недетерминированный (там set().difference()),
    поэтому latency задаётся по урлу, а не по позиции в списке.
    """
    latency_map = latency_by_url or {}

    async def _fake_get_host_latency_for_urls(urls: list[URL]) -> list[ProxyBaseDTO]:
        return [_build_proxy_dto(url=url, latency=latency_map.get(str(url), default_latency)) for url in urls]

    mock = AsyncMock(side_effect=_fake_get_host_latency_for_urls)

    with patch.object(GithubGateway, GithubGateway.get_host_latency_for_urls.__name__, mock):
        yield mock


@asynccontextmanager
async def mocked_get_host_latency(
    latency_by_url: dict[str, int | None] | None = None,
    default_latency: int | None = 100,
) -> AsyncGenerator[AsyncMock]:
    latency_map = latency_by_url or {}

    async def _fake_get_host_latency(proxy_url: URL | str) -> ProxyBaseDTO:
        url = URL(proxy_url) if isinstance(proxy_url, str) else proxy_url
        return _build_proxy_dto(url=url, latency=latency_map.get(str(url), default_latency))

    mock = AsyncMock(side_effect=_fake_get_host_latency)

    with patch.object(GithubGateway, GithubGateway.get_host_latency.__name__, mock):
        yield mock


@asynccontextmanager
async def mocked_get_host_latency_by_server(
    latency_by_server: Mapping[str, int | None] | None = None,
    default_latency: int | None = 100,
) -> AsyncGenerator[AsyncMock]:
    """
    То же, что `mocked_get_host_latency_for_urls`, но latency задаётся по параметру `server` урла.

    Урл прокси проходит через `str(URL(...))` несколько раз (фабрика -> база -> сервис),
    поэтому ключ-урл легко разъезжается на нормализации. `server` при этом не меняется
    и именно по нему `ProxyRepository.update_proxies` находит запись в базе.
    """
    latency_map = latency_by_server or {}

    async def _fake_get_host_latency_for_urls(urls: list[URL]) -> list[ProxyBaseDTO]:
        return [
            _build_proxy_dto(url=url, latency=latency_map.get(url.params.get("server", ""), default_latency))
            for url in urls
        ]

    mock = AsyncMock(side_effect=_fake_get_host_latency_for_urls)

    with patch.object(GithubGateway, GithubGateway.get_host_latency_for_urls.__name__, mock):
        yield mock
