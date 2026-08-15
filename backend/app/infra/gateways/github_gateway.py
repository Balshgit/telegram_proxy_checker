import asyncio
import time
from contextlib import suppress
from dataclasses import dataclass
from http import HTTPMethod

from httpx import URL, QueryParams

from app.core.proxies.constants import PROXY_PING_TIMEOUT, ProxyStatusEnum
from app.core.proxies.dto import ProxyBaseDTO, ProxyServerDTO
from app.infra.adapters.http_adapter import BaseHttpAdapter


@dataclass
class GithubGateway:
    http_adapter: BaseHttpAdapter

    async def get_proxies_list(self) -> list[URL]:
        response = await self.http_adapter.send_request_and_raise_for_status(
            method=HTTPMethod.GET, url="SoliSpirit/mtproto/refs/heads/master/all_proxies.txt"
        )
        content = response.content.decode()

        return [URL(url) for url in content.split("\n")]

    async def get_urls_for_ping(self) -> list[URL]:
        proxy_urls = await self.get_proxies_list()

        urls_to_ping = []
        for url in proxy_urls:
            proxy_server = self._get_params_from_proxy(url.params)

            if not proxy_server.host or not proxy_server.port:
                continue
            urls_to_ping.append(url)

        return urls_to_ping

    async def get_host_latency(self, proxy_url: URL) -> ProxyBaseDTO:
        proxy_server = self._get_params_from_proxy(proxy_url.params)
        started_at = time.monotonic()

        try:
            async with asyncio.timeout(PROXY_PING_TIMEOUT):
                _, writer = await asyncio.open_connection(host=proxy_server.host, port=proxy_server.port)
                with suppress(Exception):
                    writer.close()
                    await writer.wait_closed()
        except Exception:  # noqa: BLE001
            return ProxyBaseDTO(url=proxy_url, latency=None, status=ProxyStatusEnum.disabled)

        latency = int((time.monotonic() - started_at) * 1000)
        return ProxyBaseDTO(url=proxy_url, latency=latency, status=ProxyStatusEnum.enabled)

    @staticmethod
    def _get_params_from_proxy(params: QueryParams) -> ProxyServerDTO:
        return ProxyServerDTO(host=params.get("server"), port=params.get("port"))
