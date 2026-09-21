from dataclasses import dataclass
from http import HTTPMethod
from typing import cast

from httpx import URL, HTTPStatusError, QueryParams
from loguru import logger

from app.core.concurrency import run_async
from app.core.proxies.constants import ProxyStatusEnum
from app.core.proxies.dto import ProxyBaseDTO, ProxyServerDTO, ProxySourceToPingDTO
from app.core.proxies_sources.dto import ProxySourceDTO
from app.core.shared.types import Missing
from app.infra.adapters.http_adapter import BaseHttpAdapter
from app.infra.gateways.mtproto_checker import MTProxyChecker


@dataclass
class GithubGateway:
    github_http_adapter: BaseHttpAdapter
    mtproxy_checker: MTProxyChecker

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
        """
        Проверяет прокси настоящим MTProto-handshake, а не голым TCP-коннектом.

        Прокси считается живой, только если она приняла наш secret (для `ee` ещё и Fake-TLS)
        и вернула `resPQ` от серверов Telegram — ровно то, что делает клиент при подключении.
        Latency — время до ответа Telegram через прокси.
        """
        proxy_url = proxy_url_with_source.url
        proxy_server = self._get_params_from_proxy(proxy_url.params)
        secret = proxy_server.secret
        proxy_name = cast(str, proxy_server.host)
        source_id = cast(int | None, proxy_url_with_source.source_id)

        result = await self.mtproxy_checker.check(host=proxy_name, port=int(proxy_server.port or 0), secret=secret)
        return ProxyBaseDTO(
            name=proxy_name,
            url=proxy_url,
            source_id=source_id,
            latency=result.latency_ms if result.is_connected else None,
            status=ProxyStatusEnum.enabled if result.is_connected else ProxyStatusEnum.disabled,
        )

    async def get_host_latency_for_urls(self, urls_with_source: list[ProxySourceToPingDTO]) -> list[ProxyBaseDTO]:
        if not urls_with_source:
            return []
        tasks = [self.get_host_latency(proxy_url_with_source=uws) for uws in urls_with_source]
        proxies_dtos = await run_async(*tasks, timeout=20)
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
        return ProxyServerDTO(host=params.get("server"), port=params.get("port"), secret=params.get("secret", ""))
