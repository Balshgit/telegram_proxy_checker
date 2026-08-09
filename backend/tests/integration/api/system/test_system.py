from http import HTTPStatus

from httpx import AsyncClient


async def test_readiness_check(rest_client: AsyncClient) -> None:
    response = await rest_client.get("/api/readiness-check")
    assert response.status_code == HTTPStatus.OK
    assert response.content == b"null"


async def test_healthcheck(rest_client: AsyncClient) -> None:
    response = await rest_client.get("/api/healthcheck")
    assert response.status_code == HTTPStatus.OK
    assert response.content == b"null"
