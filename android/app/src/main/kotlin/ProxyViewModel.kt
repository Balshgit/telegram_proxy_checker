package com.example.tgproxycheck

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch

enum class Phase { Idle, Loading, Checking, Done, Cancelled, Error }

data class UiState(
    val phase: Phase = Phase.Idle,
    val total: Int = 0,
    val checked: Int = 0,
    val alive: List<ProxyResult> = emptyList(),
    val error: String? = null,
    val failures: Map<CheckError, Int> = emptyMap(),
) {
    val isBusy get() = phase == Phase.Loading || phase == Phase.Checking
}

class ProxyViewModel : ViewModel() {

    var state by mutableStateOf(UiState())
        private set

    private var job: Job? = null

    init {
        start()
    }

    fun start() {
        job?.cancel()
        job = viewModelScope.launch {
            state = UiState(phase = Phase.Loading)

            val proxies = try {
                ProxyChecker.fetchProxies { loaded -> state = state.copy(total = loaded) }
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                state = UiState(phase = Phase.Error, error = e.message ?: e.javaClass.simpleName)
                return@launch
            }

            state = state.copy(phase = Phase.Checking, total = proxies.size)

            ProxyChecker.checkAll(proxies) { outcome ->
                val result = outcome.result
                val error = outcome.error
                state = state.copy(
                    checked = state.checked + 1,
                    alive = if (result == null) state.alive
                    else (state.alive + result).sortedBy { it.pingMs },
                    failures = if (error == null) state.failures
                    else state.failures + (error to (state.failures[error] ?: 0) + 1),
                )
            }

            state = state.copy(phase = Phase.Done)
        }
    }

    /** Прерывает загрузку списка или проверку; уже найденные рабочие прокси остаются в списке. */
    fun cancel() {
        if (!state.isBusy) return
        job?.cancel()
        job = null
        state = state.copy(phase = Phase.Cancelled)
    }
}
