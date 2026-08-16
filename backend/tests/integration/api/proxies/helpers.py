from collections.abc import Generator
from contextlib import asynccontextmanager

import respx
from httpx import Response
from respx import MockRouter

from app.api.constants import PLAIN_TEXT_MEDIA_TYPE


@asynccontextmanager
async def mocked_github_get_proxies(raw_proxies: str) -> Generator[MockRouter]:
    async with respx.mock(
        assert_all_mocked=True,
        base_url="https://raw.githubusercontent.com",
    ) as respx_mock:
        github_get_proxies = respx_mock.get(
            "/SoliSpirit/mtproto/refs/heads/master/all_proxies.txt", name="keycloak_token"
        )
        github_get_proxies.return_value = Response(
            status_code=200, headers={"Content-Type": PLAIN_TEXT_MEDIA_TYPE}, content=raw_proxies
        )
        yield respx_mock
