import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from pytest_mock import MockerFixture

from app.infra.gateways.mtproto_checker import MTProxyChecker
from tests.unit.infra.gateways.helpers import CHECK_FINISHED_AT, CHECK_STARTED_AT, CHECK_TIMEOUT, DC_ID


@pytest.fixture
def checker() -> MTProxyChecker:
    return MTProxyChecker(timeout=CHECK_TIMEOUT, dc_id=DC_ID)


@pytest.fixture
def open_connection_mock(mocker: MockerFixture) -> AsyncMock:
    """Сеть в тестах недоступна: каждое подключение проверки уходит в этот мок."""
    return mocker.patch("app.infra.gateways.mtproto_checker.asyncio.open_connection", new_callable=AsyncMock)


@pytest.fixture
def time_mock(mocker: MockerFixture) -> MagicMock:
    """
    Модуль `time` внутри проверки: `monotonic` отдаёт заранее известные отметки, остальное — настоящее.

    Патчится имя в модуле проверки, а не `time.monotonic` глобально: на нём работают часы event loop.
    """
    time_mock = mocker.patch("app.infra.gateways.mtproto_checker.time", wraps=time)
    time_mock.monotonic.side_effect = [CHECK_STARTED_AT, CHECK_FINISHED_AT]
    return time_mock
