import asyncio
import time
from contextlib import suppress
from dataclasses import dataclass
from http import HTTPMethod
from typing import cast

from httpx import URL, HTTPStatusError, QueryParams
from loguru import logger

from app.core.concurrency import run_async
from app.core.proxies.constants import PROXY_PING_TIMEOUT, ProxyStatusEnum
from app.core.proxies.dto import ProxyBaseDTO, ProxyServerDTO, ProxySourceToPingDTO
from app.core.proxies_sources.dto import ProxySourceDTO
from app.core.shared.types import Missing
from app.infra.adapters.http_adapter import BaseHttpAdapter


@dataclass
class GithubGateway:
    github_http_adapter: BaseHttpAdapter

    async def get_urls_for_ping(self, proxy_source: ProxySourceDTO) -> list[ProxySourceToPingDTO]:
        proxy_urls = await self._get_proxies_urls_from_github(url=proxy_source.url)
        urls_to_ping = []
        for url in proxy_urls:
            proxy_server = self._get_params_from_proxy(url.params)
            if not proxy_server.host and not proxy_server.port:
                continue
            urls_to_ping.append(
                ProxySourceToPingDTO(url=url, source_id=proxy_source.id if proxy_source.id is not Missing else None)
            )
        return urls_to_ping

    async def get_host_latency(self, proxy_url_with_source: ProxySourceToPingDTO) -> ProxyBaseDTO:
        proxy_server = self._get_params_from_proxy(proxy_url_with_source.url.params)
        started_at = time.monotonic()
        proxy_name = cast(str, proxy_server.host)
        source_id = cast(int | None, proxy_url_with_source.source_id)
        proxy_url = proxy_url_with_source.url

        try:
            async with asyncio.timeout(PROXY_PING_TIMEOUT):
                _, writer = await asyncio.open_connection(host=proxy_server.host, port=proxy_server.port)
                with suppress(Exception):
                    writer.close()
                    await writer.wait_closed()
        except Exception:  # noqa: BLE001
            return ProxyBaseDTO(
                name=proxy_name, url=proxy_url, source_id=source_id, latency=None, status=ProxyStatusEnum.disabled
            )

        latency = int((time.monotonic() - started_at) * 1000)
        return ProxyBaseDTO(
            name=proxy_name, url=proxy_url, source_id=source_id, latency=latency, status=ProxyStatusEnum.enabled
        )

    async def get_host_latency_for_urls(self, urls_with_source: list[ProxySourceToPingDTO]) -> list[ProxyBaseDTO]:
        if not urls_with_source:
            return []
        tasks = [self.get_host_latency(proxy_url_with_source=uws) for uws in urls_with_source]
        proxies_dtos = await run_async(*tasks)
        return list(proxies_dtos)

    async def _get_proxies_urls_from_github(self, url: URL) -> list[URL]:
        response = await self.github_http_adapter.send_request_and_raise_for_status(method=HTTPMethod.GET, url=url.path)
        urls = []
        try:
            content = response.content.decode()
            urls = [URL(url) for url in content.split("\n")]
        except HTTPStatusError as exc:
            logger.error("cant get proxies from github", exc_info=str(exc))
        return urls

    @staticmethod
    def _get_params_from_proxy(params: QueryParams) -> ProxyServerDTO:
        return ProxyServerDTO(host=params.get("server"), port=params.get("port"))
