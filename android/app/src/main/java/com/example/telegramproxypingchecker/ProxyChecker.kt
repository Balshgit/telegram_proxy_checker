package com.example.telegramproxypingchecker

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.sync.Semaphore
import kotlinx.coroutines.sync.withPermit
import kotlinx.coroutines.withContext
import android.util.Base64
import org.json.JSONArray
import org.json.JSONObject
import org.json.JSONTokener
import java.io.DataInputStream
import java.io.EOFException
import java.io.IOException
import java.net.HttpURLConnection
import java.net.InetSocketAddress
import java.net.Socket
import java.net.SocketTimeoutException
import java.net.URL
import java.net.URLDecoder
import java.security.MessageDigest
import java.security.SecureRandom
import javax.crypto.Cipher
import javax.crypto.spec.IvParameterSpec
import javax.crypto.spec.SecretKeySpec

data class Proxy(val url: String, val server: String, val port: Int, val secret: String)

data class ProxyResult(val proxy: Proxy, val pingMs: Double)

/** Почему прокси не прошла проверку. */
enum class CheckError(val label: String) {
    UNSUPPORTED_SECRET("секрет ee — не проверяется"),
    BAD_SECRET("неверный формат секрета"),
    CONNECT_FAILED("не удалось подключиться"),
    TIMEOUT("прокси молчит (таймаут)"),
    NO_ANSWER("прокси закрыла соединение"),
    BAD_ANSWER("пришёл не тот ответ"),
}

/** Итог проверки одной прокси: либо result, либо error. */
data class CheckOutcome(val result: ProxyResult?, val error: CheckError?)

object ProxyChecker {

    private const val BASE_URL = "https://bot.mywistr.ru"
    private const val PAGE_SIZE = 100
    private const val MAX_PAGES = 500

    private fun pageUrl(offset: Int): String =
        if (offset == 0) "$BASE_URL/api/proxies?limit=$PAGE_SIZE"
        else "$BASE_URL/api/proxies?limit=$PAGE_SIZE&offset=$offset"

    /**
     * Сколько прокси проверяется одновременно. 64 — это размер пула Dispatchers.IO:
     * больше блокирующих сокетов он всё равно не обслужит одновременно, а на мобильных
     * сетях/роутерах сотни одновременных соединений начинают теряться и искажают пинг.
     * При ~2100 прокси и худшем случае 10 с на прокси это до ~5 минут, обычно быстрее.
     */
    private const val PARALLELISM = 64
    private const val TIMEOUT_MS = 5_000
    private const val DC_ID: Short = 2
    private const val RES_PQ = 0x05162463
    private const val REQ_PQ_MULTI = 0xbe7e8ef1.toInt()

    private val random = SecureRandom()

    /**
     * 1–2. Загружает все страницы всех прокси:
     * ?limit=100, затем &offset=100, &offset=200 … пока next_page не станет null
     * (или страница не окажется пустой).
     */
    suspend fun fetchProxies(onProgress: (Int) -> Unit = {}): List<Proxy> = withContext(Dispatchers.IO) {
        val all = LinkedHashMap<String, Proxy>()
        var offset = 0
        for (pageIndex in 0 until MAX_PAGES) {
            val page = parsePage(httpGet(pageUrl(offset)))
            page.proxies.forEach { all.putIfAbsent(it.url, it) }
            withContext(Dispatchers.Main) { onProgress(all.size) }
            if (page.nextPage == null || page.itemCount == 0) break
            offset += PAGE_SIZE
        }
        all.values.toList()
    }

    private fun httpGet(url: String): String {
        val conn = (URL(url).openConnection() as HttpURLConnection).apply {
            connectTimeout = 10_000
            readTimeout = 15_000
            setRequestProperty("Accept", "application/json")
        }
        try {
            val code = conn.responseCode
            if (code !in 200..299) throw IOException("Сервер ответил HTTP $code")
            return conn.inputStream.bufferedReader().use { it.readText() }
        } finally {
            conn.disconnect()
        }
    }

    private class Page(val proxies: List<Proxy>, val itemCount: Int, val nextPage: String?)

    private fun parsePage(body: String): Page {
        val root = JSONTokener(body).nextValue()
        val next = (root as? JSONObject)
            ?.optJSONObject("payload")
            ?.optJSONObject("pagination")
            ?.str("next_page")
        return Page(parse(body), itemsOf(root).length(), next)
    }

    private fun itemsOf(root: Any?): JSONArray = when (root) {
        is JSONArray -> root
        is JSONObject -> root.optJSONObject("payload")?.optJSONArray("data")
            ?: root.optJSONArray("payload")
            ?: root.optJSONArray("data")
            ?: JSONArray()
        else -> JSONArray()
    }

    fun parse(body: String): List<Proxy> {
        val items = itemsOf(JSONTokener(body).nextValue())

        val result = mutableListOf<Proxy>()
        for (i in 0 until items.length()) {
            val obj = items.optJSONObject(i) ?: continue
            val url = obj.str("url") ?: continue
            val query = queryParams(url)
            val server = obj.str("server") ?: query["server"] ?: continue
            val port = obj.str("port")?.toIntOrNull() ?: query["port"]?.toIntOrNull() ?: continue
            if (port !in 1..65535) continue
            val secret = obj.str("secret") ?: query["secret"] ?: continue
            result += Proxy(url = url, server = server, port = port, secret = secret)
        }
        return result.distinctBy { it.url }
    }

    /**
     * 3. Проверка как в Telegram: подключаемся к прокси, делаем MTProto-рукопожатие
     * (obfuscated2) с секретом, отправляем req_pq_multi на DC 2 и ждём resPQ.
     * Возвращает время запрос→ответ в мс или null, если прокси не работает.
     * Поддерживаются секреты dd… и обычные 32 hex; ee… (FakeTLS) пока нет.
     */
    suspend fun check(proxy: Proxy): CheckOutcome = withContext(Dispatchers.IO) {
        try {
            probe(proxy)
        } catch (e: Exception) {
            fail(CheckError.NO_ANSWER)
        }
    }

    private fun fail(error: CheckError) = CheckOutcome(null, error)

    private fun probe(proxy: Proxy): CheckOutcome {
        val raw = decodeSecret(proxy.secret) ?: return fail(CheckError.BAD_SECRET)
        val padded: Boolean
        val secret: ByteArray
        when {
            raw.size == 17 && raw[0] == 0xdd.toByte() -> { padded = true; secret = raw.copyOfRange(1, 17) }
            raw.size == 16 -> { padded = false; secret = raw }
            raw.size > 17 && raw[0] == 0xee.toByte() -> return fail(CheckError.UNSUPPORTED_SECRET)
            else -> return fail(CheckError.BAD_SECRET)
        }
        val tag = if (padded) 0xdddddddd.toInt() else 0xeeeeeeee.toInt()

        Socket().use { socket ->
            try {
                socket.connect(InetSocketAddress(proxy.server, proxy.port), TIMEOUT_MS)
            } catch (e: Exception) {
                return fail(CheckError.CONNECT_FAILED)
            }
            socket.soTimeout = TIMEOUT_MS
            socket.tcpNoDelay = true
            val output = socket.getOutputStream()
            val input = DataInputStream(socket.getInputStream())

            // --- obfuscated2 заголовок ---
            val init = randomInit()
            putIntLE(init, 56, tag)
            init[60] = (DC_ID.toInt() and 0xff).toByte()
            init[61] = ((DC_ID.toInt() shr 8) and 0xff).toByte()

            val reversed = init.copyOfRange(8, 56).reversedArray()
            val encrypt = aesCtr(sha256(init.copyOfRange(8, 40), secret), init.copyOfRange(40, 56))
            val decrypt = aesCtr(sha256(reversed.copyOfRange(0, 32), secret), reversed.copyOfRange(32, 48))

            val encryptedInit = encrypt.update(init)
            val header = init.copyOf()
            System.arraycopy(encryptedInit, 56, header, 56, 8)

            // --- req_pq_multi (незашифрованное MTProto-сообщение) ---
            val nonce = ByteArray(16).also { random.nextBytes(it) }
            val message = ByteArray(40)
            putLongLE(message, 8, messageId())
            putIntLE(message, 16, 20)
            putIntLE(message, 20, REQ_PQ_MULTI)
            System.arraycopy(nonce, 0, message, 24, 16)

            val padding = if (padded) ByteArray(random.nextInt(16)).also { random.nextBytes(it) } else ByteArray(0)
            val packet = ByteArray(4 + message.size + padding.size)
            putIntLE(packet, 0, message.size + padding.size)
            System.arraycopy(message, 0, packet, 4, message.size)
            System.arraycopy(padding, 0, packet, 4 + message.size, padding.size)

            val start = System.nanoTime()
            val (response, elapsedMs) = try {
                output.write(header + encrypt.update(packet))
                output.flush()

                // --- ответ resPQ ---
                val lengthBytes = ByteArray(4).also { input.readFully(it) }
                val length = getIntLE(decrypt.update(lengthBytes), 0) and 0x7fffffff
                if (length < 40 || length > 65_536) return fail(CheckError.BAD_ANSWER)
                val body = ByteArray(length).also { input.readFully(it) }
                val elapsed = (System.nanoTime() - start) / 1_000_000.0
                Pair(decrypt.update(body), elapsed)
            } catch (e: SocketTimeoutException) {
                return fail(CheckError.TIMEOUT)
            } catch (e: EOFException) {
                return fail(CheckError.NO_ANSWER)
            } catch (e: IOException) {
                return fail(CheckError.NO_ANSWER)
            }

            if (getIntLE(response, 20) != RES_PQ) return fail(CheckError.BAD_ANSWER)
            if (!response.copyOfRange(24, 40).contentEquals(nonce)) return fail(CheckError.BAD_ANSWER)
            return CheckOutcome(ProxyResult(proxy, elapsedMs), null)
        }
    }

    private fun randomInit(): ByteArray {
        val forbidden = intArrayOf(
            0x44414548, // "HEAD"
            0x54534f50, // "POST"
            0x20544547, // "GET "
            0x4954504f, // "OPTI"
            0x02010316, // TLS
            0xdddddddd.toInt(),
            0xeeeeeeee.toInt(),
        )
        while (true) {
            val b = ByteArray(64).also { random.nextBytes(it) }
            if (b[0] == 0xef.toByte()) continue
            if (getIntLE(b, 0) in forbidden) continue
            if (getIntLE(b, 4) == 0) continue
            return b
        }
    }

    private fun decodeSecret(secret: String): ByteArray? {
        val s = secret.trim()
        if (s.length % 2 == 0 && s.all { it in '0'..'9' || it in 'a'..'f' || it in 'A'..'F' }) {
            return ByteArray(s.length / 2) { i -> s.substring(i * 2, i * 2 + 2).toInt(16).toByte() }
        }
        return try {
            Base64.decode(s, Base64.URL_SAFE or Base64.NO_PADDING or Base64.NO_WRAP)
        } catch (e: IllegalArgumentException) {
            null
        }
    }

    private fun messageId(): Long {
        val ms = System.currentTimeMillis()
        return ((ms / 1000) shl 32) or (((ms % 1000) shl 22) and 0xfffffffcL)
    }

    private fun sha256(key: ByteArray, secret: ByteArray): ByteArray =
        MessageDigest.getInstance("SHA-256").digest(key + secret)

    private fun aesCtr(key: ByteArray, iv: ByteArray): Cipher =
        Cipher.getInstance("AES/CTR/NoPadding").apply {
            init(Cipher.ENCRYPT_MODE, SecretKeySpec(key, "AES"), IvParameterSpec(iv))
        }

    private fun getIntLE(b: ByteArray, off: Int): Int =
        (b[off].toInt() and 0xff) or
            ((b[off + 1].toInt() and 0xff) shl 8) or
            ((b[off + 2].toInt() and 0xff) shl 16) or
            ((b[off + 3].toInt() and 0xff) shl 24)

    private fun putIntLE(b: ByteArray, off: Int, v: Int) {
        for (i in 0 until 4) b[off + i] = (v shr (8 * i)).toByte()
    }

    private fun putLongLE(b: ByteArray, off: Int, v: Long) {
        for (i in 0 until 8) b[off + i] = (v shr (8 * i)).toByte()
    }

    /** 4. Проверяет все прокси параллельно, onChecked вызывается после каждого. */
    suspend fun checkAll(
        proxies: List<Proxy>,
        onChecked: (CheckOutcome) -> Unit,
    ): List<ProxyResult> = coroutineScope {
        val semaphore = Semaphore(PARALLELISM)
        proxies.map { proxy ->
            async {
                semaphore.withPermit {
                    val outcome = check(proxy)
                    onChecked(outcome)
                    outcome.result
                }
            }
        }.awaitAll().filterNotNull().sortedBy { it.pingMs }
    }

    private fun JSONObject.str(key: String): String? =
        if (!has(key) || isNull(key)) null else optString(key).trim().ifEmpty { null }

    private fun queryParams(url: String): Map<String, String> =
        url.substringAfter('?', "")
            .split('&')
            .mapNotNull { part ->
                val key = part.substringBefore('=', "")
                if (key.isEmpty()) null
                else key to URLDecoder.decode(part.substringAfter('='), "UTF-8")
            }
            .toMap()
}
