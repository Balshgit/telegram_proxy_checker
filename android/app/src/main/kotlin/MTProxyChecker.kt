package com.example.tgproxycheck

/*
 * Порт backend/app/infra/gateways/mtproto_checker.py (MTProxyChecker.check) один в один.
 *
 * Проверка MTProto-прокси тем же способом, каким к ней подключается Telegram:
 * 1. для `ee`-секретов — Fake-TLS ClientHello, подписанный HMAC по секрету, и сверка HMAC в ответе сервера;
 * 2. obfuscated2-инициализация с ключами, выведенными из секрета;
 * 3. отправка незашифрованного `req_pq_multi` в DC Telegram через прокси;
 * 4. ожидание `resPQ` с нашим nonce.
 *
 * Пришёл `resPQ` — значит, прокси знает секрет и реально пересылает трафик до серверов Telegram.
 */

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.async
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeoutOrNull
import java.io.EOFException
import java.io.IOException
import java.io.InputStream
import java.io.OutputStream
import java.net.InetAddress
import java.net.InetSocketAddress
import java.net.Socket
import java.net.SocketException
import java.net.SocketTimeoutException
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.security.MessageDigest
import java.security.SecureRandom
import java.util.concurrent.atomic.AtomicBoolean
import javax.crypto.Cipher
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec

enum class ProxyCheckError(val value: String) {
    BAD_SECRET("bad_secret"),
    CONNECT_FAILED("connect_failed"),
    TLS_REJECTED("tls_rejected"), // в ответ на ClientHello пришёл не ServerHello: не тот секрет или не MTProxy
    TLS_BAD_HMAC("tls_bad_hmac"), // ServerHello пришёл, но подписан не нашим секретом
    NO_ANSWER("no_answer"), // прокси закрыла соединение, не дождавшись ответа Telegram
    BAD_ANSWER("bad_answer"), // пришло что-то, но не resPQ на наш запрос
    TIMEOUT("timeout"), // прокси молчит: обычно так MTProxy реагирует на неверный секрет
}

enum class SecretMode { PLAIN, PADDED, FAKE_TLS }

data class ProxyCheckResult(
    val isConnected: Boolean,
    val latencyMs: Int? = null,
    val error: ProxyCheckError? = null,
)

private val random = SecureRandom()

private fun urandom(size: Int): ByteArray = ByteArray(size).also { random.nextBytes(it) }

private fun u8(b: Byte): Int = b.toInt() and 0xFF

private fun le32(value: Int): ByteArray =
    ByteBuffer.allocate(4).order(ByteOrder.LITTLE_ENDIAN).putInt(value).array()

private fun be16(value: Int): ByteArray = byteArrayOf((value ushr 8).toByte(), value.toByte())

private fun hex(s: String): ByteArray = ByteArray(s.length / 2) { s.substring(it * 2, it * 2 + 2).toInt(16).toByte() }

private fun hmacSha256(key: ByteArray, data: ByteArray): ByteArray =
    Mac.getInstance("HmacSHA256").run {
        init(SecretKeySpec(key, "HmacSHA256"))
        doFinal(data)
    }

private fun sha256(data: ByteArray): ByteArray = MessageDigest.getInstance("SHA-256").digest(data)

/** Конец потока посреди ожидаемых данных (аналог asyncio.IncompleteReadError). */
private class IncompleteReadException : EOFException()

class MTProxySecret private constructor(val key: ByteArray, val mode: SecretMode, val domain: String = "") {
    companion object {
        const val KEY_SIZE = 16
        const val PREFIX_PADDED = 0xDD
        const val PREFIX_FAKE_TLS = 0xEE

        /** Секрет в ссылках бывает и в hex, и в base64url (часто для `ee`). */
        fun parse(rawInput: String): MTProxySecret {
            val raw = rawInput.trim()
            val data = PyCompat.fromHex(raw)
                ?: PyCompat.urlsafeB64Decode(raw + "=".repeat(Math.floorMod(-raw.length, 4)))
                ?: throw IllegalArgumentException("secret is neither hex nor base64")

            if (data.size == KEY_SIZE) return MTProxySecret(data, SecretMode.PLAIN)
            if (data.size == KEY_SIZE + 1 && u8(data[0]) == PREFIX_PADDED) {
                return MTProxySecret(data.copyOfRange(1, data.size), SecretMode.PADDED)
            }
            if (data.size > KEY_SIZE + 1 && u8(data[0]) == PREFIX_FAKE_TLS) {
                // decode("ascii", "ignore"): байты вне ASCII выбрасываются
                val domain = data.copyOfRange(KEY_SIZE + 1, data.size)
                    .filter { it >= 0 }.map { it.toInt().toChar() }.joinToString("")
                return MTProxySecret(data.copyOfRange(1, KEY_SIZE + 1), SecretMode.FAKE_TLS, domain)
            }
            throw IllegalArgumentException("unsupported secret format (${data.size} bytes)")
        }
    }
}

/** Повторяет поведение Python `bytes.fromhex` и `base64.urlsafe_b64decode` (не строгий режим). */
internal object PyCompat {
    private fun isPyAsciiSpace(c: Char) = c == ' ' || c == '\t' || c == '\n' || c == '\r' || c == '\u000B' || c == '\u000C'

    fun fromHex(s: String): ByteArray? {
        val out = java.io.ByteArrayOutputStream()
        var i = 0
        while (i < s.length) {
            if (isPyAsciiSpace(s[i])) { i++; continue }
            if (i + 1 >= s.length) return null
            val hi = Character.digit(s[i], 16)
            val lo = Character.digit(s[i + 1], 16)
            if (hi < 0 || lo < 0 || s[i].code > 127 || s[i + 1].code > 127) return null
            out.write(hi * 16 + lo)
            i += 2
        }
        return out.toByteArray()
    }

    private val B64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"

    /** binascii.a2b_base64(strict_mode=False) после замены `-_` на `+/`. null — ошибка декодирования. */
    fun urlsafeB64Decode(s: String): ByteArray? {
        if (s.any { it.code > 127 }) return null
        val src = s.replace('-', '+').replace('_', '/')
        val out = java.io.ByteArrayOutputStream()
        var quadPos = 0
        var leftChar = 0
        var pads = 0
        for (ch in src) {
            if (ch == '=') {
                if (quadPos >= 2 && quadPos + ++pads >= 4) return out.toByteArray()
                continue
            }
            val v = B64.indexOf(ch)
            if (v < 0) continue
            pads = 0
            when (quadPos) {
                0 -> { quadPos = 1; leftChar = v }
                1 -> { quadPos = 2; out.write((leftChar shl 2) or (v shr 4)); leftChar = v and 0x0F }
                2 -> { quadPos = 3; out.write((leftChar shl 4) or (v shr 2)); leftChar = v and 0x03 }
                else -> { quadPos = 0; out.write((leftChar shl 6) or v); leftChar = 0 }
            }
        }
        return if (quadPos != 0) null else out.toByteArray()
    }
}

/** AES-256-CTR с полным 128-битным big-endian счётчиком, как `modes.CTR` из cryptography. */
private class AesCtr(key: ByteArray, iv: ByteArray) {
    private val aes = Cipher.getInstance("AES/ECB/NoPadding").apply { init(Cipher.ENCRYPT_MODE, SecretKeySpec(key, "AES")) }
    private val counter = iv.copyOf()
    private val keystream = ByteArray(16)
    private var pos = 16

    fun update(data: ByteArray): ByteArray {
        val out = ByteArray(data.size)
        for (i in data.indices) {
            if (pos == 16) {
                aes.doFinal(counter, 0, 16, keystream, 0)
                for (j in 15 downTo 0) {
                    counter[j] = (counter[j] + 1).toByte()
                    if (counter[j] != 0.toByte()) break
                }
                pos = 0
            }
            out[i] = (data[i].toInt() xor keystream[pos++].toInt()).toByte()
        }
        return out
    }
}

/** Клиентская сторона obfuscated2: 64 случайных байта задают ключи AES-256-CTR в обе стороны. */
private class Obfuscated2Cipher(secretKey: ByteArray, protocolTag: ByteArray, dcId: Int) {
    companion object {
        const val INIT_SIZE = 64
        const val ABRIDGED_FIRST_BYTE = 0xEF
        val TAG_INTERMEDIATE = byteArrayOf(0xEE.toByte(), 0xEE.toByte(), 0xEE.toByte(), 0xEE.toByte())
        val TAG_PADDED_INTERMEDIATE = byteArrayOf(0xDD.toByte(), 0xDD.toByte(), 0xDD.toByte(), 0xDD.toByte())
        private val FORBIDDEN_INIT_PREFIXES = listOf(
            "HEAD".toByteArray(), "POST".toByteArray(), "GET ".toByteArray(), "OPTI".toByteArray(),
            byteArrayOf(0x16, 0x03, 0x01, 0x02), TAG_INTERMEDIATE, TAG_PADDED_INTERMEDIATE,
        )

        private fun randomInit(): ByteArray {
            while (true) {
                val init = urandom(INIT_SIZE)
                val prefix = init.copyOfRange(0, 4)
                if (u8(init[0]) != ABRIDGED_FIRST_BYTE &&
                    FORBIDDEN_INIT_PREFIXES.none { it.contentEquals(prefix) } &&
                    !init.copyOfRange(4, 8).contentEquals(ByteArray(4))
                ) return init
            }
        }
    }

    private val encryptor: AesCtr
    private val decryptor: AesCtr
    val header: ByteArray

    init {
        val init = randomInit()
        protocolTag.copyInto(init, 56)
        init[60] = dcId.toByte() // struct.pack("<h", dc_id)
        init[61] = (dcId shr 8).toByte()

        val reversedPart = init.copyOfRange(8, 56).reversedArray()
        val encKey = sha256(init.copyOfRange(8, 40) + secretKey)
        val decKey = sha256(reversedPart.copyOfRange(0, 32) + secretKey)
        encryptor = AesCtr(encKey, init.copyOfRange(40, 56))
        decryptor = AesCtr(decKey, reversedPart.copyOfRange(32, 48))

        val encrypted = encryptor.update(init)
        header = init.copyOfRange(0, 56) + encrypted.copyOfRange(56, 64)
    }

    fun encrypt(data: ByteArray): ByteArray = encryptor.update(data)
    fun decrypt(data: ByteArray): ByteArray = decryptor.update(data)
}

/** Читает из сокета ответ прокси, снимая TLS-обёртку (для `ee`) и obfuscated2-шифрование. */
private class ObfuscatedStreamReader(
    private val input: InputStream,
    private val cipher: Obfuscated2Cipher,
    private val overTls: Boolean,
) {
    private var buffer = ByteArray(0)

    fun readExactly(size: Int): ByteArray {
        while (buffer.size < size) buffer += cipher.decrypt(readChunk())
        val data = buffer.copyOfRange(0, size)
        buffer = buffer.copyOfRange(size, buffer.size)
        return data
    }

    private fun readChunk(): ByteArray {
        if (!overTls) {
            val chunk = ByteArray(4096)
            val n = input.read(chunk)
            if (n <= 0) throw IncompleteReadException()
            return chunk.copyOf(n)
        }
        while (true) {
            val (recordType, record) = MTProxyChecker.readTlsRecord(input)
            if (recordType == MTProxyChecker.TLS_RECORD_APPLICATION_DATA) {
                return record.copyOfRange(MTProxyChecker.TLS_RECORD_HEADER_SIZE, record.size)
            }
        }
    }
}

/**
 * Проверяет MTProto-прокси полным handshake до DC Telegram.
 *
 * @param timeout общий таймаут на одну проверку (коннект + handshake + ответ Telegram), секунды.
 * @param dcId DC Telegram, к которому прокси должна переслать запрос.
 */
class MTProxyChecker(val timeout: Double = PROXY_PING_TIMEOUT, val dcId: Int = 2) {
    companion object {
        const val PROXY_PING_TIMEOUT = 10.0

        /**
         * Отдельный scope для DNS: InetAddress.getByName нельзя прервать ни отменой корутины, ни закрытием сокета.
         * Резолв идёт «в фоне», а проверка ждёт его не дольше оставшегося таймаута и уходит, не дожидаясь.
         */
        private val dnsScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

        const val REQ_PQ_MULTI = 0xBE7E8EF1.toInt()
        const val RES_PQ = 0x05162463
        const val MAX_RANDOM_PADDING = 16

        const val TLS_RECORD_HANDSHAKE = 0x16
        const val TLS_RECORD_CHANGE_CIPHER_SPEC = 0x14
        const val TLS_RECORD_APPLICATION_DATA = 0x17
        const val TLS_RECORD_HEADER_SIZE = 5
        const val TLS_RANDOM_OFFSET = 11
        const val TLS_RANDOM_SIZE = 32
        const val TLS_CLIENT_HELLO_SIZE = 517
        const val TLS_MAX_RECORD_PAYLOAD = 16384
        val TLS_CHANGE_CIPHER_SPEC = byteArrayOf(0x14, 0x03, 0x03, 0x00, 0x01, 0x01)

        const val FRAME_LENGTH_SIZE = 4
        const val MIN_FRAME_SIZE = 4
        const val MAX_FRAME_SIZE = 1 shl 16
        // Раскладка ответа resPQ: 8 байт auth_key_id, 8 msg_id, 4 длина, 4 конструктор, 16 nonce.
        const val RES_PQ_MIN_SIZE = 40

        private fun readExactly(input: InputStream, size: Int): ByteArray {
            val out = ByteArray(size)
            var off = 0
            while (off < size) {
                val n = input.read(out, off, size - off)
                if (n < 0) throw IncompleteReadException()
                off += n
            }
            return out
        }

        /** Возвращает тип записи и запись целиком (заголовок + тело). */
        fun readTlsRecord(input: InputStream): Pair<Int, ByteArray> {
            val header = readExactly(input, TLS_RECORD_HEADER_SIZE)
            val body = readExactly(input, (u8(header[3]) shl 8) or u8(header[4]))
            return u8(header[0]) to (header + body)
        }

        internal fun grease(): ByteArray {
            val value = ((u8(urandom(1)[0]) and 0xF0) or 0x0A).toByte()
            return byteArrayOf(value, value)
        }

        private fun tlsExtension(extType: ByteArray, data: ByteArray): ByteArray = extType + be16(data.size) + data

        /** ClientHello в стиле Chrome/tdlib размером 517 байт; поле random нулевое и подписывается позже. */
        internal fun buildClientHello(domain: String): ByteArray {
            val sni = domain.toByteArray(Charsets.UTF_8)
            val ext = ::tlsExtension
            val ciphers = grease() + hex("130113021303c02bc02fc02cc030cca9cca8c013c014009c009d002f0035")
            var extensions = listOf(
                ext(grease(), ByteArray(0)),
                ext(hex("0000"), be16(sni.size + 3) + byteArrayOf(0) + be16(sni.size) + sni),
                ext(hex("0017"), ByteArray(0)),
                ext(hex("ff01"), hex("00")),
                ext(hex("000a"), hex("0008") + grease() + hex("001d00170018")),
                ext(hex("000b"), hex("0100")),
                ext(hex("0023"), ByteArray(0)),
                ext(hex("0010"), hex("000c02683208687474702f312e31")),
                ext(hex("0005"), hex("0100000000")),
                ext(hex("000d"), hex("001004030804040105030805050108060601")),
                ext(hex("0012"), ByteArray(0)),
                ext(hex("0033"), hex("002b") + grease() + hex("000100001d0020") + urandom(32)),
                ext(hex("002d"), hex("0101")),
                ext(hex("002b"), hex("06") + grease() + hex("03040303")),
                ext(hex("001b"), hex("020002")),
            ).reduce(ByteArray::plus)
            val tail = ext(grease(), hex("00"))
            val sessionId = urandom(32)

            val unpadded = assembleClientHello(ciphers, extensions + tail, sessionId)
            val paddingSize = TLS_CLIENT_HELLO_SIZE - unpadded.size - 4
            if (paddingSize >= 0) extensions += ext(hex("0015"), ByteArray(paddingSize))
            return assembleClientHello(ciphers, extensions + tail, sessionId)
        }

        private fun assembleClientHello(ciphers: ByteArray, extensions: ByteArray, sessionId: ByteArray): ByteArray {
            val body = hex("0303") + ByteArray(TLS_RANDOM_SIZE) + byteArrayOf(sessionId.size.toByte()) + sessionId +
                be16(ciphers.size) + ciphers + hex("0100") + be16(extensions.size) + extensions
            val handshake = byteArrayOf(0x01, (body.size ushr 16).toByte(), (body.size ushr 8).toByte(), body.size.toByte()) + body
            return hex("160301") + be16(handshake.size) + handshake
        }

        internal fun wrapInTlsRecords(payload: ByteArray): ByteArray {
            var out = TLS_CHANGE_CIPHER_SPEC
            var i = 0
            while (i < payload.size) {
                val chunk = payload.copyOfRange(i, minOf(i + TLS_MAX_RECORD_PAYLOAD, payload.size))
                out += hex("170303") + be16(chunk.size) + chunk
                i += TLS_MAX_RECORD_PAYLOAD
            }
            return out
        }

        internal fun buildReqPqMulti(nonce: ByteArray): ByteArray {
            // int(time.time() * 2**32) & ~3
            val msgId = (System.currentTimeMillis() / 1000.0 * 4294967296.0).toLong() and 3L.inv()
            val body = le32(REQ_PQ_MULTI) + nonce
            return ByteArray(8) +
                ByteBuffer.allocate(12).order(ByteOrder.LITTLE_ENDIAN).putLong(msgId).putInt(body.size).array() +
                body
        }

        internal fun frameIntermediate(payloadIn: ByteArray, padded: Boolean): ByteArray {
            var payload = payloadIn
            if (padded) payload += urandom(u8(urandom(1)[0]) % MAX_RANDOM_PADDING)
            return le32(payload.size) + payload
        }

        internal fun isResPqFor(answer: ByteArray, nonce: ByteArray): Boolean =
            answer.size >= RES_PQ_MIN_SIZE &&
                answer.copyOfRange(0, 8).contentEquals(ByteArray(8)) &&
                ByteBuffer.wrap(answer, 20, 4).order(ByteOrder.LITTLE_ENDIAN).int == RES_PQ &&
                answer.copyOfRange(24, 40).contentEquals(nonce)
    }

    /** Latency в результате — время от начала проверки (включая DNS) до ответа `resPQ` от Telegram. */
    suspend fun check(host: String, port: Int, secret: String): ProxyCheckResult {
        val parsedSecret = try {
            MTProxySecret.parse(secret)
        } catch (e: IllegalArgumentException) {
            return ProxyCheckResult(isConnected = false, error = ProxyCheckError.BAD_SECRET)
        }
        val timeoutResult = ProxyCheckResult(isConnected = false, error = ProxyCheckError.TIMEOUT)
        val connectFailed = ProxyCheckResult(isConnected = false, error = ProxyCheckError.CONNECT_FAILED)
        val startedAt = System.nanoTime()
        val deadline = startedAt + (timeout * 1_000_000_000).toLong()

        if (port !in 0..65535) return connectFailed // в Python это OSError/OverflowError при коннекте
        val ip = when (val resolved = resolve(host, deadline)) {
            is DnsResult.Ok -> resolved.address
            DnsResult.Failed -> return connectFailed
            DnsResult.TimedOut -> return timeoutResult
        }
        val address = InetSocketAddress(ip, port)

        return withContext(Dispatchers.IO) {
            val socket = Socket()
            val timedOut = AtomicBoolean(false)
            // Аналог asyncio.timeout: по истечении общего таймаута рвём сокет, блокирующие вызовы падают.
            // Сторож живёт на Dispatchers.Default: потоки IO могут быть все заняты блокирующими сокетами,
            // и тогда сторож на IO не смог бы проснуться вовремя.
            val watchdog = launch(Dispatchers.Default) {
                try {
                    delay(remainingMs(deadline))
                    timedOut.set(true)
                } finally {
                    runCatching { socket.close() }
                }
            }
            try {
                doCheck(socket, address, parsedSecret, timedOut, startedAt, deadline)
            } catch (e: IOException) {
                if (timedOut.get() || e is SocketTimeoutException) timeoutResult else connectFailed
            } finally {
                watchdog.cancel()
                runCatching { socket.close() }
            }
        }
    }

    private sealed interface DnsResult {
        class Ok(val address: InetAddress) : DnsResult
        data object Failed : DnsResult
        data object TimedOut : DnsResult
    }

    private suspend fun resolve(host: String, deadline: Long): DnsResult {
        val lookup = dnsScope.async { InetAddress.getByName(host) }
        return try {
            withTimeoutOrNull(remainingMs(deadline)) { lookup.await() }
                ?.let { DnsResult.Ok(it) }
                ?: DnsResult.TimedOut.also { lookup.cancel() }
        } catch (e: IOException) { // UnknownHostException и т.п.
            DnsResult.Failed
        } catch (e: SecurityException) {
            DnsResult.Failed
        }
    }

    private fun remainingMs(deadline: Long): Long = ((deadline - System.nanoTime()) / 1_000_000).coerceAtLeast(1)

    private fun doCheck(
        socket: Socket,
        address: InetSocketAddress,
        secret: MTProxySecret,
        timedOut: AtomicBoolean,
        startedAt: Long,
        deadline: Long,
    ): ProxyCheckResult {
        val timeoutResult = ProxyCheckResult(isConnected = false, error = ProxyCheckError.TIMEOUT)
        try {
            if (timedOut.get()) return timeoutResult
            socket.tcpNoDelay = true
            // Таймауты на самом сокете: даже если сторож запоздает, connect/read не повиснут дольше дедлайна.
            socket.connect(address, remainingMs(deadline).coerceAtMost(Int.MAX_VALUE.toLong()).toInt())
            socket.soTimeout = remainingMs(deadline).coerceAtMost(Int.MAX_VALUE.toLong()).toInt()
        } catch (e: IOException) {
            if (timedOut.get() || e is SocketTimeoutException) return timeoutResult
            return ProxyCheckResult(isConnected = false, error = ProxyCheckError.CONNECT_FAILED)
        }

        val input = socket.getInputStream()
        val output = socket.getOutputStream()

        val overTls = secret.mode == SecretMode.FAKE_TLS
        if (overTls) {
            val error = fakeTlsHandshake(input, output, secret)
            if (error != null) return if (timedOut.get()) timeoutResult else ProxyCheckResult(isConnected = false, error = error)
        }

        val padded = secret.mode == SecretMode.PADDED || secret.mode == SecretMode.FAKE_TLS
        val tag = if (padded) Obfuscated2Cipher.TAG_PADDED_INTERMEDIATE else Obfuscated2Cipher.TAG_INTERMEDIATE
        val cipher = Obfuscated2Cipher(secret.key, tag, dcId)
        val nonce = urandom(16)
        val payload = cipher.header + cipher.encrypt(frameIntermediate(buildReqPqMulti(nonce), padded))
        output.write(if (overTls) wrapInTlsRecords(payload) else payload)
        output.flush()

        val stream = ObfuscatedStreamReader(input, cipher, overTls)
        val answer: ByteArray
        try {
            val length = ByteBuffer.wrap(stream.readExactly(FRAME_LENGTH_SIZE)).order(ByteOrder.LITTLE_ENDIAN).int and 0x7FFFFFFF
            if (length !in MIN_FRAME_SIZE..MAX_FRAME_SIZE) {
                return ProxyCheckResult(isConnected = false, error = ProxyCheckError.BAD_ANSWER)
            }
            answer = stream.readExactly(length)
        } catch (e: IncompleteReadException) {
            return if (timedOut.get()) timeoutResult else ProxyCheckResult(isConnected = false, error = ProxyCheckError.NO_ANSWER)
        } catch (e: SocketException) { // ConnectionError: reset / broken pipe / aborted
            return if (timedOut.get()) timeoutResult else ProxyCheckResult(isConnected = false, error = ProxyCheckError.NO_ANSWER)
        }

        if (!isResPqFor(answer, nonce)) return ProxyCheckResult(isConnected = false, error = ProxyCheckError.BAD_ANSWER)
        return ProxyCheckResult(isConnected = true, latencyMs = ((System.nanoTime() - startedAt) / 1_000_000).toInt())
    }

    private fun fakeTlsHandshake(input: InputStream, output: OutputStream, secret: MTProxySecret): ProxyCheckError? {
        val randomEnd = TLS_RANDOM_OFFSET + TLS_RANDOM_SIZE

        val hello = buildClientHello(secret.domain)
        val clientDigest = hmacSha256(secret.key, hello)
        val timestamp = le32((System.currentTimeMillis() / 1000).toInt())
        for (i in 0 until 4) {
            clientDigest[TLS_RANDOM_SIZE - 4 + i] = (clientDigest[TLS_RANDOM_SIZE - 4 + i].toInt() xor timestamp[i].toInt()).toByte()
        }
        clientDigest.copyInto(hello, TLS_RANDOM_OFFSET)
        output.write(hello)
        output.flush()

        // Сервер отвечает ServerHello, ChangeCipherSpec и одной записью Application Data.
        var response: ByteArray
        try {
            var (recordType, first) = readTlsRecord(input)
            response = first
            if (recordType != TLS_RECORD_HANDSHAKE || response.size < randomEnd) return ProxyCheckError.TLS_REJECTED
            while (recordType != TLS_RECORD_APPLICATION_DATA) {
                val (nextType, record) = readTlsRecord(input)
                recordType = nextType
                if (recordType != TLS_RECORD_CHANGE_CIPHER_SPEC && recordType != TLS_RECORD_APPLICATION_DATA) {
                    return ProxyCheckError.TLS_REJECTED
                }
                response += record
            }
        } catch (e: IncompleteReadException) {
            return ProxyCheckError.TLS_REJECTED
        }

        val serverRandom = response.copyOfRange(TLS_RANDOM_OFFSET, randomEnd)
        val signed = response.copyOf()
        ByteArray(TLS_RANDOM_SIZE).copyInto(signed, TLS_RANDOM_OFFSET)
        val expected = hmacSha256(secret.key, clientDigest + signed)
        if (!MessageDigest.isEqual(serverRandom, expected)) return ProxyCheckError.TLS_BAD_HMAC
        return null
    }
}
