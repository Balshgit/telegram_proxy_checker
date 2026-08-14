from dataclasses import dataclass
from http import HTTPMethod

from httpx import URL

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
