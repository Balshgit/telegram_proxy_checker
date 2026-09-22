package com.example.tgproxycheck

import android.content.ActivityNotFoundException
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.widget.Toast
import java.util.Locale
import kotlin.math.roundToInt
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.scaleIn
import androidx.compose.animation.scaleOut
import androidx.compose.foundation.background
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.ExtendedFloatingActionButton
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.dynamicDarkColorScheme
import androidx.compose.material3.dynamicLightColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.derivedStateOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            AppTheme {
                val vm: ProxyViewModel = viewModel()
                ProxyScreen(state = vm.state, onRefresh = vm::start, onCancel = vm::cancel)
            }
        }
    }
}

@Composable
private fun AppTheme(content: @Composable () -> Unit) {
    val dark = isSystemInDarkTheme()
    val context = LocalContext.current
    val colors = when {
        Build.VERSION.SDK_INT >= Build.VERSION_CODES.S ->
            if (dark) dynamicDarkColorScheme(context) else dynamicLightColorScheme(context)
        dark -> darkColorScheme()
        else -> lightColorScheme()
    }
    MaterialTheme(colorScheme = colors, content = content)
}

@Composable
fun ProxyScreen(state: UiState, onRefresh: () -> Unit, onCancel: () -> Unit) {
    val context = LocalContext.current
    val listState = rememberLazyListState()
    val scope = rememberCoroutineScope()
    // Кнопка «Наверх» появляется, когда карточка статуса ушла за верхний край экрана.
    val showScrollToTop by remember { derivedStateOf { listState.firstVisibleItemIndex > 1 } }

    Scaffold(
        modifier = Modifier.fillMaxSize(),
        floatingActionButton = {
            AnimatedVisibility(
                visible = showScrollToTop,
                enter = fadeIn() + scaleIn(),
                exit = fadeOut() + scaleOut(),
            ) {
                ExtendedFloatingActionButton(
                    onClick = { scope.launch { listState.animateScrollToItem(0) } },
                ) {
                    Text("↑  Наверх")
                }
            }
        },
    ) { inner ->
        LazyColumn(
            state = listState,
            modifier = Modifier.fillMaxSize(),
            contentPadding = PaddingValues(
                start = 16.dp,
                end = 16.dp,
                top = inner.calculateTopPadding() + 16.dp,
                // Запас снизу, чтобы кнопка «Наверх» не закрывала последнюю карточку.
                bottom = inner.calculateBottomPadding() + 88.dp,
            ),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            item { Header() }
            item {
                StatusCard(
                    state = state,
                    onRefresh = onRefresh,
                    onCancel = onCancel,
                    onCopyAll = {
                        copy(context, state.alive.joinToString("\n") { it.proxy.url })
                    },
                )
            }
            if (state.phase == Phase.Done && state.alive.isEmpty()) {
                item { EmptyState() }
            }
            items(state.alive, key = { it.proxy.url }) { result ->
                ProxyCard(
                    result = result,
                    onOpen = { openInTelegram(context, result.proxy.url) },
                    onCopy = { copy(context, result.proxy.url) },
                )
            }
        }
    }
}

@Composable
private fun Header() {
    Column(Modifier.padding(bottom = 4.dp)) {
        Text(
            "tgproxycheck",
            style = MaterialTheme.typography.headlineMedium,
            fontWeight = FontWeight.Bold,
        )
        Text(
            "Рабочие MTProto-прокси для Telegram",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
private fun StatusCard(state: UiState, onRefresh: () -> Unit, onCancel: () -> Unit, onCopyAll: () -> Unit) {
    Card(
        shape = RoundedCornerShape(20.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer),
    ) {
        Column(Modifier.padding(18.dp)) {
            val title = when (state.phase) {
                Phase.Idle, Phase.Loading ->
                    if (state.total > 0) "Загружаю список… ${state.total}" else "Загружаю список…"
                Phase.Checking -> "Проверено ${state.checked} из ${state.total}"
                Phase.Done -> "Рабочих: ${state.alive.size} из ${state.total}"
                Phase.Cancelled ->
                    if (state.checked > 0) "Отменено: проверено ${state.checked} из ${state.total}, рабочих ${state.alive.size}"
                    else "Проверка отменена"
                Phase.Error -> "Не удалось загрузить список"
            }
            Text(
                title,
                style = MaterialTheme.typography.titleLarge,
                fontWeight = FontWeight.SemiBold,
                color = MaterialTheme.colorScheme.onPrimaryContainer,
            )

            if (state.phase == Phase.Error && state.error != null) {
                Spacer(Modifier.height(4.dp))
                Text(
                    state.error,
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.error,
                )
            }

            if (state.failures.isNotEmpty()) {
                Spacer(Modifier.height(8.dp))
                CheckError.entries
                    .filter { (state.failures[it] ?: 0) > 0 }
                    .forEach { error ->
                        Row(Modifier.fillMaxWidth().padding(vertical = 1.dp)) {
                            Text(
                                error.label,
                                modifier = Modifier.weight(1f),
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onPrimaryContainer.copy(alpha = 0.8f),
                            )
                            Text(
                                "${state.failures[error]}",
                                style = MaterialTheme.typography.bodySmall,
                                fontWeight = FontWeight.SemiBold,
                                color = MaterialTheme.colorScheme.onPrimaryContainer,
                            )
                        }
                    }
            }

            if (state.isBusy) {
                Spacer(Modifier.height(12.dp))
                if (state.phase == Phase.Checking && state.total > 0) {
                    LinearProgressIndicator(
                        progress = { state.checked.toFloat() / state.total },
                        modifier = Modifier.fillMaxWidth().height(6.dp).clip(CircleShape),
                    )
                } else {
                    LinearProgressIndicator(
                        modifier = Modifier.fillMaxWidth().height(6.dp).clip(CircleShape),
                    )
                }
            }

            Spacer(Modifier.height(14.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                if (state.isBusy) {
                    Button(
                        onClick = onCancel,
                        colors = ButtonDefaults.buttonColors(
                            containerColor = MaterialTheme.colorScheme.error,
                            contentColor = MaterialTheme.colorScheme.onError,
                        ),
                    ) {
                        CircularProgressIndicator(
                            modifier = Modifier.size(16.dp),
                            strokeWidth = 2.dp,
                            color = MaterialTheme.colorScheme.onError,
                        )
                        Spacer(Modifier.width(8.dp))
                        Text("Отменить")
                    }
                } else {
                    Button(onClick = onRefresh) {
                        Text("Проверить снова")
                    }
                }
                OutlinedButton(onClick = onCopyAll, enabled = state.alive.isNotEmpty()) {
                    Text("Копировать все")
                }
            }
        }
    }
}

@Composable
private fun ProxyCard(result: ProxyResult, onOpen: () -> Unit, onCopy: () -> Unit) {
    Card(
        onClick = onOpen,
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
    ) {
        Row(
            modifier = Modifier.padding(start = 16.dp, end = 8.dp, top = 12.dp, bottom = 12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            PingBadge(result)
            Spacer(Modifier.width(14.dp))
            Column(Modifier.weight(1f)) {
                Text(
                    "${result.proxy.server}:${result.proxy.port}",
                    fontFamily = FontFamily.Monospace,
                    fontWeight = FontWeight.SemiBold,
                    style = MaterialTheme.typography.bodyLarge,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                Text(
                    result.proxy.url,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
            TextButton(onClick = onCopy) { Text("Копир.") }
        }
    }
}

@Composable
private fun PingBadge(result: ProxyResult) {
    val ms = result.pingMs
    val color = when {
        ms < 150 -> Color(0xFF2E9E5B)
        ms < 400 -> Color(0xFFE0A100)
        else -> Color(0xFFD9534F)
    }
    val value = if (ms < 10) String.format(Locale.US, "%.1f", ms) else ms.roundToInt().toString()
    Column(
        modifier = Modifier
            .size(width = 72.dp, height = 40.dp)
            .clip(RoundedCornerShape(12.dp))
            .background(color.copy(alpha = 0.16f)),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(
            "$value ms",
            color = color,
            fontWeight = FontWeight.Bold,
            style = MaterialTheme.typography.labelLarge,
        )
    }
}

@Composable
private fun EmptyState() {
    Text(
        "Ни один прокси не ответил.\nПопробуйте проверить ещё раз чуть позже.",
        modifier = Modifier.fillMaxWidth().padding(vertical = 32.dp),
        textAlign = TextAlign.Center,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )
}

private fun openInTelegram(context: Context, url: String) {
    try {
        context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
    } catch (e: ActivityNotFoundException) {
        copy(context, url)
        Toast.makeText(context, "Telegram не найден — ссылка скопирована", Toast.LENGTH_SHORT).show()
    }
}

private fun copy(context: Context, text: String) {
    val clipboard = context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
    clipboard.setPrimaryClip(ClipData.newPlainText("proxy", text))
    Toast.makeText(context, "Скопировано", Toast.LENGTH_SHORT).show()
}
