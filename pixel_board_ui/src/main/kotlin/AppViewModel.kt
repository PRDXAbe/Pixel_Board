package com.pixelboard

import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*
import kotlinx.serialization.json.Json
import java.io.File

class AppViewModel(val projectRoot: String) {

    private val processManager = ProcessManager(projectRoot)
    private val configPath     = File("$projectRoot/board_config.json")

    private val _state = MutableStateFlow(AppUiState(boardConfig = loadBoardConfig()))
    val state: StateFlow<AppUiState> = _state.asStateFlow()

    private val scope      = CoroutineScope(SupervisorJob() + Dispatchers.Default)
    private var bridgeJob: Job? = null

    private val json = Json { ignoreUnknownKeys = true; isLenient = true }

    // ── Config I/O ────────────────────────────────────────────────────────────

    private fun loadBoardConfig(): BoardConfig {
        if (!configPath.exists()) return BoardConfig()
        return runCatching {
            val raw = configPath.readText()
            // Simple key extraction without adding another dependency
            val w = Regex(""""board_width_mm"\s*:\s*(\d+)""").find(raw)?.groupValues?.get(1)?.toIntOrNull()
            val h = Regex(""""board_height_mm"\s*:\s*(\d+)""").find(raw)?.groupValues?.get(1)?.toIntOrNull()
            BoardConfig(
                widthMm  = w ?: 1000,
                heightMm = h ?: 500,
            )
        }.getOrDefault(BoardConfig())
    }

    fun saveBoardConfig(widthMm: Int, heightMm: Int) {
        _state.update { it.copy(boardConfig = BoardConfig(widthMm, heightMm)) }

        // Patch only the two fields — preserve everything else in the JSON
        scope.launch(Dispatchers.IO) {
            runCatching {
                val current = if (configPath.exists()) configPath.readText() else "{}"
                var updated = current
                    .replace(Regex(""""board_width_mm"\s*:\s*\d+"""),  """"board_width_mm": $widthMm""")
                    .replace(Regex(""""board_height_mm"\s*:\s*\d+"""), """"board_height_mm": $heightMm""")
                // If keys didn't exist, insert before closing brace
                if (!updated.contains("board_width_mm")) {
                    updated = updated.trimEnd().trimEnd('}') +
                        """,
  "board_width_mm": $widthMm,
  "board_height_mm": $heightMm
}"""
                }
                configPath.writeText(updated)
            }
        }
    }

    // ── Controls ──────────────────────────────────────────────────────────────

    fun start() {
        if (_state.value.isDriverRunning) return
        _state.update { it.copy(isDriverRunning = true, errorMessage = null) }

        scope.launch(Dispatchers.IO) {
            runCatching { processManager.startDriver() }.onFailure { e ->
                _state.update { it.copy(errorMessage = "Driver failed: ${e.message}") }
            }
        }

        bridgeJob = scope.launch {
            delay(3_000)
            processManager.streamBridgeOutput()
                .catch { e ->
                    _state.update { it.copy(isConnected = false, errorMessage = "Bridge: ${e.message}") }
                }
                .collect { line -> parseFrame(line) }
            _state.update { it.copy(isConnected = false) }
        }
    }

    fun stop() {
        bridgeJob?.cancel()
        bridgeJob = null
        scope.launch(Dispatchers.IO) { processManager.stopAll() }
        _state.update { it.copy(isDriverRunning = false, isConnected = false) }
    }

    fun dismissError() = _state.update { it.copy(errorMessage = null) }

    // ── Parsing ───────────────────────────────────────────────────────────────

    private fun parseFrame(line: String) {
        runCatching {
            val parsed = json.decodeFromString<BoardFrameJson>(line)
            _state.update { it.copy(isConnected = true, frame = parsed.toUiFrame()) }
        }
    }

    // ── Cleanup ───────────────────────────────────────────────────────────────

    fun dispose() {
        stop()
        scope.cancel()
    }
}
