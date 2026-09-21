"""
Фейковая MTProto-прокси для юнит-тестов `MTProxyChecker`.

Сеть не нужна: `asyncio.open_connection` подменяется в тестах и отдаёт настоящий `asyncio.StreamReader`
и мок `asyncio.StreamWriter`. Всё, что проверка пишет в writer, попадает в `FakeMTProxy`, который играет
серверную сторону протокола: сверяет подпись Fake-TLS ClientHello, отвечает ServerHello, снимает
obfuscated2-шифрование с запроса и кладёт в reader ответ, зашифрованный ключами сервера.

Криптография здесь написана независимо от проверяемого кода: если проверка начнёт выводить ключи или
подписывать handshake иначе, фейковая прокси перестанет её понимать и тесты упадут.
"""

import asyncio
import base64
import hashlib
import hmac
import os
import struct
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from unittest.mock import MagicMock

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

PROXY_HOST = "proxy.example.com"
PROXY_PORT = 8443
DC_ID = 4
DEFAULT_DC_ID = 2

CHECK_TIMEOUT = 1.0
# Таймаут для сценариев, где прокси молчит: ждать секунду ради такого теста незачем.
SILENT_PROXY_TIMEOUT = 0.05

# `time.monotonic` мокается этими значениями: разница точно представима во float, latency ровно 125 мс.
CHECK_STARTED_AT = 1000.0
CHECK_FINISHED_AT = 1000.125
EXPECTED_LATENCY_MS = 125

SECRET_KEY = bytes.fromhex("00112233445566778899aabbccddeeff")
FOREIGN_SECRET_KEY = bytes.fromhex("ffeeddccbbaa99887766554433221100")
FAKE_TLS_DOMAIN = "www.google.com"

PLAIN_SECRET = SECRET_KEY.hex()
PADDED_SECRET = "dd" + SECRET_KEY.hex()
FAKE_TLS_SECRET = "ee" + SECRET_KEY.hex() + FAKE_TLS_DOMAIN.encode().hex()
FAKE_TLS_SECRET_BASE64 = base64.urlsafe_b64encode(bytes.fromhex(FAKE_TLS_SECRET)).decode().rstrip("=")

# Значения протокола прибиты гвоздями намеренно, а не взяты из `MTProxyChecker`:
# тест должен упасть, если проверка начнёт слать что-то другое.
TAG_INTERMEDIATE = b"\xee\xee\xee\xee"
TAG_PADDED_INTERMEDIATE = b"\xdd\xdd\xdd\xdd"
REQ_PQ_MULTI = 0xBE7E8EF1
RES_PQ = 0x05162463
VECTOR = 0x1CB5C415
NONCE_SIZE = 16
REQ_PQ_MULTI_BODY_SIZE = 20  # конструктор 4 + nonce 16
REQ_PQ_MULTI_MESSAGE_SIZE = 40  # auth_key_id 8 + msg_id 8 + длина 4 + конструктор 4 + nonce 16
MAX_FRAME_SIZE = 1 << 16
QUICK_ACK_FLAG = 0x80000000

TLS_CLIENT_HELLO_SIZE = 517
TLS_RANDOM = slice(11, 43)
TLS_TIMESTAMP_TOLERANCE = 5
TLS_HANDSHAKE = 0x16
TLS_ALERT = 0x15
TLS_APPLICATION_DATA = 0x17
TLS_CHANGE_CIPHER_SPEC_RECORD = b"\x14\x03\x03\x00\x01\x01"
TLS_ALERT_RECORD = b"\x15\x03\x03\x00\x02\x02\x28"


class Hangup(StrEnum):
    """Что прокси делает с соединением после своего ответа."""

    close = "close"
    reset = "reset"


@dataclass(slots=True, frozen=True)
class ClientRequest:
    """Запрос проверки, расшифрованный на стороне прокси."""

    protocol_tag: bytes
    dc_id: int
    frame_size: int
    auth_key_id: bytes
    message_size: int
    constructor: int
    nonce: bytes


# Получает расшифрованный запрос, возвращает открытый поток байт ответа (кадры intermediate с длиной).
Responder = Callable[[ClientRequest], bytes]
# Получает ClientHello, возвращает сырые байты ответа прокси.
TlsResponder = Callable[[bytes], bytes]


def tls_record(record_type: int, body: bytes) -> bytes:
    return bytes((record_type,)) + b"\x03\x03" + struct.pack(">H", len(body)) + body


def intermediate_frame(message: bytes) -> bytes:
    return struct.pack("<I", len(message)) + message


def build_res_pq(
    nonce: bytes, *, constructor: int = RES_PQ, auth_key_id: bytes = b"\0" * 8, server_nonce: bytes | None = None
) -> bytes:
    """Незашифрованное сообщение `resPQ`: nonce, server_nonce, pq и список отпечатков ключей сервера."""
    pq = b"\x08" + os.urandom(8) + b"\0" * 3
    fingerprints = struct.pack("<II", VECTOR, 1) + os.urandom(8)
    body = struct.pack("<I", constructor) + nonce + (server_nonce or os.urandom(16)) + pq + fingerprints
    msg_id = int(time.time() * 2**32) | 1
    return auth_key_id + struct.pack("<qi", msg_id, len(body)) + body


def respond_with_res_pq(request: ClientRequest) -> bytes:
    return intermediate_frame(build_res_pq(request.nonce))


def respond_with_foreign_nonce(_: ClientRequest) -> bytes:
    return intermediate_frame(build_res_pq(os.urandom(16)))


def respond_with_wrong_constructor(request: ClientRequest) -> bytes:
    return intermediate_frame(build_res_pq(request.nonce, constructor=REQ_PQ_MULTI))


def respond_with_encrypted_message(request: ClientRequest) -> bytes:
    """Ненулевой auth_key_id: так выглядит уже зашифрованное сообщение, а не ответ на req_pq_multi."""
    return intermediate_frame(build_res_pq(request.nonce, auth_key_id=os.urandom(8)))


def respond_with_truncated_res_pq(request: ClientRequest) -> bytes:
    return intermediate_frame(build_res_pq(request.nonce)[: REQ_PQ_MULTI_MESSAGE_SIZE - 1])


def respond_with_quick_ack_flag(request: ClientRequest) -> bytes:
    """Старший бит длины кадра — флаг quick ack, в длину он не входит."""
    message = build_res_pq(request.nonce)
    return struct.pack("<I", len(message) | QUICK_ACK_FLAG) + message


def respond_with_frame_size(frame_size: int) -> Responder:
    """Кадр с заданной длиной и без тела: проверка должна отбросить его по одному заголовку."""

    def responder(_: ClientRequest) -> bytes:
        return struct.pack("<I", frame_size)

    return responder


def respond_with_incomplete_frame(request: ClientRequest) -> bytes:
    """Заголовок обещает полный resPQ, но приходит только его начало."""
    return intermediate_frame(build_res_pq(request.nonce))[:-1]


def server_hello_record(client_hello: bytes) -> bytes:
    """ServerHello с нулевым полем random: его подписывают уже вместе со всем ответом."""
    session_id = client_hello[44:76]
    body = b"\x03\x03" + b"\0" * 32 + b"\x20" + session_id + b"\x13\x01\x00"
    body += bytes.fromhex("002e002b0002030400330024001d0020") + os.urandom(32)
    return tls_record(TLS_HANDSHAKE, b"\x02" + len(body).to_bytes(3, "big") + body)


def server_hello_signed_by(secret_key: bytes) -> TlsResponder:
    """
    Ответ Fake-TLS прокси: ServerHello, ChangeCipherSpec и Application Data.

    Поле random ServerHello — HMAC-SHA256 по секрету от client random и всего ответа с обнулённым random.
    """

    def responder(client_hello: bytes) -> bytes:
        response = bytearray(
            server_hello_record(client_hello)
            + TLS_CHANGE_CIPHER_SPEC_RECORD
            + tls_record(TLS_APPLICATION_DATA, os.urandom(117))
        )
        response[TLS_RANDOM] = hmac.new(secret_key, client_hello[TLS_RANDOM] + bytes(response), hashlib.sha256).digest()
        return bytes(response)

    return responder


def respond_with_nothing(_: bytes) -> bytes:
    return b""


def respond_with_tls_alert(_: bytes) -> bytes:
    return TLS_ALERT_RECORD


def respond_with_short_server_hello(_: bytes) -> bytes:
    """Handshake-запись, в которую не помещается даже поле random."""
    return tls_record(TLS_HANDSHAKE, b"\x02\x00\x00\x02\x03\x03")


def respond_with_server_hello_then_alert(client_hello: bytes) -> bytes:
    return server_hello_record(client_hello) + TLS_CHANGE_CIPHER_SPEC_RECORD + TLS_ALERT_RECORD


def respond_with_truncated_server_hello(client_hello: bytes) -> bytes:
    return server_hello_record(client_hello)[:20]


def is_signed_client_hello(client_hello: bytes, secret_key: bytes) -> bool:
    """
    Проверка ClientHello так, как её делает MTProxy.

    random = HMAC-SHA256(secret, ClientHello с нулевым random), где последние 4 байта XOR-нуты с unix-временем.
    """
    client_random = client_hello[TLS_RANDOM]
    unsigned = bytearray(client_hello)
    unsigned[TLS_RANDOM] = b"\0" * 32
    digest = hmac.new(secret_key, bytes(unsigned), hashlib.sha256).digest()
    if not hmac.compare_digest(client_random[:28], digest[:28]):
        return False
    timestamp = bytes(a ^ b for a, b in zip(client_random[28:], digest[28:], strict=True))
    return abs(struct.unpack("<I", timestamp)[0] - time.time()) <= TLS_TIMESTAMP_TOLERANCE


async def hang_forever(*_: Any, **__: Any) -> None:
    """Подключение, которое никогда не устанавливается."""
    await asyncio.Event().wait()


class _ServerObfuscation:
    """Серверная сторона obfuscated2: ключи выводятся из первых 64 байт соединения и секрета."""

    def __init__(self, init: bytes, secret_key: bytes) -> None:
        reversed_part = init[8:56][::-1]
        decrypt_key = hashlib.sha256(init[8:40] + secret_key).digest()
        encrypt_key = hashlib.sha256(reversed_part[:32] + secret_key).digest()
        self._decryptor = Cipher(algorithms.AES(decrypt_key), modes.CTR(init[40:56])).decryptor()
        self._encryptor = Cipher(algorithms.AES(encrypt_key), modes.CTR(reversed_part[32:48])).encryptor()

        decrypted_init = self._decryptor.update(init)
        self.protocol_tag = decrypted_init[56:60]
        self.dc_id = struct.unpack("<h", decrypted_init[60:62])[0]

    def decrypt(self, data: bytes) -> bytes:
        return self._decryptor.update(data)

    def encrypt(self, data: bytes) -> bytes:
        return self._encryptor.update(data)


class FakeMTProxy:
    """
    Прокси, которая понимает запрос проверки и отвечает по заданному сценарию.

    :param secret_key: ключ, которым прокси снимает obfuscated2 с запроса.
    :param respond: ответ на запрос; `None` — прокси молчит.
    :param hangup: что сделать с соединением после ответа (или вместо него, если `respond=None`).
    :param tls_respond: ответ на Fake-TLS ClientHello; по умолчанию — ServerHello, подписанный `secret_key`.
    :param hangup_after_hello: закрыть соединение сразу после ответа на ClientHello.
    :param tls_answer_record_size: на записи какого размера резать ответ поверх Fake-TLS.
    :param tls_records_before_answer: служебные TLS-записи, которые прокси шлёт перед ответом.
    """

    def __init__(
        self,
        secret_key: bytes = SECRET_KEY,
        *,
        respond: Responder | None = respond_with_res_pq,
        hangup: Hangup | None = None,
        tls_respond: TlsResponder | None = None,
        hangup_after_hello: bool = False,
        tls_answer_record_size: int = 16384,
        tls_records_before_answer: bytes = b"",
    ) -> None:
        self._secret_key = secret_key
        self._respond = respond
        self._hangup = hangup
        self._tls_respond = tls_respond or server_hello_signed_by(secret_key)
        self._hangup_after_hello = hangup_after_hello
        self._tls_answer_record_size = tls_answer_record_size
        self._tls_records_before_answer = tls_records_before_answer
        self._over_tls = False

        self.client_hellos: list[bytes] = []
        self.requests: list[ClientRequest] = []
        self.reader = asyncio.StreamReader()
        self.writer = MagicMock(spec=asyncio.StreamWriter)
        self.writer.write.side_effect = self._receive

    @property
    def connection(self) -> tuple[asyncio.StreamReader, MagicMock]:
        """То, что должен вернуть замоканный `asyncio.open_connection`."""
        return self.reader, self.writer

    def _receive(self, data: bytes) -> None:
        # Обычное obfuscated2-соединение не может начинаться с TLS handshake: проверка исключает такой префикс.
        if not self._over_tls and data.startswith(b"\x16\x03\x01"):
            self._receive_client_hello(data)
        else:
            self._receive_request(self._unwrap_tls_records(data) if self._over_tls else data)

    def _receive_client_hello(self, client_hello: bytes) -> None:
        self._over_tls = True
        self.client_hellos.append(client_hello)
        self.reader.feed_data(self._tls_respond(client_hello))
        if self._hangup_after_hello:
            self.reader.feed_eof()

    def _receive_request(self, data: bytes) -> None:
        obfuscation = _ServerObfuscation(data[:64], self._secret_key)
        plaintext = obfuscation.decrypt(data[64:])
        frame_size = struct.unpack("<I", plaintext[:4])[0]
        message = plaintext[4:][:frame_size]
        request = ClientRequest(
            protocol_tag=obfuscation.protocol_tag,
            dc_id=obfuscation.dc_id,
            frame_size=frame_size,
            auth_key_id=message[:8],
            message_size=struct.unpack("<i", message[16:20])[0],
            constructor=struct.unpack("<I", message[20:24])[0],
            nonce=message[24:40],
        )
        self.requests.append(request)

        if self._respond is not None:
            answer = obfuscation.encrypt(self._respond(request))
            self.reader.feed_data(self._wrap_in_tls_records(answer) if self._over_tls else answer)
        if self._hangup == Hangup.close:
            self.reader.feed_eof()
        elif self._hangup == Hangup.reset:
            self.reader.set_exception(ConnectionResetError("connection reset by proxy"))

    @staticmethod
    def _unwrap_tls_records(data: bytes) -> bytes:
        """Клиент после handshake шлёт ChangeCipherSpec и данные в записях Application Data."""
        assert data.startswith(TLS_CHANGE_CIPHER_SPEC_RECORD)
        payload, rest = b"", data.removeprefix(TLS_CHANGE_CIPHER_SPEC_RECORD)
        while rest:
            header, rest = rest[:5], rest[5:]
            assert header.startswith(b"\x17\x03\x03")
            size = struct.unpack(">H", header[3:])[0]
            payload, rest = payload + rest[:size], rest[size:]
        return payload

    def _wrap_in_tls_records(self, data: bytes) -> bytes:
        size = self._tls_answer_record_size
        records = (tls_record(TLS_APPLICATION_DATA, data[i:][:size]) for i in range(0, len(data), size))
        return self._tls_records_before_answer + b"".join(records)
