package com.example.telegramproxypingchecker

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.sync.Semaphore
import kotlinx.coroutines.sync.withPermit
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import org.json.JSONTokener
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLDecoder

data class Proxy(val url: String, val server: String, val port: Int, val secret: String)

data class ProxyResult(val proxy: Proxy, val pingMs: Double)

/** Почему прокси не прошла проверку (коды те же, что у бэкенда). */
enum class CheckError(val label: String) {
    BAD_SECRET("неверный формат секрета"),
    CONNECT_FAILED("не удалось подключиться"),
    TLS_REJECTED("Fake-TLS отклонён"),
    TLS_BAD_HMAC("Fake-TLS: чужая подпись"),
    NO_ANSWER("прокси закрыла соединение"),
    BAD_ANSWER("пришёл не тот ответ"),
    TIMEOUT("прокси молчит (таймаут)");

    companion object {
        fun from(error: ProxyCheckError): CheckError = when (error) {
            ProxyCheckError.BAD_SECRET -> BAD_SECRET
            ProxyCheckError.CONNECT_FAILED -> CONNECT_FAILED
            ProxyCheckError.TLS_REJECTED -> TLS_REJECTED
            ProxyCheckError.TLS_BAD_HMAC -> TLS_BAD_HMAC
            ProxyCheckError.NO_ANSWER -> NO_ANSWER
            ProxyCheckError.BAD_ANSWER -> BAD_ANSWER
            ProxyCheckError.TIMEOUT -> TIMEOUT
        }
    }
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
     * При ~2100 прокси и худшем случае 10 с (таймаут бэкенда) на прокси это до ~5 минут, обычно быстрее.
     */
    private const val PARALLELISM = 64

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

    private val mtproxyChecker = MTProxyChecker(timeout = MTProxyChecker.PROXY_PING_TIMEOUT)

    /**
     * 3. Проверка ровно как на бэкенде (MTProxyChecker.check из mtproto_checker.py):
     * для ee — Fake-TLS handshake, затем obfuscated2, req_pq_multi на DC 2 и ожидание resPQ.
     * Пинг — время от начала коннекта до ответа Telegram.
     */
    suspend fun check(proxy: Proxy): CheckOutcome {
        val result = mtproxyChecker.check(host = proxy.server, port = proxy.port, secret = proxy.secret)
        if (result.isConnected) {
            return CheckOutcome(ProxyResult(proxy, (result.latencyMs ?: 0).toDouble()), null)
        }
        return CheckOutcome(null, CheckError.from(result.error ?: ProxyCheckError.NO_ANSWER))
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
