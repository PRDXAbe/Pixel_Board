package com.pixelboard

import androidx.compose.ui.graphics.toComposeImageBitmap
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import java.awt.Frame
import java.io.File
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import kotlin.math.hypot
import kotlin.math.min
import kotlin.math.roundToInt

class AppViewModel(val projectRoot: String) {

    private val processManager = ProcessManager(projectRoot)
    private val configPath     = File("$projectRoot/board_config.json")
    private val captureDirPath = File("$projectRoot/captures")
    private val desktopInputController = createDesktopInputController()

    private val json = Json {
        ignoreUnknownKeys = true
        isLenient = true
        prettyPrint = true
        prettyPrintIndent = "  "
    }
    private val fileTimestampFormat = DateTimeFormatter.ofPattern("yyyyMMdd_HHmmss")
    private val initialBoardConfig = loadBoardConfig()
    private val _state = MutableStateFlow(AppUiState(boardConfig = initialBoardConfig))
    val state: StateFlow<AppUiState> = _state.asStateFlow()

    private val scope      = CoroutineScope(SupervisorJob() + Dispatchers.Default)
    private var bridgeJob: Job? = null
    private var displayRefreshJob: Job? = null
    private var screenPreviewJob: Job? = null
    private var interactivePointerJob: Job? = null
    private val runCaptureLock = Any()
    private val runTouchSamples = mutableListOf<RunTouchSample>()
    private val activeRunTouches = mutableMapOf<Int, ActiveRunTouch>()
    private var runStartedAt: Instant? = null
    private var activeInteractiveTouchId: Int? = null
    @Volatile
    private var interactiveGesture: InteractiveGestureSession? = null
    private val pendingTapJobs = mutableSetOf<Job>()
    private var lastUiFramePublishMs: Long = 0L

    init {
        val displays = probeAvailableDisplays()
        val selectedDisplayId = displays.firstOrNull()?.id
        _state.update { current ->
            val boardConfig = displays.firstOrNull { it.id == selectedDisplayId }
                ?.let { display -> withStandardScreenSizeIfMissing(current.boardConfig, display) }
                ?: current.boardConfig
            current.copy(
                boardConfig = boardConfig,
                availableDisplays = displays,
                selectedDisplayId = selectedDisplayId,
                desktopInjectionAvailable = desktopInputController.status.available,
                desktopInjectionMessage = buildDesktopStatusMessage(
                    availableDisplays = displays,
                    selectedDisplayId = selectedDisplayId,
                    interactiveModeEnabled = current.interactiveModeEnabled,
                    activeTouchId = null,
                ),
            )
        }
        displayRefreshJob = scope.launch {
            while (isActive) {
                refreshAvailableDisplays()
                delay(1_500)
            }
        }
        screenPreviewJob = scope.launch(Dispatchers.IO) {
            while (isActive) {
                refreshScreenPreview()
                delay(150)
            }
        }
    }

    // ── Config I/O ────────────────────────────────────────────────────────────

    private fun loadBoardConfig(): BoardConfig {
        if (!configPath.exists()) return BoardConfig()
        return runCatching {
            val current = readConfigObject()
            val defaults = BoardConfig()
            BoardConfig(
                widthMm = current.int("board_width_mm") ?: defaults.widthMm,
                heightMm = current.int("board_height_mm") ?: defaults.heightMm,
                lidarModel = current.string("lidar_model")
                    ?.let { value -> LidarModel.entries.firstOrNull { it.name.equals(value, ignoreCase = true) } }
                    ?: defaults.lidarModel,
                mountModeKey = current.string("mount_mode") ?: defaults.mountModeKey,
                standardScreenWidthPx = current.int("screen_width_px"),
                standardScreenHeightPx = current.int("screen_height_px"),
                geometry = BoardGeometry(
                    minX = current.float("board_min_x") ?: defaults.geometry.minX,
                    maxX = current.float("board_max_x") ?: defaults.geometry.maxX,
                    minY = current.float("board_min_y") ?: defaults.geometry.minY,
                    maxY = current.float("board_max_y") ?: defaults.geometry.maxY,
                ),
            )
        }.onFailure { error ->
            println(
                "PixelBoard config load failed: path=${configPath.absolutePath} " +
                    "exists=${configPath.exists()} error=${error.message}"
            )
        }.getOrDefault(BoardConfig())
    }

    fun saveBoardConfig(widthMm: Int, heightMm: Int) {
        updateBoardConfig { current ->
            val updated = current.copy(widthMm = widthMm, heightMm = heightMm)
            updated.copy(geometry = deriveGeometry(updated))
        }
    }

    fun setLidarModel(model: LidarModel) {
        updateBoardConfig { it.copy(lidarModel = model) }
    }

    fun setMountMode(mode: MountMode) {
        updateBoardConfig { current ->
            val updated = current.copy(mountModeKey = mode.configValue)
            updated.copy(geometry = deriveGeometry(updated))
        }
    }

    fun setInteractiveModeEnabled(enabled: Boolean) {
        if (!enabled) {
            releaseInteractivePointer()
            cancelPendingTap()
        }
        _state.update { current ->
            current.copy(
                interactiveModeEnabled = enabled,
                activeInteractiveTouchId = activeInteractiveTouchId,
                screenPreview = if (enabled) current.screenPreview else null,
                desktopInjectionMessage = buildDesktopStatusMessage(
                    availableDisplays = current.availableDisplays,
                    selectedDisplayId = current.selectedDisplayId,
                    interactiveModeEnabled = enabled,
                    activeTouchId = activeInteractiveTouchId,
                ),
            )
        }
    }

    fun selectDisplay(displayId: String) {
        releaseInteractivePointer()
        cancelPendingTap()
        _state.update { current ->
            val boardConfig = current.availableDisplays.firstOrNull { it.id == displayId }
                ?.let { display -> withStandardScreenSizeIfMissing(current.boardConfig, display) }
                ?: current.boardConfig
            current.copy(
                boardConfig = boardConfig,
                selectedDisplayId = displayId,
                activeInteractiveTouchId = null,
                screenPreview = null,
                desktopInjectionMessage = buildDesktopStatusMessage(
                    availableDisplays = current.availableDisplays,
                    selectedDisplayId = displayId,
                    interactiveModeEnabled = current.interactiveModeEnabled,
                    activeTouchId = null,
                ),
            )
        }
    }

    fun saveBoardGeometry(geometry: BoardGeometry) {
        updateBoardConfig { it.copy(geometry = geometry) }
    }

    private fun withStandardScreenSizeIfMissing(config: BoardConfig, display: DisplayTarget): BoardConfig =
        if (config.standardScreenWidthPx != null && config.standardScreenHeightPx != null) {
            config
        } else {
            config.copy(
                standardScreenWidthPx = config.standardScreenWidthPx ?: display.width,
                standardScreenHeightPx = config.standardScreenHeightPx ?: display.height,
            )
        }

    private fun persistConfig() {
        val cfg = _state.value.boardConfig
        scope.launch(Dispatchers.IO) {
            runCatching {
                val merged = readConfigObject().toMutableMap().apply {
                    put("board_width_mm", JsonPrimitive(cfg.widthMm))
                    put("board_height_mm", JsonPrimitive(cfg.heightMm))
                    put("lidar_model", JsonPrimitive(cfg.lidarModel.name))
                    put("mount_mode", JsonPrimitive(cfg.mountModeKey))
                    cfg.standardScreenWidthPx?.let { put("screen_width_px", JsonPrimitive(it)) }
                    cfg.standardScreenHeightPx?.let { put("screen_height_px", JsonPrimitive(it)) }
                    put("board_min_x", JsonPrimitive(cfg.geometry.minX))
                    put("board_max_x", JsonPrimitive(cfg.geometry.maxX))
                    put("board_min_y", JsonPrimitive(cfg.geometry.minY))
                    put("board_max_y", JsonPrimitive(cfg.geometry.maxY))
                }
                configPath.writeText(json.encodeToString(JsonObject.serializer(), JsonObject(merged)))
            }
        }
    }

    private fun updateBoardConfig(transform: (BoardConfig) -> BoardConfig) {
        _state.update { current -> current.copy(boardConfig = transform(current.boardConfig)) }
        persistConfig()
    }

    private fun readConfigObject(): JsonObject {
        if (!configPath.exists()) return JsonObject(emptyMap())
        return runCatching {
            json.parseToJsonElement(configPath.readText()).jsonObject
        }.onFailure { error ->
            println(
                "PixelBoard config parse failed: path=${configPath.absolutePath} " +
                    "error=${error.message}"
            )
        }.getOrDefault(JsonObject(emptyMap()))
    }

    // ── Controls ──────────────────────────────────────────────────────────────

    fun start() {
        if (_state.value.isDriverRunning) return
        resetRunCapture()
        cancelPendingTap()
        _state.update {
            it.copy(
                isDriverRunning = true,
                errorMessage = null,
                activeInteractiveTouchId = null,
                desktopInjectionMessage = buildDesktopStatusMessage(
                    availableDisplays = it.availableDisplays,
                    selectedDisplayId = it.selectedDisplayId,
                    interactiveModeEnabled = it.interactiveModeEnabled,
                    activeTouchId = null,
                ),
            )
        }

        val model = _state.value.boardConfig.lidarModel
        scope.launch(Dispatchers.IO) {
            runCatching { processManager.startDriver(model) }.onFailure { e ->
                _state.update { it.copy(errorMessage = "Driver failed: ${e.message}") }
            }
        }

        bridgeJob = scope.launch {
            delay(3_000)
            processManager.streamBridgeOutput()
                .catch { e ->
                    releaseInteractivePointer()
                    _state.update { it.copy(isConnected = false, errorMessage = "Bridge: ${e.message}") }
                }
                .collect { line -> parseFrame(line) }
            releaseInteractivePointer()
            _state.update {
                it.copy(
                    isConnected = false,
                    activeInteractiveTouchId = null,
                    desktopInjectionMessage = buildDesktopStatusMessage(
                        availableDisplays = it.availableDisplays,
                        selectedDisplayId = it.selectedDisplayId,
                        interactiveModeEnabled = it.interactiveModeEnabled,
                        activeTouchId = null,
                    ),
                )
            }
        }
    }

    fun stop() {
        val finalizedCount = finalizeActiveRunTouches()
        releaseInteractivePointer()
        cancelPendingTap()
        bridgeJob?.cancel()
        bridgeJob = null
        scope.launch(Dispatchers.IO) { processManager.stopAll() }
        _state.update {
            it.copy(
                isDriverRunning = false,
                isConnected = false,
                runCaptureCount = finalizedCount,
                activeInteractiveTouchId = null,
                desktopInjectionMessage = buildDesktopStatusMessage(
                    availableDisplays = it.availableDisplays,
                    selectedDisplayId = it.selectedDisplayId,
                    interactiveModeEnabled = it.interactiveModeEnabled,
                    activeTouchId = null,
                ),
            )
        }
    }

    fun dismissError() = _state.update { it.copy(errorMessage = null) }

    fun saveRunCapture() {
        val snapshot = snapshotRunCapture() ?: return

        val currentState = _state.value
        val frame = currentState.frame
        val boardWidthMm = if (frame.boardWidthMm > 0) frame.boardWidthMm else currentState.boardConfig.widthMm
        val boardHeightMm = if (frame.boardHeightMm > 0) frame.boardHeightMm else currentState.boardConfig.heightMm
        val mountMode = frame.mountMode.ifBlank { currentState.boardConfig.mountModeKey }
        val payload = RunCaptureExport(
            startedAt = snapshot.first.toString(),
            savedAt = Instant.now().toString(),
            lidarModel = currentState.boardConfig.lidarModel.name,
            boardWidthMm = boardWidthMm,
            boardHeightMm = boardHeightMm,
            mountMode = mountMode,
            sampleCount = snapshot.second.size,
            samples = snapshot.second,
        )

        scope.launch(Dispatchers.IO) {
            runCatching {
                captureDirPath.mkdirs()
                val stamp = fileTimestampFormat.format(snapshot.first.atZone(ZoneId.systemDefault()))
                val outFile = File(captureDirPath, "pixelboard_run_$stamp.json")
                outFile.writeText(json.encodeToString(RunCaptureExport.serializer(), payload))
                outFile.absolutePath
            }.onSuccess { path ->
                _state.update { it.copy(lastSavedRunPath = path) }
            }.onFailure { e ->
                _state.update { it.copy(errorMessage = "Save run failed: ${e.message}") }
            }
        }
    }

    // ── Parsing ───────────────────────────────────────────────────────────────

    private fun parseFrame(line: String) {
        runCatching {
            val parsed = json.decodeFromString<BoardFrameJson>(line)
            val frame = parsed.toUiFrame()
            val currentState = _state.value
            val runCaptureCount = updateRunCapture(frame)
            val activeTouchId = syncInteractivePointer(frame, currentState)
            val nowMs = System.currentTimeMillis()
            val touchIdsChanged = currentState.frame.touches.map { it.id } != frame.touches.map { it.id }
            val touchCountChanged = currentState.frame.touches.size != frame.touches.size
            val shouldPublishFrame =
                currentState.frame.scanCount == 0 ||
                nowMs - lastUiFramePublishMs >= UI_FRAME_PUBLISH_INTERVAL_MS ||
                touchIdsChanged ||
                touchCountChanged
            val shouldUpdateState =
                shouldPublishFrame ||
                !currentState.isConnected ||
                currentState.runCaptureCount != runCaptureCount ||
                currentState.activeInteractiveTouchId != activeTouchId

            if (!shouldUpdateState) {
                return@runCatching
            }

            if (shouldPublishFrame) {
                lastUiFramePublishMs = nowMs
            }

            _state.update {
                it.copy(
                    isConnected = true,
                    frame = if (shouldPublishFrame) frame else it.frame,
                    runCaptureCount = runCaptureCount,
                    activeInteractiveTouchId = activeTouchId,
                    desktopInjectionMessage = buildDesktopStatusMessage(
                        availableDisplays = it.availableDisplays,
                        selectedDisplayId = it.selectedDisplayId,
                        interactiveModeEnabled = it.interactiveModeEnabled,
                        activeTouchId = activeTouchId,
                    ),
                )
            }
        }
    }

    private fun resetRunCapture() {
        synchronized(runCaptureLock) {
            runTouchSamples.clear()
            activeRunTouches.clear()
            runStartedAt = Instant.now()
        }
        _state.update { it.copy(runCaptureCount = 0, lastSavedRunPath = null) }
    }

    private fun updateRunCapture(frame: BoardFrame): Int {
        val now = Instant.now()
        synchronized(runCaptureLock) {
            val startedAt = runStartedAt ?: now.also { runStartedAt = it }
            val elapsedMs = now.toEpochMilli() - startedAt.toEpochMilli()
            val seenTouchIds = mutableSetOf<Int>()

            frame.touches.forEach { touch ->
                seenTouchIds += touch.id
                activeRunTouches[touch.id] = ActiveRunTouch(
                    touchId = touch.id,
                    elapsedMs = elapsedMs,
                    scanCount = frame.scanCount,
                    rateHz = frame.rateHz,
                    px = touch.px,
                    py = touch.py,
                    mx = touch.mx,
                    my = touch.my,
                )
            }

            val releasedTouchIds = activeRunTouches.keys
                .filterNot { it in seenTouchIds }
                .sorted()
            releasedTouchIds.forEach { touchId ->
                val finishedTouch = activeRunTouches.remove(touchId) ?: return@forEach
                runTouchSamples += finishedTouch.toSample()
            }

            return runTouchSamples.size
        }
    }

    private fun snapshotRunCapture(): Pair<Instant, List<RunTouchSample>>? =
        synchronized(runCaptureLock) {
            val startedAt = runStartedAt ?: return@synchronized null
            val samples = buildList {
                addAll(runTouchSamples)
                activeRunTouches.values
                    .sortedBy { it.touchId }
                    .forEach { add(it.toSample()) }
            }
            if (samples.isEmpty()) {
                null
            } else {
                startedAt to samples
            }
        }

    private fun finalizeActiveRunTouches(): Int =
        synchronized(runCaptureLock) {
            activeRunTouches.values
                .sortedBy { it.touchId }
                .forEach { runTouchSamples += it.toSample() }
            activeRunTouches.clear()
            runTouchSamples.size
        }

    private fun syncInteractivePointer(frame: BoardFrame, uiState: AppUiState): Int? {
        if (!uiState.interactiveModeEnabled || !uiState.desktopInjectionAvailable) {
            releaseInteractivePointer()
            return null
        }

        val selectedDisplay = uiState.availableDisplays.firstOrNull { it.id == uiState.selectedDisplayId }
        if (selectedDisplay == null) {
            releaseInteractivePointer()
            return null
        }

        val nowMs = System.currentTimeMillis()
        val currentSession = interactiveGesture
        if (currentSession != null) {
            val activeTouch = frame.touches.firstOrNull { it.id == currentSession.touchId }
            if (activeTouch == null) {
                finalizeInteractiveGesture(currentSession, nowMs)
                return null
            }

            val rawScreen = mapTouchToDisplay(activeTouch, selectedDisplay, frame)
            val currentScreen = stabilizeInteractiveScreenPosition(
                previousX = currentSession.lastMeasuredScreenX,
                previousY = currentSession.lastMeasuredScreenY,
                rawX = rawScreen.first,
                rawY = rawScreen.second,
            )
            val pointerVelocity = computeInteractivePointerVelocity(
                previousMeasuredX = currentSession.lastMeasuredScreenX,
                previousMeasuredY = currentSession.lastMeasuredScreenY,
                previousMeasuredAtMs = currentSession.lastMeasuredAtMs,
                currentMeasuredX = currentScreen.first,
                currentMeasuredY = currentScreen.second,
                currentMeasuredAtMs = nowMs,
            )
            val isUnsafeTarget = shouldSuppressInteractiveTarget(currentScreen.first, currentScreen.second)
            val movedSinceLastMm = hypot(
                (activeTouch.px - currentSession.lastTouch.px).toDouble(),
                (activeTouch.py - currentSession.lastTouch.py).toDouble(),
            )
            val movedFromAnchorMm = hypot(
                (activeTouch.px - currentSession.hoverAnchorTouch.px).toDouble(),
                (activeTouch.py - currentSession.hoverAnchorTouch.py).toDouble(),
            )
            val stationarySinceMs = if (movedSinceLastMm <= HOLD_STATIONARY_RADIUS_MM) {
                currentSession.stationarySinceMs
            } else {
                nowMs
            }
            val keepAnchor = !isUnsafeTarget && movedFromAnchorMm <= INTERACTION_HOVER_ANCHOR_RADIUS_MM
            val anchorTouch = if (keepAnchor) {
                currentSession.hoverAnchorTouch
            } else {
                activeTouch
            }
            val anchorScreenX = if (keepAnchor) {
                currentSession.hoverAnchorScreenX
            } else {
                currentScreen.first
            }
            val anchorScreenY = if (keepAnchor) {
                currentSession.hoverAnchorScreenY
            } else {
                currentScreen.second
            }
            val anchorFrames = if (keepAnchor) {
                currentSession.hoverAnchorFrames + 1
            } else {
                1
            }
            val anchorSinceMs = if (keepAnchor) {
                currentSession.hoverAnchorSinceMs
            } else {
                nowMs
            }
            val keepDwellAnchor = !isUnsafeTarget &&
                isWithinDwellDoubleClickRadius(
                    anchorScreenX = currentSession.dwellAnchorScreenX,
                    anchorScreenY = currentSession.dwellAnchorScreenY,
                    currentScreenX = currentScreen.first,
                    currentScreenY = currentScreen.second,
                )
            val dwellAnchorScreenX = if (keepDwellAnchor) {
                currentSession.dwellAnchorScreenX
            } else {
                currentScreen.first
            }
            val dwellAnchorScreenY = if (keepDwellAnchor) {
                currentSession.dwellAnchorScreenY
            } else {
                currentScreen.second
            }
            val dwellAnchorStartedAtMs = if (keepDwellAnchor) {
                currentSession.dwellAnchorStartedAtMs
            } else {
                nowMs
            }
            val dwellDoubleClickTriggered = !isUnsafeTarget &&
                shouldTriggerDwellDoubleClick(
                    anchorScreenX = dwellAnchorScreenX,
                    anchorScreenY = dwellAnchorScreenY,
                    currentScreenX = currentScreen.first,
                    currentScreenY = currentScreen.second,
                    stableElapsedMs = nowMs - dwellAnchorStartedAtMs,
                )
            val baseSession = currentSession.copy(
                lastTouch = activeTouch,
                lastScreenX = currentScreen.first,
                lastScreenY = currentScreen.second,
                stationarySinceMs = stationarySinceMs,
                seenFrames = currentSession.seenFrames + 1,
                hoverAnchorTouch = anchorTouch,
                hoverAnchorScreenX = anchorScreenX,
                hoverAnchorScreenY = anchorScreenY,
                hoverAnchorFrames = anchorFrames,
                hoverAnchorSinceMs = anchorSinceMs,
                suppressDesktopActions = isUnsafeTarget,
                lastMeasuredScreenX = currentScreen.first,
                lastMeasuredScreenY = currentScreen.second,
                lastMeasuredAtMs = nowMs,
                velocityScreenXPxPerMs = pointerVelocity.first,
                velocityScreenYPxPerMs = pointerVelocity.second,
                dwellAnchorScreenX = if (dwellDoubleClickTriggered) currentScreen.first else dwellAnchorScreenX,
                dwellAnchorScreenY = if (dwellDoubleClickTriggered) currentScreen.second else dwellAnchorScreenY,
                dwellAnchorStartedAtMs = if (dwellDoubleClickTriggered) nowMs else dwellAnchorStartedAtMs,
                tapActionConsumed = currentSession.tapActionConsumed || dwellDoubleClickTriggered,
            )

            if (dwellDoubleClickTriggered) {
                performDoubleClick(dwellAnchorScreenX, dwellAnchorScreenY)
            }

            if (baseSession.isButtonDown && isUnsafeTarget) {
                desktopInputController.mouseUp()
                val safeSession = baseSession.copy(
                    isButtonDown = false,
                    isDragArmed = false,
                    isDragging = false,
                    stationarySinceMs = nowMs,
                    pressAnchorTouch = null,
                )
                desktopInputController.move(currentScreen.first, currentScreen.second)
                interactiveGesture = safeSession
                activeInteractiveTouchId = safeSession.touchId
                return safeSession.touchId
            }

            val updatedSession = when {
                baseSession.suppressDesktopActions || isUnsafeTarget -> {
                    desktopInputController.move(currentScreen.first, currentScreen.second)
                    baseSession
                }

                else -> {
                    desktopInputController.move(currentScreen.first, currentScreen.second)
                    baseSession
                }
            }
            interactiveGesture = updatedSession
            activeInteractiveTouchId = updatedSession.touchId
            ensureInteractivePointerLoop()
            return updatedSession.touchId
        }

        val targetTouch = frame.touches.minByOrNull { it.id } ?: run {
            releaseInteractivePointer()
            return null
        }
        val (screenX, screenY) = mapTouchToDisplay(targetTouch, selectedDisplay, frame)
        val suppressDesktopActions = shouldSuppressInteractiveTarget(screenX, screenY)
        desktopInputController.move(screenX, screenY)
        interactiveGesture = InteractiveGestureSession(
            touchId = targetTouch.id,
            startMs = nowMs,
            startTouch = targetTouch,
            lastTouch = targetTouch,
            startScreenX = screenX,
            startScreenY = screenY,
            lastScreenX = screenX,
            lastScreenY = screenY,
            isButtonDown = false,
            isDragArmed = false,
            isDragging = false,
            stationarySinceMs = nowMs,
            pressAnchorTouch = null,
            seenFrames = 1,
            suppressDesktopActions = suppressDesktopActions,
            hoverAnchorTouch = targetTouch,
            hoverAnchorScreenX = screenX,
            hoverAnchorScreenY = screenY,
            hoverAnchorFrames = if (suppressDesktopActions) 0 else 1,
            hoverAnchorSinceMs = nowMs,
            lastMeasuredScreenX = screenX,
            lastMeasuredScreenY = screenY,
            lastMeasuredAtMs = nowMs,
            velocityScreenXPxPerMs = 0.0,
            velocityScreenYPxPerMs = 0.0,
            dwellAnchorScreenX = screenX,
            dwellAnchorScreenY = screenY,
            dwellAnchorStartedAtMs = nowMs,
            tapActionConsumed = false,
        )
        activeInteractiveTouchId = targetTouch.id
        ensureInteractivePointerLoop()
        return targetTouch.id
    }

    private fun ensureInteractivePointerLoop() {
        if (interactivePointerJob?.isActive == true) {
            return
        }

        interactivePointerJob = scope.launch {
            var lastTouchId: Int? = null
            var lastProjectedX: Int? = null
            var lastProjectedY: Int? = null

            while (isActive) {
                val session = interactiveGesture
                if (session == null) {
                    lastTouchId = null
                    lastProjectedX = null
                    lastProjectedY = null
                    delay(INTERACTION_POINTER_TICK_MS)
                    continue
                }

                if (session.touchId != lastTouchId) {
                    lastTouchId = session.touchId
                    lastProjectedX = null
                    lastProjectedY = null
                }

                val predictedScreen = predictInteractiveScreenPosition(
                    measuredX = session.lastMeasuredScreenX,
                    measuredY = session.lastMeasuredScreenY,
                    velocityXPxPerMs = session.velocityScreenXPxPerMs,
                    velocityYPxPerMs = session.velocityScreenYPxPerMs,
                    elapsedSinceMeasurementMs = System.currentTimeMillis() - session.lastMeasuredAtMs,
                )

                if (
                    !session.suppressDesktopActions &&
                    !shouldSuppressInteractiveTarget(predictedScreen.first, predictedScreen.second) &&
                    (predictedScreen.first != lastProjectedX || predictedScreen.second != lastProjectedY)
                ) {
                    desktopInputController.move(predictedScreen.first, predictedScreen.second)
                    lastProjectedX = predictedScreen.first
                    lastProjectedY = predictedScreen.second
                }

                delay(INTERACTION_POINTER_TICK_MS)
            }
        }
    }

    private fun releaseInteractivePointer() {
        interactivePointerJob?.cancel()
        interactivePointerJob = null
        desktopInputController.releaseAll()
        activeInteractiveTouchId = null
        interactiveGesture = null
    }

    private fun cancelPendingTap() {
        val jobsToCancel = synchronized(pendingTapJobs) {
            pendingTapJobs.toList().also { pendingTapJobs.clear() }
        }
        jobsToCancel.forEach { it.cancel() }
    }

    private fun schedulePendingTap(screenX: Int, screenY: Int) {
        val job = scope.launch {
            delay(SINGLE_CLICK_DELAY_MS)
            performClick(screenX, screenY)
        }
        synchronized(pendingTapJobs) {
            pendingTapJobs += job
        }
        job.invokeOnCompletion {
            synchronized(pendingTapJobs) {
                pendingTapJobs.remove(job)
            }
        }
    }

    private fun finalizeInteractiveGesture(
        session: InteractiveGestureSession,
        nowMs: Long,
    ) {
        if (session.isButtonDown) {
            desktopInputController.mouseUp()
            activeInteractiveTouchId = null
            interactiveGesture = null
            return
        }

        if (session.tapActionConsumed) {
            activeInteractiveTouchId = null
            interactiveGesture = null
            return
        }

        val lastTouch = session.lastTouch
        val releaseDriftMm = hypot(
            (lastTouch.px - session.hoverAnchorTouch.px).toDouble(),
            (lastTouch.py - session.hoverAnchorTouch.py).toDouble(),
        )
        val isTap = !session.suppressDesktopActions &&
            !shouldSuppressInteractiveTarget(session.hoverAnchorScreenX, session.hoverAnchorScreenY) &&
            isTapFrameConfirmationSatisfied(
                seenFrames = session.seenFrames,
                hoverAnchorFrames = session.hoverAnchorFrames,
            ) &&
            releaseDriftMm <= INTERACTION_RELEASE_DRIFT_MAX_MM
        if (isTap) {
            schedulePendingTap(session.hoverAnchorScreenX, session.hoverAnchorScreenY)
        }
        activeInteractiveTouchId = null
        interactiveGesture = null
    }

    private fun startHold(
        session: InteractiveGestureSession,
        currentTouch: TouchPoint,
        currentScreen: Pair<Int, Int>,
    ): InteractiveGestureSession {
        desktopInputController.move(currentScreen.first, currentScreen.second)
        desktopInputController.mouseDown()
        return session.copy(
            lastTouch = currentTouch,
            lastScreenX = currentScreen.first,
            lastScreenY = currentScreen.second,
            isButtonDown = true,
            isDragArmed = true,
            isDragging = false,
            stationarySinceMs = session.stationarySinceMs,
            pressAnchorTouch = currentTouch,
        )
    }

    private fun startDrag(
        session: InteractiveGestureSession,
        currentTouch: TouchPoint,
        currentScreen: Pair<Int, Int>,
    ): InteractiveGestureSession {
        if (!session.isButtonDown) {
            desktopInputController.move(currentScreen.first, currentScreen.second)
            desktopInputController.mouseDown()
        }
        desktopInputController.move(currentScreen.first, currentScreen.second)
        return session.copy(
            lastTouch = currentTouch,
            isButtonDown = true,
            isDragArmed = true,
            isDragging = true,
            lastScreenX = currentScreen.first,
            lastScreenY = currentScreen.second,
            pressAnchorTouch = session.pressAnchorTouch ?: currentTouch,
        )
    }

    private fun performClick(screenX: Int, screenY: Int) {
        if (shouldSuppressInteractiveTarget(screenX, screenY)) {
            return
        }
        desktopInputController.click(screenX, screenY)
    }

    private fun performDoubleClick(screenX: Int, screenY: Int) {
        if (shouldSuppressInteractiveTarget(screenX, screenY)) {
            return
        }
        desktopInputController.doubleClick(screenX, screenY)
    }

    private fun shouldSuppressInteractiveTarget(screenX: Int, screenY: Int): Boolean =
        findPixelBoardWindowBounds()?.contains(screenX, screenY) == true

    private fun mapTouchToDisplay(
        touch: TouchPoint,
        display: DisplayTarget,
        frame: BoardFrame,
    ): Pair<Int, Int> {
        val mapping = computeBoardDisplayMapping(display, frame)
        val touchPx = touch.px.toFloat().coerceIn(0f, mapping.boardWidthMm)
        val touchPy = touch.py.toFloat().coerceIn(0f, mapping.boardHeightMm)
        val minScreenX = display.x + mapping.offsetXPx
        val minScreenY = display.y + mapping.offsetYPx
        val maxScreenX = minScreenX + mapping.contentWidthPx - 1
        val maxScreenY = minScreenY + mapping.contentHeightPx - 1
        val screenX = (minScreenX + (touchPx * mapping.pixelsPerMm).roundToInt()).coerceIn(minScreenX, maxScreenX)
        val screenY = (minScreenY + (touchPy * mapping.pixelsPerMm).roundToInt()).coerceIn(minScreenY, maxScreenY)
        return screenX to screenY
    }

    private fun computeBoardDisplayMapping(
        display: DisplayTarget,
        frame: BoardFrame,
    ): BoardDisplayMapping {
        val config = _state.value.boardConfig
        val boardWidthMm = (if (frame.boardWidthMm > 0) frame.boardWidthMm else config.widthMm)
            .coerceAtLeast(1)
        val boardHeightMm = (if (frame.boardHeightMm > 0) frame.boardHeightMm else config.heightMm)
            .coerceAtLeast(1)
        val referenceWidthPx = (config.standardScreenWidthPx ?: display.width).coerceAtLeast(1)
        val referenceHeightPx = (config.standardScreenHeightPx ?: display.height).coerceAtLeast(1)
        val mappingWidthPx = min(referenceWidthPx, display.width)
        val mappingHeightPx = min(referenceHeightPx, display.height)

        val pixelsPerMm = min(
            mappingWidthPx.toFloat() / boardWidthMm.toFloat(),
            mappingHeightPx.toFloat() / boardHeightMm.toFloat(),
        ).coerceAtLeast(0.001f)

        val contentWidthPx = (boardWidthMm.toFloat() * pixelsPerMm).roundToInt().coerceAtLeast(1)
        val contentHeightPx = (boardHeightMm.toFloat() * pixelsPerMm).roundToInt().coerceAtLeast(1)
        val offsetXPx = ((mappingWidthPx - contentWidthPx) / 2f).roundToInt()
        val offsetYPx = ((mappingHeightPx - contentHeightPx) / 2f).roundToInt()

        return BoardDisplayMapping(
            boardWidthMm = boardWidthMm.toFloat(),
            boardHeightMm = boardHeightMm.toFloat(),
            pixelsPerMm = pixelsPerMm,
            offsetXPx = offsetXPx,
            offsetYPx = offsetYPx,
            contentWidthPx = contentWidthPx,
            contentHeightPx = contentHeightPx,
            referenceWidthPx = referenceWidthPx,
            referenceHeightPx = referenceHeightPx,
        )
    }

    private fun refreshScreenPreview() {
        val current = _state.value
        if (!current.interactiveModeEnabled) {
            if (current.screenPreview != null) {
                _state.update { it.copy(screenPreview = null) }
            }
            return
        }

        val selectedDisplay = current.availableDisplays.firstOrNull { it.id == current.selectedDisplayId }
        if (selectedDisplay == null) {
            if (current.screenPreview != null) {
                _state.update { it.copy(screenPreview = null) }
            }
            return
        }

        val capture = desktopInputController.capture(selectedDisplay)
        if (capture == null) {
            if (current.screenPreview != null) {
                _state.update { it.copy(screenPreview = null) }
            }
            return
        }

        val preview = capture.toComposeImageBitmap()
        _state.update { state ->
            if (state.selectedDisplayId == selectedDisplay.id) {
                state.copy(screenPreview = preview)
            } else {
                state
            }
        }
    }

    private fun refreshAvailableDisplays() {
        val displays = probeAvailableDisplays()
        val currentState = _state.value
        val resolvedSelectedDisplayId = when {
            displays.any { it.id == currentState.selectedDisplayId } -> currentState.selectedDisplayId
            displays.isNotEmpty() -> displays.first().id
            else -> null
        }

        if (resolvedSelectedDisplayId != currentState.selectedDisplayId) {
            releaseInteractivePointer()
        }

        _state.update { current ->
            current.copy(
                availableDisplays = displays,
                selectedDisplayId = resolvedSelectedDisplayId,
                activeInteractiveTouchId = activeInteractiveTouchId,
                screenPreview = if (resolvedSelectedDisplayId == current.selectedDisplayId) current.screenPreview else null,
                desktopInjectionMessage = buildDesktopStatusMessage(
                    availableDisplays = displays,
                    selectedDisplayId = resolvedSelectedDisplayId,
                    interactiveModeEnabled = current.interactiveModeEnabled,
                    activeTouchId = activeInteractiveTouchId,
                ),
            )
        }
    }

    private fun buildDesktopStatusMessage(
        availableDisplays: List<DisplayTarget>,
        selectedDisplayId: String?,
        interactiveModeEnabled: Boolean,
        activeTouchId: Int?,
    ): String {
        if (availableDisplays.isEmpty()) {
            return if (interactiveModeEnabled) {
                "Interactive mode is on, but no target display is available."
            } else {
                desktopInputController.status.message
            }
        }

        val selectedDisplay = availableDisplays.firstOrNull { it.id == selectedDisplayId }
            ?: return if (interactiveModeEnabled) {
                "Interactive mode is on, but no display is selected yet."
            } else {
                "Select a display to enable projected interaction."
            }

        if (!desktopInputController.status.available) {
            return if (interactiveModeEnabled) {
                "Interactive mode is on for ${selectedDisplay.name}, but desktop injection is unavailable. ${desktopInputController.status.message}"
            } else {
                desktopInputController.status.message
            }
        }
        return when {
            !interactiveModeEnabled ->
                "Interactive mode is off. Selected display: ${selectedDisplay.name}."
            activeTouchId != null ->
                "Projected interaction is active on ${selectedDisplay.name} with touch #$activeTouchId."
            else ->
                "Interactive mode is armed for ${selectedDisplay.name}."
        }
    }

    // ── Cleanup ───────────────────────────────────────────────────────────────

    fun dispose() {
        releaseInteractivePointer()
        stop()
        displayRefreshJob?.cancel()
        screenPreviewJob?.cancel()
        scope.cancel()
    }
}

private fun findPixelBoardWindowBounds() =
    Frame.getFrames()
        .firstOrNull {
            shouldUsePixelBoardWindowSuppression(
                title = it.title,
                isShowing = it.isShowing,
                extendedState = it.extendedState,
                isActive = it.isActive,
            )
        }
        ?.bounds

private data class ActiveRunTouch(
    val touchId: Int,
    val elapsedMs: Long,
    val scanCount: Int,
    val rateHz: Float,
    val px: Int,
    val py: Int,
    val mx: Float,
    val my: Float,
) {
    fun toSample(): RunTouchSample = RunTouchSample(
        touchId = touchId,
        elapsedMs = elapsedMs,
        scanCount = scanCount,
        rateHz = rateHz,
        px = px,
        py = py,
        mx = mx,
        my = my,
    )
}

private data class InteractiveGestureSession(
    val touchId: Int,
    val startMs: Long,
    val startTouch: TouchPoint,
    val lastTouch: TouchPoint,
    val startScreenX: Int,
    val startScreenY: Int,
    val lastScreenX: Int,
    val lastScreenY: Int,
    val isButtonDown: Boolean,
    val isDragArmed: Boolean,
    val isDragging: Boolean,
    val stationarySinceMs: Long,
    val pressAnchorTouch: TouchPoint?,
    val seenFrames: Int,
    val suppressDesktopActions: Boolean,
    val hoverAnchorTouch: TouchPoint,
    val hoverAnchorScreenX: Int,
    val hoverAnchorScreenY: Int,
    val hoverAnchorFrames: Int,
    val hoverAnchorSinceMs: Long,
    val lastMeasuredScreenX: Int,
    val lastMeasuredScreenY: Int,
    val lastMeasuredAtMs: Long,
    val velocityScreenXPxPerMs: Double,
    val velocityScreenYPxPerMs: Double,
    val dwellAnchorScreenX: Int,
    val dwellAnchorScreenY: Int,
    val dwellAnchorStartedAtMs: Long,
    val tapActionConsumed: Boolean,
)

private data class BoardDisplayMapping(
    val boardWidthMm: Float,
    val boardHeightMm: Float,
    val pixelsPerMm: Float,
    val offsetXPx: Int,
    val offsetYPx: Int,
    val contentWidthPx: Int,
    val contentHeightPx: Int,
    val referenceWidthPx: Int,
    val referenceHeightPx: Int,
)

private fun JsonObject.string(key: String): String? =
    this[key]?.jsonPrimitive?.contentOrNull

private fun JsonObject.int(key: String): Int? =
    this[key]?.jsonPrimitive?.contentOrNull?.toIntOrNull()

private fun JsonObject.float(key: String): Float? =
    this[key]?.jsonPrimitive?.contentOrNull?.toFloatOrNull()

private fun deriveGeometry(config: BoardConfig): BoardGeometry {
    val gap = config.geometry.minX.coerceAtLeast(0f)
    val widthM = config.widthMm / 1000f
    val heightM = config.heightMm / 1000f

    return when (config.mountMode) {
        MountMode.BOTTOM_CENTER -> BoardGeometry(
            minX = gap,
            maxX = gap + heightM,
            minY = -widthM / 2f,
            maxY = widthM / 2f,
        )
        MountMode.SIDE_EDGE -> BoardGeometry(
            minX = gap,
            maxX = gap + widthM,
            minY = -heightM / 2f,
            maxY = heightM / 2f,
        )
        else -> config.geometry
    }
}
