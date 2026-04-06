import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.*
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.layout.onGloballyPositioned
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.IntSize
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import androidx.compose.ui.window.Window
import androidx.compose.ui.window.WindowPlacement
import androidx.compose.ui.window.application
import androidx.compose.ui.window.rememberWindowState

// ─── Entry Point ─────────────────────────────────────────────────────────────

fun main() = application {
    var showSplash by remember { mutableStateOf(true) }
    val windowState = rememberWindowState(placement = WindowPlacement.Floating)

    LaunchedEffect(Unit) {
        delay(3000)
        showSplash = false
        windowState.placement = WindowPlacement.Maximized
    }

    Window(
        onCloseRequest = ::exitApplication,
        state = windowState,
        title = if (showSplash) "Starting Adapt Board..." else "Adapt Board - Project View"
    ) {
        if (showSplash) {
            SplashScreen()
        } else {
            AdaptBoardApp(onQuit = ::exitApplication)
        }
    }
}

// ─── Splash Screen ───────────────────────────────────────────────────────────

@Composable
fun SplashScreen() {
    val infiniteTransition = rememberInfiniteTransition()
    val alpha by infiniteTransition.animateFloat(
        initialValue = 0.2f, targetValue = 1.0f,
        animationSpec = infiniteRepeatable(
            animation = tween(1000, easing = LinearEasing),
            repeatMode = RepeatMode.Reverse
        )
    )
    Box(
        Modifier.fillMaxSize().background(Color(0xFF2B2D30)),
        contentAlignment = Alignment.Center
    ) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Text("Adapt Board", color = AppColors.accent, fontSize = 48.sp,
                fontWeight = FontWeight.Bold, modifier = Modifier.padding(bottom = 16.dp))
            CircularProgressIndicator(
                color = Color.White.copy(alpha = alpha),
                modifier = Modifier.size(48.dp)
            )
        }
    }
}

// ─── App Shell (Navigation + Drawer) ─────────────────────────────────────────

@Composable
fun AdaptBoardApp(onQuit: () -> Unit) {
    var currentPage by remember { mutableStateOf(Page.MAIN) }
    var drawerOpen  by remember { mutableStateOf(false) }
    val simState    = remember { SimulationConfigState() }
    val simManager  = remember { SimulationManager() }
    val rwManager   = remember { RealWorldManager() }
    var appMode     by remember { mutableStateOf(AppMode.SIMULATION) }
    val scope       = rememberCoroutineScope()

    Box(Modifier.fillMaxSize()) {
        when (currentPage) {
            Page.MAIN     -> MainBoardPage(
                onMenuToggle = { drawerOpen = !drawerOpen },
                boardSettings = simState.config.board,
                config = simState.config,
                simManager = simManager,
                rwManager = rwManager,
                appMode = appMode,
                onModeChange = { newMode ->
                    // Stop whichever active mode we're leaving
                    if (newMode != appMode) {
                        if (appMode == AppMode.SIMULATION) simManager.stop()
                        else rwManager.disconnect()
                        appMode = newMode
                    }
                }
            )
            Page.SETTINGS -> SettingsPage(onBack = { currentPage = Page.MAIN }, simState = simState)
            Page.ABOUT    -> AboutPage(onBack = { currentPage = Page.MAIN })
        }

        // Scrim
        if (drawerOpen) {
            Box(
                Modifier.fillMaxSize()
                    .background(Color.Black.copy(alpha = 0.4f))
                    .clickable(
                        indication = null,
                        interactionSource = remember { MutableInteractionSource() }
                    ) { drawerOpen = false }
            )
        }
        // Drawer overlay
        AnimatedVisibility(
            visible = drawerOpen,
            enter = slideInHorizontally { -it } + fadeIn(),
            exit  = slideOutHorizontally { -it } + fadeOut()
        ) {
            DrawerContent(
                onSettings = { drawerOpen = false; currentPage = Page.SETTINGS },
                onAbout    = { drawerOpen = false; currentPage = Page.ABOUT },
                onQuit     = onQuit,
                simManager = simManager,
                scope      = scope
            )
        }
    }
}

// ─── Main Board Page ─────────────────────────────────────────────────────────

@Composable
fun MainBoardPage(
    onMenuToggle: () -> Unit,
    boardSettings: BoardSettings,
    config: SimulationConfig,
    simManager: SimulationManager,
    rwManager: RealWorldManager,
    appMode: AppMode,
    onModeChange: (AppMode) -> Unit
) {
    var canvasSize by remember { mutableStateOf(IntSize.Zero) }
    var lidarState by remember { mutableStateOf(LidarState()) }
    var userHasDragged by remember { mutableStateOf(false) }

    val scope = rememberCoroutineScope()
    var feedbackMessage by remember { mutableStateOf<String?>(null) }

    // ── Tracker: auto-start/stop with simulation ────────────────────
    val trackerParser = remember { TrackerParser() }

    // Clean up tracker when composable leaves
    DisposableEffect(Unit) {
        onDispose { trackerParser.stop() }
    }

    // Derive canvas fractions from user-editable settings.
    // Support (dashed margin) is the visual anchor at a fixed canvas fraction.
    // Board (grey rect) scales proportionally within it.
    val supportWFrac = 0.56f
    val supportHFrac = 0.60f
    val boardWFrac   = if (boardSettings.marginWidth > 0)
        supportWFrac * (boardSettings.boardWidth.toFloat() / boardSettings.marginWidth) else supportWFrac
    val boardHFrac   = if (boardSettings.marginHeight > 0)
        supportHFrac * (boardSettings.boardHeight.toFloat() / boardSettings.marginHeight) else supportHFrac

    val boardConfig   = BoardConfig(widthFraction = boardWFrac, heightFraction = boardHFrac)
    val supportConfig = SupportConfig(widthFraction = supportWFrac, heightFraction = supportHFrac)
    val isSimRunning  = appMode == AppMode.SIMULATION && simManager.status == SimStatus.RUNNING
    val isRwConnected = appMode == AppMode.REAL_WORLD  && rwManager.status == RwStatus.CONNECTED
    val isActive      = isSimRunning || isRwConnected

    // ── Tracker: auto-start/stop with simulation ─────────────────────────────
    // Keyed on lidar position AND board/margin settings so the tracker restarts
    // (with fresh board bounds) whenever the lidar is moved or dimensions change.
    LaunchedEffect(
        simManager.status, rwManager.status, appMode,
        lidarState.x, lidarState.y,
        boardSettings.boardWidth, boardSettings.boardHeight,
        boardSettings.marginWidth, boardSettings.marginHeight
    ) {
        if (isSimRunning) {
            val cw = canvasSize.width.toFloat()
            val ch = canvasSize.height.toFloat()
            val mw = boardSettings.marginWidth.toFloat()
            val mh = boardSettings.marginHeight.toFloat()
            if (cw > 0f && ch > 0f && mw > 0f && mh > 0f) {
                trackerParser.start(config, scope, AppMode.SIMULATION)
            } else {
                trackerParser.start(config, scope, AppMode.SIMULATION)
            }
        } else if (isRwConnected) {
            trackerParser.start(config, scope, AppMode.REAL_WORLD)
        } else {
            trackerParser.stop()
        }
    }

    // Auto-snap Lidar to strictly valid positions based on current constraints or window resize
    LaunchedEffect(config.lidar.placementAxis, canvasSize, supportWFrac, supportHFrac, boardWFrac, boardHFrac) {
        if (canvasSize.width > 100 && canvasSize.height > 100) {
            val biasX = if (lidarState.x < 0f) canvasSize.width / 2f else lidarState.x
            val biasY = if (lidarState.y < 0f) canvasSize.height.toFloat() else lidarState.y
            val (nx, ny) = clampToGap(
                biasX, biasY,
                canvasSize.width.toFloat(), canvasSize.height.toFloat(),
                26f, config.lidar.placementAxis,
                supportWFrac, supportHFrac, boardWFrac, boardHFrac
            )
            if (nx != lidarState.x || ny != lidarState.y) {
                lidarState = lidarState.copy(x = nx, y = ny)
            }
        }
    }

    Row(Modifier.fillMaxSize().background(Color.White).padding(16.dp)) {
        Box(
            Modifier.weight(1f).fillMaxHeight()
                .border(2.dp, AppColors.primary, RoundedCornerShape(12.dp))
                .clip(RoundedCornerShape(12.dp))
                .background(Color.White)
        ) {
            Row(Modifier.fillMaxSize()) {

                // ── Canvas Area ──────────────────────────────────────────
                Box(
                    Modifier.weight(1f).fillMaxHeight()
                        .onGloballyPositioned { coords ->
                            val newSize = coords.size
                            if (canvasSize != newSize) {
                                canvasSize = newSize
                            }
                        }
                ) {
                    // Grid + Support + Board + Ball Overlay
                    Canvas(Modifier.fillMaxSize()) {
                        drawGrid()
                        drawSupport(supportConfig)
                        drawBoard(boardConfig)
                        drawDetectedBalls(
                            balls = trackerParser.detections,
                            lidarState = lidarState,
                            marginWidthM  = boardSettings.marginWidth.toFloat(),
                            marginHeightM = boardSettings.marginHeight.toFloat(),
                            supportWFrac  = supportWFrac,
                            supportHFrac  = supportHFrac
                        )
                    }

                    // Lidar Dot – rendered BEFORE interactive widgets so its
                    // fillMaxSize gesture overlay doesn't steal their clicks.
                    LidarDot(
                        state = lidarState,
                        canvasSize = canvasSize,
                        placementAxis = config.lidar.placementAxis,
                        onMove = { nx, ny ->
                            userHasDragged = true
                            lidarState = lidarState.copy(x = nx, y = ny)
                        },
                        onToggleLock = { lidarState = lidarState.copy(isLocked = !lidarState.isLocked) },
                        supportWFrac = supportWFrac,
                        supportHFrac = supportHFrac,
                        boardWFrac   = boardWFrac,
                        boardHFrac   = boardHFrac
                    )

                    // "A" badge (placed AFTER overlay → gets event priority)
                    Box(
                        Modifier.padding(20.dp).size(52.dp)
                            .background(AppColors.primary, CircleShape)
                            .clickable { onMenuToggle() },
                        contentAlignment = Alignment.Center
                    ) {
                        Text("A", color = Color.White, fontSize = 26.sp, fontWeight = FontWeight.Bold)
                    }
                    
                    // Status Badge (Top End)
                    Box(Modifier.align(Alignment.TopEnd).padding(20.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            // ── Mode Toggle ──────────────────────────────
                            Row(
                                Modifier.background(AppColors.sidebar, RoundedCornerShape(20.dp))
                                    .padding(horizontal = 4.dp, vertical = 2.dp),
                                horizontalArrangement = Arrangement.spacedBy(2.dp),
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                ModeChip(
                                    label = "Sim",
                                    selected = appMode == AppMode.SIMULATION,
                                    onClick = { onModeChange(AppMode.SIMULATION) }
                                )
                                ModeChip(
                                    label = "Real",
                                    selected = appMode == AppMode.REAL_WORLD,
                                    onClick = { onModeChange(AppMode.REAL_WORLD) }
                                )
                            }
                            Spacer(Modifier.width(8.dp))
                            // ── Active status dot ─────────────────────────
                            val dotColor = when {
                                appMode == AppMode.SIMULATION -> when (simManager.status) {
                                    SimStatus.RUNNING   -> Color(0xFF4CAF50)
                                    SimStatus.LAUNCHING -> AppColors.accent
                                    SimStatus.ERROR     -> AppColors.danger
                                    SimStatus.STOPPED   -> Color.Gray
                                }
                                else -> when (rwManager.status) {
                                    RwStatus.CONNECTED    -> Color(0xFF4CAF50)
                                    RwStatus.CONNECTING   -> AppColors.accent
                                    RwStatus.ERROR        -> AppColors.danger
                                    RwStatus.DISCONNECTED -> Color.Gray
                                }
                            }
                            val statusLabel = if (appMode == AppMode.SIMULATION)
                                simManager.status.name else rwManager.status.name
                            Box(Modifier.size(10.dp).background(dotColor, CircleShape))
                            Text(statusLabel, fontSize = 11.sp, color = AppColors.text,
                                fontWeight = FontWeight.SemiBold)
                        }
                    }

                    // Dimension labels
                    Box(Modifier.align(Alignment.Center).offset(y = (-200).dp)) {
                        Text("${boardSettings.boardWidth}", color = AppColors.text, fontSize = 20.sp, fontWeight = FontWeight.Bold)
                    }
                    Box(Modifier.align(Alignment.Center).offset(x = 310.dp)) {
                        Text("${boardSettings.boardHeight}", color = AppColors.text, fontSize = 20.sp, fontWeight = FontWeight.Bold)
                    }

                    // Bottom Buttons
                    Row(
                        Modifier.align(Alignment.BottomCenter).padding(bottom = 24.dp),
                        horizontalArrangement = Arrangement.spacedBy(16.dp)
                    ) {
                        if (appMode == AppMode.REAL_WORLD) {
                            // ── Real-World: Connect / Disconnect LIDAR ────
                            val isConnected = rwManager.status == RwStatus.CONNECTED
                            val isBusy = rwManager.status == RwStatus.CONNECTING
                            ActionButton(
                                iconDraw = { drawLidarIcon(isConnected) },
                                label = if (isConnected) "Disconnect" else "Connect LIDAR",
                                enabled = !isBusy,
                                onClick = {
                                    scope.launch {
                                        if (isConnected) rwManager.disconnect()
                                        else rwManager.connect(scope)
                                    }
                                }
                            )
                            // ── Viz button (only when LIDAR is live) ──────
                            if (isConnected) {
                                ActionButton(
                                    iconDraw = { drawVizIcon(rwManager.isVizRunning) },
                                    label = if (rwManager.isVizRunning) "Stop Viz" else "Launch Viz",
                                    onClick = {
                                        if (rwManager.isVizRunning) rwManager.stopViz()
                                        else rwManager.launchViz()
                                    }
                                )
                            }
                        } else {
                            // ── Simulation: Spawn / Delete buttons ────────
                        // ── Helper to compute world-space bounds from canvas layout ──
                        // (shared by both spawn buttons via a local lambda)

                        ActionButton(
                            iconDraw = { drawRectIcon() },
                            label = "Spawn 1",
                            enabled = isSimRunning,
                            onClick = {
                                scope.launch {
                                    val cw = canvasSize.width.toFloat()
                                    val ch = canvasSize.height.toFloat()
                                    val mw = boardSettings.marginWidth.toFloat()
                                    val mh = boardSettings.marginHeight.toFloat()
                                    val supportWidthPx  = cw * supportWFrac
                                    val supportHeightPx = ch * supportHFrac
                                    val pxPerMeterX = if (mw > 0f) supportWidthPx  / mw else 1f
                                    val pxPerMeterY = if (mh > 0f) supportHeightPx / mh else 1f
                                    val boardHalfPxW  = cw * boardWFrac   / 2f
                                    val boardHalfPxH  = ch * boardHFrac   / 2f
                                    val marginHalfPxW = cw * supportWFrac / 2f
                                    val marginHalfPxH = ch * supportHFrac / 2f
                                    val cx = cw / 2f; val cy = ch / 2f
                                    val centerWorldX =  (cx - lidarState.x) / pxPerMeterX
                                    val centerWorldY = -(cy - lidarState.y) / pxPerMeterY
                                    val boardHalfW = boardHalfPxW / pxPerMeterX
                                    val boardHalfH = boardHalfPxH / pxPerMeterY
                                    val marginHalfW = marginHalfPxW / pxPerMeterX
                                    val marginHalfH = marginHalfPxH / pxPerMeterY
                                    val bx0 = centerWorldX - boardHalfW; val bx1 = centerWorldX + boardHalfW
                                    val by0 = centerWorldY - boardHalfH; val by1 = centerWorldY + boardHalfH
                                    val mx0 = centerWorldX - marginHalfW; val mx1 = centerWorldX + marginHalfW
                                    val my0 = centerWorldY - marginHalfH; val my1 = centerWorldY + marginHalfH
                                    ProcessScope.runAndWait {
                                        RosBridge.spawnSingleBall(
                                            config,
                                            bx0.toDouble(), bx1.toDouble(),
                                            by0.toDouble(), by1.toDouble(),
                                            mx0.toDouble(), mx1.toDouble(),
                                            my0.toDouble(), my1.toDouble()
                                        )
                                    }
                                        .onSuccess { feedbackMessage = "Ball spawned" }
                                        .onFailure { feedbackMessage = "Spawn failed: ${it.message}" }
                                }
                            }
                        )
                        ActionButton(
                            iconDraw = { drawMultiRectIcon() },
                            label = "Spawn 5",
                            enabled = isSimRunning,
                            onClick = {
                                scope.launch {
                                    val cw = canvasSize.width.toFloat()
                                    val ch = canvasSize.height.toFloat()
                                    val mw = boardSettings.marginWidth.toFloat()
                                    val mh = boardSettings.marginHeight.toFloat()
                                    val supportWidthPx  = cw * supportWFrac
                                    val supportHeightPx = ch * supportHFrac
                                    val pxPerMeterX = if (mw > 0f) supportWidthPx  / mw else 1f
                                    val pxPerMeterY = if (mh > 0f) supportHeightPx / mh else 1f
                                    val boardHalfPxW  = cw * boardWFrac   / 2f
                                    val boardHalfPxH  = ch * boardHFrac   / 2f
                                    val marginHalfPxW = cw * supportWFrac / 2f
                                    val marginHalfPxH = ch * supportHFrac / 2f
                                    val cx = cw / 2f; val cy = ch / 2f
                                    val centerWorldX =  (cx - lidarState.x) / pxPerMeterX
                                    val centerWorldY = -(cy - lidarState.y) / pxPerMeterY
                                    val boardHalfW = boardHalfPxW / pxPerMeterX
                                    val boardHalfH = boardHalfPxH / pxPerMeterY
                                    val marginHalfW = marginHalfPxW / pxPerMeterX
                                    val marginHalfH = marginHalfPxH / pxPerMeterY
                                    val bx0 = centerWorldX - boardHalfW; val bx1 = centerWorldX + boardHalfW
                                    val by0 = centerWorldY - boardHalfH; val by1 = centerWorldY + boardHalfH
                                    val mx0 = centerWorldX - marginHalfW; val mx1 = centerWorldX + marginHalfW
                                    val my0 = centerWorldY - marginHalfH; val my1 = centerWorldY + marginHalfH
                                    ProcessScope.runAndWait {
                                        RosBridge.spawnMultipleBalls(
                                            numBalls = 5,
                                            config = config,
                                            bx0.toDouble(), bx1.toDouble(),
                                            by0.toDouble(), by1.toDouble(),
                                            mx0.toDouble(), mx1.toDouble(),
                                            my0.toDouble(), my1.toDouble()
                                        )
                                    }
                                        .onSuccess { feedbackMessage = "5 balls spawned" }
                                        .onFailure { feedbackMessage = "Spawn failed: ${it.message}" }
                                }
                            }
                        )
                        ActionButton(
                            iconDraw = { drawTrashIcon() },
                            label = "Delete 1",
                            enabled = isSimRunning,
                            onClick = {
                                scope.launch {
                                    ProcessScope.runAndWait { RosBridge.removeBalls(1) }
                                        .onSuccess { feedbackMessage = "Ball removed" }
                                        .onFailure { feedbackMessage = "Remove failed: ${it.message}" }
                                }
                            }
                        )
                        ActionButton(
                            iconDraw = { drawTrashAllIcon() },
                            label = "Delete All",
                            enabled = isSimRunning,
                            onClick = {
                                scope.launch {
                                    ProcessScope.runAndWait { RosBridge.removeBalls() }
                                        .onSuccess { feedbackMessage = "All balls removed" }
                                        .onFailure { feedbackMessage = "Remove failed: ${it.message}" }
                                }
                            }
                        )
                        } // end SIMULATION mode buttons
                    } // end Row

                    // Transient feedback message
                    feedbackMessage?.let { msg ->
                        LaunchedEffect(msg) {
                            delay(2000)
                            feedbackMessage = null
                        }
                        Text(
                            msg,
                            color = AppColors.accent,
                            fontSize = 13.sp,
                            modifier = Modifier.align(Alignment.BottomCenter).padding(bottom = 80.dp)
                        )
                    }
                }

                // Right Info Panel (from InfoPanel.kt)
                InfoPanel(
                    lidarState = lidarState,
                    canvasWidth = canvasSize.width.toFloat(),
                    canvasHeight = canvasSize.height.toFloat(),
                    simManager = simManager,
                    detectionCount = trackerParser.detections.size,
                    trackerFrameCount = trackerParser.frameCount,
                    totalBallCount = trackerParser.totalBallCount,
                    appMode = appMode,
                    rwManager = rwManager
                )
            }
        }
    }
}

// ─── Grid Drawing ────────────────────────────────────────────────────────────

private fun DrawScope.drawGrid() {
    val step = 50.dp.toPx()
    for (i in 0..(size.width / step).toInt())
        drawLine(AppColors.grid, Offset(i * step, 0f), Offset(i * step, size.height), 1f)
    for (i in 0..(size.height / step).toInt())
        drawLine(AppColors.grid, Offset(0f, i * step), Offset(size.width, i * step), 1f)
}

// ─── Action Buttons ──────────────────────────────────────────────────────────

@Composable
private fun ActionButton(
    iconDraw: DrawScope.() -> Unit,
    label: String,
    enabled: Boolean = true,
    onClick: () -> Unit = {}
) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Canvas(Modifier.size(22.dp)) { iconDraw() }
        Spacer(Modifier.height(6.dp))
        Button(
            onClick = onClick,
            enabled = enabled,
            colors = ButtonDefaults.buttonColors(backgroundColor = AppColors.primary),
            shape = RoundedCornerShape(16.dp),
            modifier = Modifier.width(110.dp)
        ) { Text(label, color = Color.White, fontSize = 15.sp) }
    }
}

private fun DrawScope.drawRectIcon() {
    drawRect(Color.Gray, Offset(2f, 2f),
        Size(size.width - 4f, size.height - 4f), style = Stroke(3f))
}

private fun DrawScope.drawMultiRectIcon() {
    // Two overlapping small rectangles to represent "multiple"
    val w = size.width; val h = size.height
    drawRect(Color.Gray, Offset(0f, 4f), Size(w * 0.7f, h * 0.7f), style = Stroke(2.5f))
    drawRect(Color.Gray, Offset(w * 0.3f, 0f), Size(w * 0.7f, h * 0.7f), style = Stroke(2.5f))
}

private fun DrawScope.drawTrashIcon() {
    val w = size.width; val h = size.height
    // Body of bin
    drawRect(Color.Gray, Offset(w * 0.15f, h * 0.35f),
        Size(w * 0.7f, h * 0.6f), style = Stroke(2.5f))
    // Lid
    drawLine(Color.Gray, Offset(w * 0.05f, h * 0.3f), Offset(w * 0.95f, h * 0.3f), 2.5f)
    // Handle
    drawLine(Color.Gray, Offset(w * 0.35f, h * 0.15f), Offset(w * 0.65f, h * 0.15f), 2.5f)
    // Vertical lines inside bin
    drawLine(Color.Gray, Offset(w * 0.38f, h * 0.5f), Offset(w * 0.38f, h * 0.82f), 1.5f)
    drawLine(Color.Gray, Offset(w * 0.615f, h * 0.5f), Offset(w * 0.615f, h * 0.82f), 1.5f)
}

private fun DrawScope.drawTrashAllIcon() {
    val w = size.width; val h = size.height
    // Same bin icon with an X over it to indicate "all"
    drawRect(Color.Gray, Offset(w * 0.15f, h * 0.35f),
        Size(w * 0.7f, h * 0.6f), style = Stroke(2.5f))
    drawLine(Color.Gray, Offset(w * 0.05f, h * 0.3f), Offset(w * 0.95f, h * 0.3f), 2.5f)
    drawLine(Color.Gray, Offset(w * 0.35f, h * 0.15f), Offset(w * 0.65f, h * 0.15f), 2.5f)
    // X inside bin
    drawLine(Color(0xFFFF6B6B), Offset(w * 0.25f, h * 0.48f), Offset(w * 0.75f, h * 0.88f), 2f)
    drawLine(Color(0xFFFF6B6B), Offset(w * 0.75f, h * 0.48f), Offset(w * 0.25f, h * 0.88f), 2f)
}

// ─── LIDAR Icon (Connect / Disconnect) ──────────────────────────────────────

private fun DrawScope.drawLidarIcon(connected: Boolean) {
    val w = size.width; val h = size.height
    val color = if (connected) Color(0xFF4CAF50) else Color.Gray
    // Outer arc (scan fan)
    drawArc(color, startAngle = 180f, sweepAngle = 180f, useCenter = false,
        topLeft = Offset(w * 0.1f, h * 0.1f), size = Size(w * 0.8f, h * 0.8f),
        style = Stroke(2.5f))
    // Centre dot (sensor)
    drawCircle(color, radius = 3f, center = Offset(w / 2, h * 0.85f))
    // Small tick mark for "connected"
    if (connected) {
        drawLine(Color(0xFF4CAF50), Offset(w * 0.35f, h * 0.55f), Offset(w * 0.48f, h * 0.70f), 2f)
        drawLine(Color(0xFF4CAF50), Offset(w * 0.48f, h * 0.70f), Offset(w * 0.70f, h * 0.40f), 2f)
    }
}

// ─── Mode Toggle Chip ────────────────────────────────────────────────────────

@Composable
private fun ModeChip(label: String, selected: Boolean, onClick: () -> Unit) {
    Box(
        Modifier
            .background(
                if (selected) AppColors.primary else Color.Transparent,
                RoundedCornerShape(16.dp)
            )
            .clickable(onClick = onClick)
            .padding(horizontal = 10.dp, vertical = 4.dp),
        contentAlignment = Alignment.Center
    ) {
        Text(
            label,
            color = if (selected) Color.White else AppColors.text,
            fontSize = 12.sp,
            fontWeight = if (selected) FontWeight.Bold else FontWeight.Normal
        )
    }
}

// ─── Viz Icon ────────────────────────────────────────────────────────────────

private fun DrawScope.drawVizIcon(running: Boolean) {
    val w = size.width; val h = size.height
    val color = if (running) Color(0xFF4CAF50) else Color.Gray
    // Monitor frame
    drawRect(color, Offset(0f, 0f), Size(w, h * 0.70f), style = Stroke(2.5f))
    // Stand
    drawLine(color, Offset(w / 2, h * 0.70f), Offset(w / 2, h * 0.88f), 2.5f)
    drawLine(color, Offset(w * 0.25f, h * 0.88f), Offset(w * 0.75f, h * 0.88f), 2.5f)
    // Scan line inside monitor when active
    if (running) {
        drawLine(Color(0xFF4CAF50), Offset(w * 0.15f, h * 0.35f), Offset(w * 0.85f, h * 0.35f), 1.5f)
    }
}


