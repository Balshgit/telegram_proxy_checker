"""
Проверка MTProto-прокси тем же способом, каким к ней подключается Telegram.

Голый TCP-коннект показывает только то, что порт открыт. `MTProxyChecker` выполняет настоящий handshake:

1. для `ee`-секретов — Fake-TLS ClientHello, подписанный HMAC по секрету, и сверка HMAC в ответе сервера;
2. obfuscated2-инициализация с ключами, выведенными из секрета;
3. отправка незашифрованного `req_pq_multi` в DC Telegram через прокси;
4. ожидание `resPQ` с нашим nonce.

Пришёл `resPQ` — значит, прокси знает секрет и реально пересылает трафик до серверов Telegram.
Аккаунт, api_id и авторизация не нужны: это первый шаг создания auth key, его делает любой клиент.
"""

import asyncio
import base64
import binascii
import hashlib
import hmac
import os
import struct
import time
from contextlib import suppress
from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


class ProxyCheckError(StrEnum):
    bad_secret = "bad_secret"
    connect_failed = "connect_failed"
    tls_rejected = "tls_rejected"  # в ответ на ClientHello пришёл не ServerHello: не тот секрет или не MTProxy
    tls_bad_hmac = "tls_bad_hmac"  # ServerHello пришёл, но подписан не нашим секретом
    no_answer = "no_answer"  # прокси закрыла соединение, не дождавшись ответа Telegram
    bad_answer = "bad_answer"  # пришло что-то, но не resPQ на наш запрос
    timeout = "timeout"  # прокси молчит: обычно так MTProxy реагирует на неверный секрет


class SecretMode(StrEnum):
    plain = "plain"
    padded = "dd"
    fake_tls = "ee"


@dataclass(slots=True, frozen=True)
class ProxyCheckResult:
    is_connected: bool
    latency_ms: int | None = None
    error: ProxyCheckError | None = None


@dataclass(slots=True, frozen=True)
class MTProxySecret:
    KEY_SIZE: ClassVar[int] = 16
    PREFIX_PADDED: ClassVar[int] = 0xDD
    PREFIX_FAKE_TLS: ClassVar[int] = 0xEE

    key: bytes
    mode: SecretMode
    domain: str = ""

    @classmethod
    def parse(cls, raw: str) -> MTProxySecret:
        """Секрет в ссылках бывает и в hex, и в base64url (часто для `ee`)."""
        raw = raw.strip()
        try:
            data = bytes.fromhex(raw)
        except ValueError:
            try:
                data = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
            except (binascii.Error, ValueError) as exc:
                raise ValueError("secret is neither hex nor base64") from exc

        if len(data) == cls.KEY_SIZE:
            return cls(key=data, mode=SecretMode.plain)
        if len(data) == cls.KEY_SIZE + 1 and data[0] == cls.PREFIX_PADDED:
            return cls(key=data[1:], mode=SecretMode.padded)
        if len(data) > cls.KEY_SIZE + 1 and data[0] == cls.PREFIX_FAKE_TLS:
            domain = data[cls.KEY_SIZE + 1:].decode("ascii", "ignore")  # fmt: skip
            return cls(key=data[1: cls.KEY_SIZE + 1], mode=SecretMode.fake_tls, domain=domain)  # fmt: skip
        raise ValueError(f"unsupported secret format ({len(data)} bytes)")


class Obfuscated2Cipher:
    """Клиентская сторона obfuscated2: 64 случайных байта задают ключи AES-256-CTR в обе стороны."""

    INIT_SIZE: ClassVar[int] = 64
    ABRIDGED_FIRST_BYTE: ClassVar[int] = 0xEF
    TAG_INTERMEDIATE: ClassVar[bytes] = b"\xee\xee\xee\xee"
    TAG_PADDED_INTERMEDIATE: ClassVar[bytes] = b"\xdd\xdd\xdd\xdd"
    FORBIDDEN_INIT_PREFIXES: ClassVar[frozenset[bytes]] = frozenset(
        {b"HEAD", b"POST", b"GET ", b"OPTI", b"\x16\x03\x01\x02", TAG_INTERMEDIATE, TAG_PADDED_INTERMEDIATE}
    )

    def __init__(self, secret_key: bytes, protocol_tag: bytes, dc_id: int) -> None:
        init = self._random_init()
        init[56:60] = protocol_tag
        init[60:62] = struct.pack("<h", dc_id)

        reversed_part = bytes(init[8:56])[::-1]
        enc_key = hashlib.sha256(bytes(init[8:40]) + secret_key).digest()
        dec_key = hashlib.sha256(reversed_part[:32] + secret_key).digest()
        self._encryptor = Cipher(algorithms.AES(enc_key), modes.CTR(bytes(init[40:56]))).encryptor()
        self._decryptor = Cipher(algorithms.AES(dec_key), modes.CTR(reversed_part[32:48])).decryptor()

        encrypted = self._encryptor.update(bytes(init))
        self.header = bytes(init[:56]) + encrypted[56:64]

    @classmethod
    def _random_init(cls) -> bytearray:
        while True:
            init = bytearray(os.urandom(cls.INIT_SIZE))
            if (
                init[0] != cls.ABRIDGED_FIRST_BYTE
                and bytes(init[:4]) not in cls.FORBIDDEN_INIT_PREFIXES
                and init[4:8] != b"\0\0\0\0"
            ):
                return init

    def encrypt(self, data: bytes) -> bytes:
        return self._encryptor.update(data)

    def decrypt(self, data: bytes) -> bytes:
        return self._decryptor.update(data)


class ObfuscatedStreamReader:
    """Читает из сокета ответ прокси, снимая TLS-обёртку (для `ee`) и obfuscated2-шифрование."""

    def __init__(self, reader: asyncio.StreamReader, cipher: Obfuscated2Cipher, over_tls: bool) -> None:
        self._reader = reader
        self._cipher = cipher
        self._over_tls = over_tls
        self._buffer = b""

    async def read_exactly(self, size: int) -> bytes:
        while len(self._buffer) < size:
            self._buffer += self._cipher.decrypt(await self._read_chunk())
        data, self._buffer = self._buffer[:size], self._buffer[size:]
        return data

    async def _read_chunk(self) -> bytes:
        if not self._over_tls:
            chunk = await self._reader.read(4096)
            if not chunk:
                raise asyncio.IncompleteReadError(self._buffer, None)
            return chunk
        while True:
            record_type, record = await MTProxyChecker.read_tls_record(self._reader)
            if record_type == MTProxyChecker.TLS_RECORD_APPLICATION_DATA:
                return record[MTProxyChecker.TLS_RECORD_HEADER_SIZE:]  # fmt: skip


@dataclass(slots=True, frozen=True)
class MTProxyChecker:
    """
    Проверяет MTProto-прокси полным handshake до DC Telegram.

    :param timeout: общий таймаут на одну проверку (коннект + handshake + ответ Telegram), секунды.
    :param dc_id: DC Telegram, к которому прокси должна переслать запрос.
    """

    REQ_PQ_MULTI: ClassVar[int] = 0xBE7E8EF1
    RES_PQ: ClassVar[int] = 0x05162463
    MAX_RANDOM_PADDING: ClassVar[int] = 16

    TLS_RECORD_HANDSHAKE: ClassVar[int] = 0x16
    TLS_RECORD_CHANGE_CIPHER_SPEC: ClassVar[int] = 0x14
    TLS_RECORD_APPLICATION_DATA: ClassVar[int] = 0x17
    TLS_RECORD_HEADER_SIZE: ClassVar[int] = 5
    TLS_RANDOM_OFFSET: ClassVar[int] = 11
    TLS_RANDOM_SIZE: ClassVar[int] = 32
    TLS_CLIENT_HELLO_SIZE: ClassVar[int] = 517
    TLS_MAX_RECORD_PAYLOAD: ClassVar[int] = 16384
    TLS_CHANGE_CIPHER_SPEC: ClassVar[bytes] = b"\x14\x03\x03\x00\x01\x01"

    FRAME_LENGTH_SIZE: ClassVar[int] = 4
    MIN_FRAME_SIZE: ClassVar[int] = 4
    MAX_FRAME_SIZE: ClassVar[int] = 1 << 16
    # Раскладка ответа resPQ: 8 байт auth_key_id, 8 msg_id, 4 длина, 4 конструктор, 16 nonce.
    RES_PQ_CONSTRUCTOR_SLICE: ClassVar[slice] = slice(20, 24)
    RES_PQ_NONCE_SLICE: ClassVar[slice] = slice(24, 40)
    RES_PQ_MIN_SIZE: ClassVar[int] = 40

    timeout: float
    dc_id: int = 2

    async def check(self, host: str, port: int, secret: str) -> ProxyCheckResult:
        """Latency в результате — время от начала коннекта до ответа `resPQ` от Telegram."""
        try:
            parsed_secret = MTProxySecret.parse(secret)
        except ValueError:
            return ProxyCheckResult(is_connected=False, error=ProxyCheckError.bad_secret)
        try:
            async with asyncio.timeout(self.timeout):
                return await self._check(host, port, parsed_secret)
        except TimeoutError:
            return ProxyCheckResult(is_connected=False, error=ProxyCheckError.timeout)
        except OSError:
            return ProxyCheckResult(is_connected=False, error=ProxyCheckError.connect_failed)

    async def _check(self, host: str, port: int, secret: MTProxySecret) -> ProxyCheckResult:
        started_at = time.monotonic()
        try:
            reader, writer = await asyncio.open_connection(host, port)
        except OSError:
            return ProxyCheckResult(is_connected=False, error=ProxyCheckError.connect_failed)

        try:
            over_tls = secret.mode == SecretMode.fake_tls
            if over_tls and (error := await self._fake_tls_handshake(reader, writer, secret)):
                return ProxyCheckResult(is_connected=False, error=error)

            padded = secret.mode in {SecretMode.padded, SecretMode.fake_tls}
            tag = Obfuscated2Cipher.TAG_PADDED_INTERMEDIATE if padded else Obfuscated2Cipher.TAG_INTERMEDIATE
            cipher = Obfuscated2Cipher(secret.key, tag, self.dc_id)
            nonce = os.urandom(16)
            payload = cipher.header + cipher.encrypt(self._frame_intermediate(self._build_req_pq_multi(nonce), padded))
            writer.write(self._wrap_in_tls_records(payload) if over_tls else payload)
            await writer.drain()

            stream = ObfuscatedStreamReader(reader, cipher, over_tls)
            try:
                length = struct.unpack("<I", await stream.read_exactly(self.FRAME_LENGTH_SIZE))[0] & 0x7FFFFFFF
                if not self.MIN_FRAME_SIZE <= length <= self.MAX_FRAME_SIZE:
                    return ProxyCheckResult(is_connected=False, error=ProxyCheckError.bad_answer)
                answer = await stream.read_exactly(length)
            except asyncio.IncompleteReadError, ConnectionError:
                return ProxyCheckResult(is_connected=False, error=ProxyCheckError.no_answer)

            if not self._is_res_pq_for(answer, nonce):
                return ProxyCheckResult(is_connected=False, error=ProxyCheckError.bad_answer)
            return ProxyCheckResult(is_connected=True, latency_ms=int((time.monotonic() - started_at) * 1000))
        finally:
            writer.close()
            with suppress(Exception):
                await writer.wait_closed()

    async def _fake_tls_handshake(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, secret: MTProxySecret
    ) -> ProxyCheckError | None:
        random_slice = slice(self.TLS_RANDOM_OFFSET, self.TLS_RANDOM_OFFSET + self.TLS_RANDOM_SIZE)

        hello = bytearray(self._build_client_hello(secret.domain))
        client_digest = bytearray(hmac.new(secret.key, bytes(hello), hashlib.sha256).digest())
        timestamp = struct.pack("<I", int(time.time()))
        for i, byte in enumerate(timestamp):
            client_digest[self.TLS_RANDOM_SIZE - 4 + i] ^= byte
        hello[random_slice] = client_digest
        writer.write(bytes(hello))
        await writer.drain()

        # Сервер отвечает ServerHello, ChangeCipherSpec и одной записью Application Data.
        try:
            record_type, response = await self.read_tls_record(reader)
            if record_type != self.TLS_RECORD_HANDSHAKE or len(response) < random_slice.stop:
                return ProxyCheckError.tls_rejected
            while record_type != self.TLS_RECORD_APPLICATION_DATA:
                record_type, record = await self.read_tls_record(reader)
                if record_type not in {self.TLS_RECORD_CHANGE_CIPHER_SPEC, self.TLS_RECORD_APPLICATION_DATA}:
                    return ProxyCheckError.tls_rejected
                response += record
        except asyncio.IncompleteReadError:
            return ProxyCheckError.tls_rejected

        signed = bytearray(response)
        server_random = bytes(signed[random_slice])
        signed[random_slice] = b"\0" * self.TLS_RANDOM_SIZE
        expected = hmac.new(secret.key, bytes(client_digest) + bytes(signed), hashlib.sha256).digest()
        if not hmac.compare_digest(server_random, expected):
            return ProxyCheckError.tls_bad_hmac
        return None

    @classmethod
    async def read_tls_record(cls, reader: asyncio.StreamReader) -> tuple[int, bytes]:
        """Возвращает тип записи и запись целиком (заголовок + тело)."""
        header = await reader.readexactly(cls.TLS_RECORD_HEADER_SIZE)
        body = await reader.readexactly(struct.unpack(">H", header[3:5])[0])
        return header[0], header + body

    @classmethod
    def _build_client_hello(cls, domain: str) -> bytes:
        """ClientHello в стиле Chrome/tdlib размером 517 байт; поле random нулевое и подписывается позже."""
        sni = domain.encode()
        ext = cls._tls_extension
        ciphers = cls._grease() + bytes.fromhex("130113021303c02bc02fc02cc030cca9cca8c013c014009c009d002f0035")
        extensions = b"".join(
            (
                ext(cls._grease(), b""),
                ext(b"\x00\x00", struct.pack(">HBH", len(sni) + 3, 0, len(sni)) + sni),
                ext(b"\x00\x17", b""),
                ext(b"\xff\x01", b"\x00"),
                ext(b"\x00\x0a", b"\x00\x08" + cls._grease() + bytes.fromhex("001d00170018")),
                ext(b"\x00\x0b", b"\x01\x00"),
                ext(b"\x00\x23", b""),
                ext(b"\x00\x10", bytes.fromhex("000c02683208687474702f312e31")),
                ext(b"\x00\x05", bytes.fromhex("0100000000")),
                ext(b"\x00\x0d", bytes.fromhex("001004030804040105030805050108060601")),
                ext(b"\x00\x12", b""),
                ext(b"\x00\x33", b"\x00\x2b" + cls._grease() + bytes.fromhex("000100001d0020") + os.urandom(32)),
                ext(b"\x00\x2d", b"\x01\x01"),
                ext(b"\x00\x2b", b"\x06" + cls._grease() + bytes.fromhex("03040303")),
                ext(b"\x00\x1b", bytes.fromhex("020002")),
            )
        )
        tail = ext(cls._grease(), b"\x00")
        session_id = os.urandom(32)

        unpadded = cls._assemble_client_hello(ciphers, extensions + tail, session_id)
        padding_size = cls.TLS_CLIENT_HELLO_SIZE - len(unpadded) - 4
        if padding_size >= 0:
            extensions += ext(b"\x00\x15", b"\0" * padding_size)
        return cls._assemble_client_hello(ciphers, extensions + tail, session_id)

    @classmethod
    def _assemble_client_hello(cls, ciphers: bytes, extensions: bytes, session_id: bytes) -> bytes:
        body = b"".join(
            (
                b"\x03\x03",
                b"\0" * cls.TLS_RANDOM_SIZE,
                bytes((len(session_id),)),
                session_id,
                struct.pack(">H", len(ciphers)),
                ciphers,
                b"\x01\x00",
                struct.pack(">H", len(extensions)),
                extensions,
            )
        )
        handshake = b"\x01" + len(body).to_bytes(3, "big") + body
        return b"\x16\x03\x01" + struct.pack(">H", len(handshake)) + handshake

    @staticmethod
    def _grease() -> bytes:
        value = (os.urandom(1)[0] & 0xF0) | 0x0A
        return bytes((value, value))

    @staticmethod
    def _tls_extension(ext_type: bytes, data: bytes) -> bytes:
        return ext_type + struct.pack(">H", len(data)) + data

    @classmethod
    def _wrap_in_tls_records(cls, payload: bytes) -> bytes:
        records = [cls.TLS_CHANGE_CIPHER_SPEC]
        for i in range(0, len(payload), cls.TLS_MAX_RECORD_PAYLOAD):
            chunk = payload[i: i + cls.TLS_MAX_RECORD_PAYLOAD]  # fmt: skip
            records.append(b"\x17\x03\x03" + struct.pack(">H", len(chunk)) + chunk)
        return b"".join(records)

    @classmethod
    def _build_req_pq_multi(cls, nonce: bytes) -> bytes:
        msg_id = int(time.time() * 2**32) & ~3
        body = struct.pack("<I", cls.REQ_PQ_MULTI) + nonce
        return b"\0" * 8 + struct.pack("<qi", msg_id, len(body)) + body

    @classmethod
    def _frame_intermediate(cls, payload: bytes, padded: bool) -> bytes:
        if padded:
            payload += os.urandom(os.urandom(1)[0] % cls.MAX_RANDOM_PADDING)
        return struct.pack("<I", len(payload)) + payload

    @classmethod
    def _is_res_pq_for(cls, answer: bytes, nonce: bytes) -> bool:
        return (
            len(answer) >= cls.RES_PQ_MIN_SIZE
            and answer[:8] == b"\0" * 8
            and struct.unpack("<I", answer[cls.RES_PQ_CONSTRUCTOR_SLICE])[0] == cls.RES_PQ
            and answer[cls.RES_PQ_NONCE_SLICE] == nonce
        )
