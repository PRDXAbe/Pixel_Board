import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.Divider
import androidx.compose.material.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.withContext

// ─── Info Panel (Right Sidebar) ──────────────────────────────────────────────

/**
 * Right-hand side panel showing system configuration, status, active ROS
 * nodes, and a live log.
 *
 * In SIMULATION mode:  shows Gazebo sim status + sim stdout log.
 * In REAL_WORLD mode:  shows LIDAR device status + LD19 driver stdout log.
 */
@Composable
fun InfoPanel(
    lidarState: LidarState,
    canvasWidth: Float,
    canvasHeight: Float,
    simManager: SimulationManager,
    detectionCount: Int = 0,
    trackerFrameCount: Int = 0,
    totalBallCount: Int = 0,
    appMode: AppMode = AppMode.SIMULATION,
    rwManager: RealWorldManager? = null
) {
    val (wx, wy) = lidarState.worldCoords(canvasWidth, canvasHeight)

    // ── Helpers ──────────────────────────────────────────────────────────────
    val isAnyActive = (appMode == AppMode.SIMULATION && simManager.status == SimStatus.RUNNING) ||
                      (appMode == AppMode.REAL_WORLD  && rwManager?.status == RwStatus.CONNECTED)

    // ── Node health: poll every 5s when active ───────────────────────────────
    var activeNodes by remember { mutableStateOf<List<String>>(emptyList()) }
    var nodeCheckError by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(simManager.status, appMode, rwManager?.status) {
        if (isAnyActive) {
            while (isActive) {
                try {
                    val result = withContext(Dispatchers.IO) {
                        val proc = ProcessBuilder(
                            "bash", "-c",
                            "source /home/abhinav/Projects/Magic_Board/big_boulder/install/setup.bash" +
                            " && ros2 node list 2>/dev/null"
                        ).start()
                        val output = proc.inputStream.bufferedReader().readText()
                        proc.waitFor()
                        output
                    }
                    activeNodes = result.lines()
                        .map { it.trim() }
                        .filter { it.startsWith("/") }
                    nodeCheckError = null
                } catch (e: Exception) {
                    nodeCheckError = e.message
                    activeNodes = emptyList()
                }
                delay(5000)
            }
        } else {
            activeNodes = emptyList()
            nodeCheckError = null
        }
    }

    // ── Log lines: sim stdout or LIDAR driver stdout depending on mode ────────
    var logLines by remember { mutableStateOf<List<String>>(emptyList()) }

    LaunchedEffect(simManager.status, appMode, rwManager?.status) {
        logLines = emptyList()
        val stream = when {
            appMode == AppMode.SIMULATION && simManager.status == SimStatus.RUNNING ->
                simManager.getProcessInputStream()
            appMode == AppMode.REAL_WORLD && rwManager?.status == RwStatus.CONNECTED ->
                rwManager.getInputStream()
            else -> null
        }
        if (stream != null) {
            withContext(Dispatchers.IO) {
                try {
                    stream.bufferedReader().forEachLine { line ->
                        if (!isActive) return@forEachLine
                        logLines = (logLines + line).takeLast(50)
                    }
                } catch (_: Exception) { /* process ended */ }
            }
        }
    }

    // ─────────────────────────────────────────────────────────────────────────

    Column(
        Modifier
            .fillMaxHeight()
            .width(280.dp)
            .background(AppColors.sidebar)
            .padding(20.dp)
    ) {
        Text("SYSTEM", color = AppColors.text, fontSize = 17.sp, fontWeight = FontWeight.Bold)
        Text(
            "CONFIGURATION", color = AppColors.text, fontSize = 17.sp,
            fontWeight = FontWeight.Bold, modifier = Modifier.padding(bottom = 20.dp)
        )
        Divider(color = AppColors.grid, modifier = Modifier.padding(bottom = 16.dp))

        // ── Status row — adapts to app mode ──────────────────────────────────
        if (appMode == AppMode.REAL_WORLD && rwManager != null) {
            InfoLabel("LIDAR Device")
            Row(
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier.padding(bottom = 4.dp)
            ) {
                Box(
                    Modifier.size(8.dp).background(
                        when (rwManager.status) {
                            RwStatus.CONNECTED    -> Color(0xFF4CAF50)
                            RwStatus.CONNECTING   -> AppColors.accent
                            RwStatus.ERROR        -> AppColors.danger
                            RwStatus.DISCONNECTED -> Color.Gray
                        }, CircleShape
                    )
                )
                Spacer(Modifier.width(8.dp))
                Text(rwManager.status.name, color = AppColors.text, fontSize = 14.sp)
            }
            rwManager.errorMessage?.let { err ->
                Text(
                    err.take(120), color = AppColors.danger, fontSize = 11.sp,
                    modifier = Modifier.padding(bottom = 8.dp)
                )
            }
        } else {
            InfoLabel("Simulation")
            Row(
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier.padding(bottom = 4.dp)
            ) {
                Box(
                    Modifier.size(8.dp).background(
                        when (simManager.status) {
                            SimStatus.RUNNING   -> Color(0xFF4CAF50)
                            SimStatus.LAUNCHING -> AppColors.accent
                            SimStatus.ERROR     -> AppColors.danger
                            SimStatus.STOPPED   -> Color.Gray
                        }, CircleShape
                    )
                )
                Spacer(Modifier.width(8.dp))
                Text(simManager.status.name, color = AppColors.text, fontSize = 14.sp)
            }
            simManager.errorMessage?.let { err ->
                Text(
                    err.take(120), color = AppColors.danger, fontSize = 11.sp,
                    modifier = Modifier.padding(bottom = 8.dp)
                )
            }
        }

        Spacer(Modifier.height(8.dp))
        Divider(color = AppColors.grid, modifier = Modifier.padding(bottom = 16.dp))

        // ── Sensor Coordinates ────────────────────────────────────────────────
        InfoLabel("Sensor Coordinates")
        Text(
            "(X: ${"%.1f".format(wx)}, Y: ${"%.1f".format(wy)})",
            color = AppColors.text, fontSize = 14.sp,
            modifier = Modifier.padding(bottom = 8.dp)
        )
        InfoLabel("Lidar Range")
        Text(
            "${lidarState.range} m", color = AppColors.text, fontSize = 14.sp,
            modifier = Modifier.padding(bottom = 8.dp)
        )
        InfoLabel("Status")
        Text(
            if (lidarState.isLocked) "Locked" else "Free",
            color = if (lidarState.isLocked) AppColors.danger else AppColors.accent,
            fontSize = 14.sp, modifier = Modifier.padding(bottom = 8.dp)
        )
        Divider(color = AppColors.grid, modifier = Modifier.padding(bottom = 16.dp))

        // ── Active ROS Nodes ──────────────────────────────────────────────────
        InfoLabel("Active Nodes (${activeNodes.size})")
        if (activeNodes.isEmpty() && isAnyActive) {
            Text(
                "Scanning…", color = Color.Gray, fontSize = 12.sp,
                modifier = Modifier.padding(bottom = 8.dp)
            )
        }
        nodeCheckError?.let {
            Text("Error: $it", color = AppColors.danger, fontSize = 11.sp,
                modifier = Modifier.padding(bottom = 8.dp))
        }
        for (node in activeNodes.take(10)) {
            Text(node, color = AppColors.text, fontSize = 11.sp, fontFamily = FontFamily.Monospace)
        }
        if (activeNodes.size > 10) {
            Text("… +${activeNodes.size - 10} more", color = Color.Gray, fontSize = 11.sp)
        }
        Spacer(Modifier.height(8.dp))
        Divider(color = AppColors.grid, modifier = Modifier.padding(bottom = 12.dp))

        // ── Elevation View (Front-facing) ─────────────────────────────────────
        InfoLabel("Elevation View (Front)")
        Box(
            Modifier
                .fillMaxWidth().height(80.dp)
                .background(Color(0xFFF5F5F5), RoundedCornerShape(6.dp))
                .padding(8.dp)
        ) {
            Canvas(Modifier.fillMaxSize()) {
                val lidarY  = size.height * 0.15f
                val supportY = size.height * 0.3f
                val boardY  = size.height * 0.6f
                val groundY = size.height * 0.9f
                drawCircle(Color.Black, radius = 4f, center = Offset(size.width / 2, lidarY))
                drawLine(AppColors.grid, Offset(size.width/2, lidarY), Offset(size.width/2, supportY), strokeWidth = 1.5f)
                drawLine(AppColors.dashedLine, Offset(size.width*0.3f, supportY), Offset(size.width*0.7f, supportY), strokeWidth = 2f)
                drawRect(AppColors.solidRect, Offset(size.width*0.2f, boardY), Size(size.width*0.6f, 8f))
                drawLine(AppColors.text, Offset(0f, groundY), Offset(size.width, groundY), strokeWidth = 1f)
                drawArc(Color(0x3388FF88), startAngle = 180f, sweepAngle = 180f,
                    useCenter = false, topLeft = Offset(size.width*0.25f, lidarY),
                    size = Size(size.width*0.5f, size.width*0.5f), style = Stroke(2f))
            }
        }
        Spacer(Modifier.height(8.dp))
        Divider(color = AppColors.grid, modifier = Modifier.padding(bottom = 12.dp))

        // ── Ball Detection ────────────────────────────────────────────────────
        InfoLabel("Ball Detection")
        Text(
            "Total counted: $totalBallCount", color = AppColors.accent, fontSize = 14.sp,
            fontWeight = FontWeight.Bold, modifier = Modifier.padding(bottom = 4.dp)
        )
        Text(
            "Currently visible: $detectionCount", color = AppColors.text, fontSize = 13.sp,
            modifier = Modifier.padding(bottom = 4.dp)
        )
        Text(
            "Scan frames: $trackerFrameCount", color = Color.Gray, fontSize = 11.sp,
            modifier = Modifier.padding(bottom = 8.dp)
        )
        Divider(color = AppColors.grid, modifier = Modifier.padding(bottom = 12.dp))

        // ── Log panel ─────────────────────────────────────────────────────────
        InfoLabel(if (appMode == AppMode.REAL_WORLD) "LIDAR Log" else "Sim Log")
        Box(
            Modifier
                .fillMaxWidth()
                .weight(1f)
                .background(Color(0xFF1E1E1E), RoundedCornerShape(6.dp))
                .padding(8.dp)
        ) {
            if (logLines.isEmpty()) {
                Text(
                    if (isAnyActive) "Waiting for output…" else "Not running",
                    color = Color.Gray, fontSize = 11.sp
                )
            } else {
                val scrollState = rememberScrollState()
                LaunchedEffect(logLines.size) {
                    scrollState.animateScrollTo(scrollState.maxValue)
                }
                Column(Modifier.verticalScroll(scrollState)) {
                    for (line in logLines) {
                        Text(
                            line, color = Color(0xFFCCCCCC), fontSize = 10.sp,
                            fontFamily = FontFamily.Monospace, maxLines = 1
                        )
                    }
                }
            }
        }
    }
}

// ── Reusable label ───────────────────────────────────────────────────────────

@Composable
private fun InfoLabel(text: String) {
    Text(
        text, color = AppColors.text, fontWeight = FontWeight.SemiBold, fontSize = 13.sp,
        modifier = Modifier.padding(bottom = 4.dp)
    )
}
