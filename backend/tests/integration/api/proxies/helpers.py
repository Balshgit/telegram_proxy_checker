from collections.abc import AsyncGenerator, Mapping
from contextlib import asynccontextmanager
from typing import Any, cast
from unittest.mock import AsyncMock, patch

import respx
from httpx import URL, Response
from respx import MockRouter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.constants import PLAIN_TEXT_MEDIA_TYPE
from app.core.proxies import services as proxy_services
from app.core.proxies.constants import ProxyStatusEnum
from app.core.proxies.dto import ProxyBaseDTO, ProxySourceToPingDTO
from app.core.proxies.models import TelegramProxiesSource, TelegramProxy
from app.infra.gateways.github_gateway import GithubGateway
from app.infra.taskiq.executor import TaskiqTasksExecutor
from tests.support.factories.proxies import GITHUB_RAW_BASE_URL

GITHUB_PROXIES_ROUTE_NAME = "github_get_proxies"

PROXY_URL_BASE = "https://proxy.example.com"
PROXY_SECRET = "ee1337"
MISSING_PROXY_ID = 999_999
MISSING_PROXY_SOURCE_ID = 888_888

CHUNK_SIZE_FOR_TESTS = 5

#: Имя kwarg, с которым сервис зовёт `GithubGateway.get_host_latency_for_urls`.
PING_URLS_KWARG = "urls_with_source"
#: Ключ в `params` таскик-задачи, под которым уезжает "хвост" урлов вместе с их источниками.
DEFERRED_URLS_PARAM = "source_urls"


def build_proxy_url(server: str, port: int = 443, secret: str = PROXY_SECRET) -> str:
    """
    Строит урл прокси с параметрами server/port/secret ровно так, как их ждёт приложение.

    `name` у прокси в базе должен совпадать с параметром `server`, иначе массовое обновление
    (`ProxyRepository.update_proxies`) не найдёт запись: оно джойнится по `TelegramProxy.name`.
    """
    return str(URL(PROXY_URL_BASE, params={"server": server, "port": port, "secret": secret}))


def pinged_proxies(mocked_latency: AsyncMock) -> list[ProxySourceToPingDTO]:
    """Достаёт список `ProxySourceToPingDTO`, с которым сервис пошёл пинговать прокси."""
    return list(mocked_latency.await_args.kwargs[PING_URLS_KWARG])


def pinged_source_id_by_server(mocked_latency: AsyncMock) -> dict[str, int | None]:
    """Мапа {server: source_id} из того, что сервис отдал в гейтвей на пинг."""
    return {
        proxy_to_ping.url.params["server"]: cast(int | None, proxy_to_ping.source_id)
        for proxy_to_ping in pinged_proxies(mocked_latency)
    }


def deferred_source_urls(mocked_taskiq: AsyncMock) -> list[dict[str, Any]]:
    """Достаёт "хвост" урлов, который сервис отправил в taskiq: список словарей source_id/url."""
    return list(mocked_taskiq.await_args.kwargs["params"][DEFERRED_URLS_PARAM])


async def get_proxies_by_name(session: AsyncSession) -> dict[str, TelegramProxy]:
    """Все прокси из базы, разложенные по `name` — так удобнее сверять их с параметром `server`."""
    proxies = (await session.execute(select(TelegramProxy))).scalars().all()
    return {proxy.name: proxy for proxy in proxies}


async def get_proxies_by_url(session: AsyncSession) -> dict[str, TelegramProxy]:
    """Все прокси из базы, разложенные по `url`."""
    proxies = (await session.execute(select(TelegramProxy))).scalars().all()
    return {proxy.url: proxy for proxy in proxies}


async def get_proxies_sources_by_id(session: AsyncSession) -> dict[int, TelegramProxiesSource]:
    """
    Все источники из базы, разложенные по `id`.

    `populate_existing` обязателен: после `DELETE ... ON DELETE SET NULL` объекты в identity map
    остаются со старыми значениями, и без перечитывания тест проверял бы кэш, а не базу.
    """
    query = select(TelegramProxiesSource).execution_options(populate_existing=True)
    sources = (await session.execute(query)).scalars().all()
    return {source.id: source for source in sources}


async def get_proxies_by_id(session: AsyncSession) -> dict[int, TelegramProxy]:
    """Все прокси из базы, разложенные по `id`, с принудительным перечитыванием из базы."""
    query = select(TelegramProxy).execution_options(populate_existing=True)
    proxies = (await session.execute(query)).scalars().all()
    return {proxy.id: proxy for proxy in proxies}


@asynccontextmanager
async def mocked_github_get_proxies(raw_proxies: str) -> AsyncGenerator[MockRouter]:
    """
    Мокает HTTP-запрос в github за списком проксей.

    ВАЖНО: respx на выходе из контекста делает router.reset() и чистит `calls`,
    поэтому все проверки вида `mock.calls.call_count` должны быть ВНУТРИ `async with`.
    """
    async with respx.mock(
        assert_all_mocked=True,
        base_url=GITHUB_RAW_BASE_URL,
    ) as respx_mock:
        github_get_proxies = respx_mock.get(name=GITHUB_PROXIES_ROUTE_NAME)
        github_get_proxies.return_value = Response(
            status_code=200, headers={"Content-Type": PLAIN_TEXT_MEDIA_TYPE}, content=raw_proxies
        )
        yield respx_mock


def source_route_name(source_url: str) -> str:
    """Имя respx-роута для конкретного источника, чтобы проверять вызовы по каждому источнику отдельно."""
    return f"{GITHUB_PROXIES_ROUTE_NAME}:{source_url}"


@asynccontextmanager
async def mocked_github_get_proxies_by_source(raw_proxies_by_source: Mapping[str, str]) -> AsyncGenerator[MockRouter]:
    """
    То же, что `mocked_github_get_proxies`, но сразу для нескольких источников.

    :param raw_proxies_by_source: мапа {url источника: сырой ответ со списком проксей}.

    Каждый источник получает свой роут с именем `source_route_name(source_url)`.
    Проверки `mock.calls` / `mock.routes[...]` должны быть ВНУТРИ `async with`: на выходе respx
    делает `router.reset()` и чистит счётчики.
    """
    async with respx.mock(assert_all_mocked=True, base_url=GITHUB_RAW_BASE_URL) as respx_mock:
        for source_url, raw_proxies in raw_proxies_by_source.items():
            route = respx_mock.get(url=source_url, name=source_route_name(source_url))
            route.return_value = Response(
                status_code=200, headers={"Content-Type": PLAIN_TEXT_MEDIA_TYPE}, content=raw_proxies
            )
        yield respx_mock


def _build_proxy_dto(proxy_to_ping: ProxySourceToPingDTO, latency: int | None) -> ProxyBaseDTO:
    """
    Собирает ответ гейтвея так же, как это делает боевой `GithubGateway.get_host_latency`.

    Ключевое для тестов на источник: `source_id` берётся из входного `ProxySourceToPingDTO`
    и уезжает дальше в репозиторий — именно по этой цепочке источник попадает в `TelegramProxy`.
    """
    return ProxyBaseDTO(
        url=proxy_to_ping.url,
        name=proxy_to_ping.url.params.get("server", ""),
        source_id=cast(int | None, proxy_to_ping.source_id),
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

    Возвращает AsyncMock: у него можно смотреть await_count / await_args
    (`kwargs[PING_URLS_KWARG]` — список `ProxySourceToPingDTO`) и .return_value.

    Порядок урлов в сервисе задаётся порядком обхода источников,
    поэтому latency задаётся по урлу, а не по позиции в списке.
    """
    latency_map = latency_by_url or {}

    async def _fake_get_host_latency_for_urls(urls_with_source: list[ProxySourceToPingDTO]) -> list[ProxyBaseDTO]:
        return [
            _build_proxy_dto(
                proxy_to_ping=proxy_to_ping,
                latency=latency_map.get(str(proxy_to_ping.url), default_latency),
            )
            for proxy_to_ping in urls_with_source
        ]

    mock = AsyncMock(side_effect=_fake_get_host_latency_for_urls)

    with patch.object(GithubGateway, GithubGateway.get_host_latency_for_urls.__name__, mock):
        yield mock


@asynccontextmanager
async def mocked_save_postgres_chunk_size(chunk_size: int = CHUNK_SIZE_FOR_TESTS) -> AsyncGenerator[int]:
    """
    Уменьшает размер чанка, с которым работает `ProxyService`.

    Боевое значение — 200: чтобы дойти до ветки с отправкой "хвоста" в taskiq, тесту пришлось бы
    создавать 201 запись. `ProxyService` импортирует константу напрямую (`from ... import ...`),
    поэтому подменяем её в неймспейсе модуля сервиса, а не в `app.core.proxies.constants`.
    """
    with patch.object(proxy_services, "SAVE_POSTGRES_CHUNK_SIZE", chunk_size):
        yield chunk_size


@asynccontextmanager
async def mocked_taskiq_run() -> AsyncGenerator[AsyncMock]:
    """
    Мокает `TaskiqTasksExecutor.run`, чтобы не ходить в реальный брокер.

    Патч ставится на класс, поэтому `self` в мок не прилетает: обращение к `instance.run`
    отдаёт AsyncMock как есть. Ожидаемый вызов — `mock.await_args.args[0]` (таска)
    и `mock.await_args.kwargs["params"]`.
    """
    mock = AsyncMock(return_value=None)

    with patch.object(TaskiqTasksExecutor, TaskiqTasksExecutor.run.__name__, mock):
        yield mock


@asynccontextmanager
async def mocked_get_host_latency(
    latency_by_url: dict[str, int | None] | None = None,
    default_latency: int | None = 100,
) -> AsyncGenerator[AsyncMock]:
    """
    Мокает `GithubGateway.get_host_latency` — пинг одной прокси.

    Сервис зовёт его позиционно, поэтому в `await_args.args[0]` лежит `ProxySourceToPingDTO`
    с `source_id` той прокси, которую обновляют.
    """
    latency_map = latency_by_url or {}

    async def _fake_get_host_latency(proxy_url_with_source: ProxySourceToPingDTO) -> ProxyBaseDTO:
        return _build_proxy_dto(
            proxy_to_ping=proxy_url_with_source,
            latency=latency_map.get(str(proxy_url_with_source.url), default_latency),
        )

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

    async def _fake_get_host_latency_for_urls(urls_with_source: list[ProxySourceToPingDTO]) -> list[ProxyBaseDTO]:
        return [
            _build_proxy_dto(
                proxy_to_ping=proxy_to_ping,
                latency=latency_map.get(proxy_to_ping.url.params.get("server", ""), default_latency),
            )
            for proxy_to_ping in urls_with_source
        ]

    mock = AsyncMock(side_effect=_fake_get_host_latency_for_urls)

    with patch.object(GithubGateway, GithubGateway.get_host_latency_for_urls.__name__, mock):
        yield mock
