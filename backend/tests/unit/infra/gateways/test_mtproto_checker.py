import socket
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.proxies.constants import ProxyCheckError
from app.infra.gateways.mtproto_checker import MTProxyChecker, ProxyCheckResult
from tests.unit.infra.gateways.helpers import (
    CHECK_TIMEOUT,
    DC_ID,
    DEFAULT_DC_ID,
    EXPECTED_LATENCY_MS,
    FAKE_TLS_DOMAIN,
    FAKE_TLS_SECRET,
    FAKE_TLS_SECRET_BASE64,
    FOREIGN_SECRET_KEY,
    MAX_FRAME_SIZE,
    NONCE_SIZE,
    PADDED_SECRET,
    PLAIN_SECRET,
    PROXY_HOST,
    PROXY_PORT,
    REQ_PQ_MULTI,
    REQ_PQ_MULTI_BODY_SIZE,
    REQ_PQ_MULTI_MESSAGE_SIZE,
    SECRET_KEY,
    SILENT_PROXY_TIMEOUT,
    TAG_INTERMEDIATE,
    TAG_PADDED_INTERMEDIATE,
    TLS_CHANGE_CIPHER_SPEC_RECORD,
    TLS_CLIENT_HELLO_SIZE,
    FakeMTProxy,
    Hangup,
    Responder,
    TlsResponder,
    hang_forever,
    is_signed_client_hello,
    respond_with_encrypted_message,
    respond_with_foreign_nonce,
    respond_with_frame_size,
    respond_with_incomplete_frame,
    respond_with_nothing,
    respond_with_quick_ack_flag,
    respond_with_res_pq,
    respond_with_server_hello_then_alert,
    respond_with_short_server_hello,
    respond_with_tls_alert,
    respond_with_truncated_res_pq,
    respond_with_truncated_server_hello,
    respond_with_wrong_constructor,
    server_hello_signed_by,
)

ALL_SECRETS = [PLAIN_SECRET, PADDED_SECRET, FAKE_TLS_SECRET]
ALL_SECRET_IDS = ["plain", "dd", "ee"]


@pytest.mark.parametrize(
    "secret",
    [PLAIN_SECRET, PADDED_SECRET, FAKE_TLS_SECRET, FAKE_TLS_SECRET_BASE64, f"  {PLAIN_SECRET.upper()}\n"],
    ids=["plain", "dd", "ee", "ee-base64", "hex-with-whitespace"],
)
async def test_check_connected_proxy(
    checker: MTProxyChecker, open_connection_mock: AsyncMock, time_mock: MagicMock, secret: str
) -> None:
    proxy = FakeMTProxy()
    open_connection_mock.return_value = proxy.connection

    result = await checker.check(PROXY_HOST, PROXY_PORT, secret)

    assert result == ProxyCheckResult(is_connected=True, latency_ms=EXPECTED_LATENCY_MS, error=None)
    open_connection_mock.assert_awaited_once_with(PROXY_HOST, PROXY_PORT)
    assert len(proxy.requests) == 1


@pytest.mark.parametrize(
    "secret, protocol_tag",
    [
        (PLAIN_SECRET, TAG_INTERMEDIATE),
        (PADDED_SECRET, TAG_PADDED_INTERMEDIATE),
        (FAKE_TLS_SECRET, TAG_PADDED_INTERMEDIATE),
    ],
    ids=ALL_SECRET_IDS,
)
async def test_check_sends_req_pq_multi_to_configured_dc(
    checker: MTProxyChecker, open_connection_mock: AsyncMock, secret: str, protocol_tag: bytes
) -> None:
    proxy = FakeMTProxy()
    open_connection_mock.return_value = proxy.connection

    await checker.check(PROXY_HOST, PROXY_PORT, secret)

    [request] = proxy.requests
    assert request.protocol_tag == protocol_tag
    assert request.dc_id == DC_ID
    assert request.auth_key_id == b"\0" * 8
    assert request.constructor == REQ_PQ_MULTI
    assert request.message_size == REQ_PQ_MULTI_BODY_SIZE
    assert len(request.nonce) == NONCE_SIZE


async def test_check_sends_unpadded_frame_for_plain_secret(
    checker: MTProxyChecker, open_connection_mock: AsyncMock
) -> None:
    proxy = FakeMTProxy()
    open_connection_mock.return_value = proxy.connection

    await checker.check(PROXY_HOST, PROXY_PORT, PLAIN_SECRET)

    [request] = proxy.requests
    assert request.frame_size == REQ_PQ_MULTI_MESSAGE_SIZE


async def test_check_uses_default_dc(open_connection_mock: AsyncMock) -> None:
    proxy = FakeMTProxy()
    open_connection_mock.return_value = proxy.connection

    result = await MTProxyChecker(timeout=CHECK_TIMEOUT).check(PROXY_HOST, PROXY_PORT, PLAIN_SECRET)

    assert result.is_connected
    [request] = proxy.requests
    assert request.dc_id == DEFAULT_DC_ID


async def test_check_uses_fresh_nonce_for_every_check(checker: MTProxyChecker, open_connection_mock: AsyncMock) -> None:
    first_proxy, second_proxy = FakeMTProxy(), FakeMTProxy()
    open_connection_mock.side_effect = [first_proxy.connection, second_proxy.connection]

    await checker.check(PROXY_HOST, PROXY_PORT, PLAIN_SECRET)
    await checker.check(PROXY_HOST, PROXY_PORT, PLAIN_SECRET)

    assert first_proxy.requests[0].nonce != second_proxy.requests[0].nonce


@pytest.mark.parametrize("secret", [FAKE_TLS_SECRET, FAKE_TLS_SECRET_BASE64], ids=["hex", "base64"])
async def test_check_sends_signed_client_hello_for_fake_tls_secret(
    checker: MTProxyChecker, open_connection_mock: AsyncMock, secret: str
) -> None:
    proxy = FakeMTProxy()
    open_connection_mock.return_value = proxy.connection

    await checker.check(PROXY_HOST, PROXY_PORT, secret)

    [client_hello] = proxy.client_hellos
    assert len(client_hello) == TLS_CLIENT_HELLO_SIZE
    assert FAKE_TLS_DOMAIN.encode() in client_hello
    assert is_signed_client_hello(client_hello, SECRET_KEY)
    assert not is_signed_client_hello(client_hello, FOREIGN_SECRET_KEY)
    writes = [call.args[0] for call in proxy.writer.write.call_args_list]
    assert writes[0] == client_hello
    assert writes[1].startswith(TLS_CHANGE_CIPHER_SPEC_RECORD)


@pytest.mark.parametrize("secret", [PLAIN_SECRET, PADDED_SECRET], ids=["plain", "dd"])
async def test_check_does_not_send_client_hello_without_fake_tls(
    checker: MTProxyChecker, open_connection_mock: AsyncMock, secret: str
) -> None:
    proxy = FakeMTProxy()
    open_connection_mock.return_value = proxy.connection

    await checker.check(PROXY_HOST, PROXY_PORT, secret)

    assert proxy.client_hellos == []
    proxy.writer.write.assert_called_once()


async def test_check_accepts_quick_ack_flag_in_frame_length(
    checker: MTProxyChecker, open_connection_mock: AsyncMock
) -> None:
    proxy = FakeMTProxy(respond=respond_with_quick_ack_flag)
    open_connection_mock.return_value = proxy.connection

    result = await checker.check(PROXY_HOST, PROXY_PORT, PLAIN_SECRET)

    assert result.is_connected


async def test_check_reads_answer_split_into_many_tls_records(
    checker: MTProxyChecker, open_connection_mock: AsyncMock
) -> None:
    proxy = FakeMTProxy(tls_answer_record_size=7)
    open_connection_mock.return_value = proxy.connection

    result = await checker.check(PROXY_HOST, PROXY_PORT, FAKE_TLS_SECRET)

    assert result.is_connected


async def test_check_skips_service_tls_records_before_answer(
    checker: MTProxyChecker, open_connection_mock: AsyncMock
) -> None:
    proxy = FakeMTProxy(tls_records_before_answer=TLS_CHANGE_CIPHER_SPEC_RECORD)
    open_connection_mock.return_value = proxy.connection

    result = await checker.check(PROXY_HOST, PROXY_PORT, FAKE_TLS_SECRET)

    assert result.is_connected


@pytest.mark.parametrize(
    "secret",
    [
        "",
        "a",
        "секрет",
        "not a secret!",
        SECRET_KEY[:15].hex(),
        "ab" + SECRET_KEY.hex(),
        "dd" + SECRET_KEY.hex() + "00",
        "ee" + SECRET_KEY.hex(),
    ],
    ids=[
        "empty",
        "broken-base64-padding",
        "non-ascii",
        "garbage-of-wrong-length",
        "short-key",
        "unknown-prefix",
        "dd-with-extra-byte",
        "ee-without-domain",
    ],
)
async def test_check_rejects_bad_secret_without_connecting(
    checker: MTProxyChecker, open_connection_mock: AsyncMock, secret: str
) -> None:
    result = await checker.check(PROXY_HOST, PROXY_PORT, secret)

    assert result == ProxyCheckResult(is_connected=False, latency_ms=None, error=ProxyCheckError.bad_secret)
    open_connection_mock.assert_not_awaited()


@pytest.mark.parametrize(
    "error",
    [ConnectionRefusedError(), socket.gaierror(socket.EAI_NONAME, "Name or service not known"), OSError()],
    ids=["refused", "dns", "os-error"],
)
async def test_check_reports_connect_failed(
    checker: MTProxyChecker, open_connection_mock: AsyncMock, error: OSError
) -> None:
    open_connection_mock.side_effect = error

    result = await checker.check(PROXY_HOST, PROXY_PORT, PLAIN_SECRET)

    assert result == ProxyCheckResult(is_connected=False, latency_ms=None, error=ProxyCheckError.connect_failed)


@pytest.mark.parametrize("secret", ALL_SECRETS, ids=ALL_SECRET_IDS)
async def test_check_reports_connect_failed_when_proxy_drops_request(
    checker: MTProxyChecker, open_connection_mock: AsyncMock, secret: str
) -> None:
    proxy = FakeMTProxy()
    proxy.writer.drain.side_effect = ConnectionResetError()
    open_connection_mock.return_value = proxy.connection

    result = await checker.check(PROXY_HOST, PROXY_PORT, secret)

    assert result == ProxyCheckResult(is_connected=False, latency_ms=None, error=ProxyCheckError.connect_failed)
    proxy.writer.close.assert_called_once()


async def test_check_reports_timeout_when_connect_hangs(open_connection_mock: AsyncMock) -> None:
    open_connection_mock.side_effect = hang_forever

    result = await MTProxyChecker(timeout=SILENT_PROXY_TIMEOUT).check(PROXY_HOST, PROXY_PORT, PLAIN_SECRET)

    assert result == ProxyCheckResult(is_connected=False, latency_ms=None, error=ProxyCheckError.timeout)


@pytest.mark.parametrize("secret", ALL_SECRETS, ids=ALL_SECRET_IDS)
async def test_check_reports_timeout_when_proxy_is_silent(open_connection_mock: AsyncMock, secret: str) -> None:
    proxy = FakeMTProxy(respond=None)
    open_connection_mock.return_value = proxy.connection

    result = await MTProxyChecker(timeout=SILENT_PROXY_TIMEOUT).check(PROXY_HOST, PROXY_PORT, secret)

    assert result == ProxyCheckResult(is_connected=False, latency_ms=None, error=ProxyCheckError.timeout)
    proxy.writer.close.assert_called_once()


async def test_check_reports_timeout_when_proxy_ignores_client_hello(open_connection_mock: AsyncMock) -> None:
    proxy = FakeMTProxy(tls_respond=respond_with_nothing)
    open_connection_mock.return_value = proxy.connection

    result = await MTProxyChecker(timeout=SILENT_PROXY_TIMEOUT).check(PROXY_HOST, PROXY_PORT, FAKE_TLS_SECRET)

    assert result == ProxyCheckResult(is_connected=False, latency_ms=None, error=ProxyCheckError.timeout)
    assert proxy.requests == []


@pytest.mark.parametrize("secret", ALL_SECRETS, ids=ALL_SECRET_IDS)
@pytest.mark.parametrize(
    "respond, hangup",
    [
        (None, Hangup.close),
        (None, Hangup.reset),
        (respond_with_incomplete_frame, Hangup.close),
        (respond_with_frame_size(REQ_PQ_MULTI_MESSAGE_SIZE), Hangup.close),
    ],
    ids=["closed", "reset", "incomplete-frame", "frame-header-only"],
)
async def test_check_reports_no_answer(
    checker: MTProxyChecker, open_connection_mock: AsyncMock, secret: str, respond: Responder | None, hangup: Hangup
) -> None:
    proxy = FakeMTProxy(respond=respond, hangup=hangup)
    open_connection_mock.return_value = proxy.connection

    result = await checker.check(PROXY_HOST, PROXY_PORT, secret)

    assert result == ProxyCheckResult(is_connected=False, latency_ms=None, error=ProxyCheckError.no_answer)


@pytest.mark.parametrize("secret", ALL_SECRETS, ids=ALL_SECRET_IDS)
@pytest.mark.parametrize(
    "respond",
    [
        respond_with_foreign_nonce,
        respond_with_wrong_constructor,
        respond_with_encrypted_message,
        respond_with_truncated_res_pq,
        respond_with_frame_size(0),
        respond_with_frame_size(3),
        respond_with_frame_size(MAX_FRAME_SIZE + 1),
    ],
    ids=[
        "foreign-nonce",
        "wrong-constructor",
        "encrypted-message",
        "truncated-res-pq",
        "empty-frame",
        "frame-too-small",
        "frame-too-large",
    ],
)
async def test_check_reports_bad_answer(
    checker: MTProxyChecker, open_connection_mock: AsyncMock, secret: str, respond: Responder
) -> None:
    proxy = FakeMTProxy(respond=respond)
    open_connection_mock.return_value = proxy.connection

    result = await checker.check(PROXY_HOST, PROXY_PORT, secret)

    assert result == ProxyCheckResult(is_connected=False, latency_ms=None, error=ProxyCheckError.bad_answer)


@pytest.mark.parametrize(
    "tls_respond, hangup_after_hello",
    [
        (respond_with_tls_alert, False),
        (respond_with_short_server_hello, False),
        (respond_with_server_hello_then_alert, False),
        (respond_with_truncated_server_hello, True),
        (respond_with_nothing, True),
    ],
    ids=["alert", "short-server-hello", "alert-after-server-hello", "truncated-server-hello", "closed-on-hello"],
)
async def test_check_reports_tls_rejected(
    checker: MTProxyChecker,
    open_connection_mock: AsyncMock,
    tls_respond: TlsResponder,
    hangup_after_hello: bool,
) -> None:
    proxy = FakeMTProxy(tls_respond=tls_respond, hangup_after_hello=hangup_after_hello)
    open_connection_mock.return_value = proxy.connection

    result = await checker.check(PROXY_HOST, PROXY_PORT, FAKE_TLS_SECRET)

    assert result == ProxyCheckResult(is_connected=False, latency_ms=None, error=ProxyCheckError.tls_rejected)
    assert proxy.requests == []
    proxy.writer.close.assert_called_once()


async def test_check_reports_tls_bad_hmac(checker: MTProxyChecker, open_connection_mock: AsyncMock) -> None:
    proxy = FakeMTProxy(tls_respond=server_hello_signed_by(FOREIGN_SECRET_KEY))
    open_connection_mock.return_value = proxy.connection

    result = await checker.check(PROXY_HOST, PROXY_PORT, FAKE_TLS_SECRET)

    assert result == ProxyCheckResult(is_connected=False, latency_ms=None, error=ProxyCheckError.tls_bad_hmac)
    assert proxy.requests == []


@pytest.mark.parametrize(
    "respond, secret",
    [
        (respond_with_res_pq, PLAIN_SECRET),
        (respond_with_foreign_nonce, PADDED_SECRET),
        (None, FAKE_TLS_SECRET),
    ],
    ids=["connected", "bad-answer", "no-answer"],
)
async def test_check_closes_connection(
    checker: MTProxyChecker, open_connection_mock: AsyncMock, respond: Responder | None, secret: str
) -> None:
    proxy = FakeMTProxy(respond=respond, hangup=Hangup.close)
    open_connection_mock.return_value = proxy.connection

    await checker.check(PROXY_HOST, PROXY_PORT, secret)

    proxy.writer.close.assert_called_once()
    proxy.writer.wait_closed.assert_awaited_once()


async def test_check_ignores_errors_on_connection_close(
    checker: MTProxyChecker, open_connection_mock: AsyncMock, time_mock: MagicMock
) -> None:
    proxy = FakeMTProxy()
    proxy.writer.wait_closed.side_effect = ConnectionResetError()
    open_connection_mock.return_value = proxy.connection

    result = await checker.check(PROXY_HOST, PROXY_PORT, PLAIN_SECRET)

    assert result == ProxyCheckResult(is_connected=True, latency_ms=EXPECTED_LATENCY_MS, error=None)
    proxy.writer.wait_closed.assert_awaited_once()
