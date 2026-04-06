import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

// ─── Settings Page ───────────────────────────────────────────────────────────

@Composable
fun SettingsPage(
    onBack: () -> Unit,
    simState: SimulationConfigState
) {
    val cfg = simState.config
    val scope = rememberCoroutineScope()
    var isSaving   by remember { mutableStateOf(false) }
    val scaffoldState = rememberScaffoldState()

    Scaffold(
        scaffoldState = scaffoldState,
        topBar = {
            TopAppBar(
                backgroundColor = AppColors.primary,
                title = { Text("Settings", color = Color.White) },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.Default.ArrowBack, "Back", tint = Color.White)
                    }
                }
            )
        },
        backgroundColor = Color.White
    ) { padding ->
        Column(
            Modifier
                .fillMaxSize()
                .padding(padding)
                .verticalScroll(rememberScrollState())
                .padding(32.dp)
        ) {
            // ── Ball ─────────────────────────────────────────────────────
            SectionTitle("Ball")

            IntSettingsField(
                title       = "Ball Radius",
                description = "The radius of simulated balls that will be thrown onto the board",
                value       = cfg.ball.radius,
                onValueChange = { simState.setBallRadius(it) }
            )
            IntSettingsField(
                title       = "Ball Mass",
                description = "The mass of each simulated ball that will be thrown on board",
                value       = cfg.ball.mass,
                onValueChange = { simState.setBallMass(it) }
            )
            IntSettingsField(
                title       = "Throw Distance",
                description = "The distance from which each simulated ball will be thrown on board",
                value       = cfg.ball.throwDist,
                onValueChange = { simState.setBallThrowDist(it) }
            )

            Spacer(Modifier.height(28.dp))

            // ── Board ────────────────────────────────────────────────────
            SectionTitle("Board")

            IntSettingsField(
                title       = "Board Width",
                description = "The width of the actual board used in meters",
                value       = cfg.board.boardWidth,
                onValueChange = { simState.setBoardWidth(it) }
            )
            IntSettingsField(
                title       = "Board Height",
                description = "The height of the actual board used in meters",
                value       = cfg.board.boardHeight,
                onValueChange = { simState.setBoardHeight(it) }
            )
            IntSettingsField(
                title       = "Margin Width",
                description = "The width of the dashed imaginary margin in meters",
                value       = cfg.board.marginWidth,
                onValueChange = { simState.setMarginWidth(it) }
            )
            IntSettingsField(
                title       = "Margin Height",
                description = "The height of the dashed imaginary margin in meters",
                value       = cfg.board.marginHeight,
                onValueChange = { simState.setMarginHeight(it) }
            )

            Spacer(Modifier.height(28.dp))

            // ── Lidar ────────────────────────────────────────────────────
            SectionTitle("Lidar")

            IntSettingsField(
                title       = "Scan Frequency",
                description = "The frequency at which we scan each object (Hz)",
                value       = cfg.lidar.scanFrequency,
                onValueChange = { simState.setScanFrequency(it) }
            )
            IntSettingsField(
                title       = "Max Range",
                description = "The range we will scan the lidar with",
                value       = cfg.lidar.maxRange,
                onValueChange = { simState.setMaxRange(it) }
            )
            IntSettingsField(
                title       = "Scan Counts",
                description = "Number of points detected to confirm single vs. multiple balls",
                value       = cfg.lidar.scanCounts,
                onValueChange = { simState.setScanCounts(it) }
            )
            IntSettingsField(
                title       = "Scan Closeness",
                description = "Distance between scans to determine if a scan is unique or not",
                value       = cfg.lidar.scanCloseness,
                onValueChange = { simState.setScanCloseness(it) }
            )
            IntSettingsField(
                title       = "Scan Hide Angle",
                description = "Angle of scan hidden to avoid detecting floor, wall, etc.",
                value       = cfg.lidar.scanHideAngle,
                onValueChange = { simState.setScanHideAngle(it) }
            )

            Spacer(Modifier.height(16.dp))
            PlacementAxisField(
                title = "Placement Axis",
                description = "Restrict lidar movement to Vertical (Top/Bottom) or Horizontal (Left/Right) gaps.",
                current = cfg.lidar.placementAxis,
                onSelected = { simState.setLidarPlacementAxis(it) }
            )

            Spacer(Modifier.height(32.dp))

            // ── Save Settings Button ─────────────────────────────────────
            Button(
                onClick = {
                    if (isSaving) return@Button
                    isSaving = true
                    scope.launch {
                        val result = saveSettings(simState)
                        isSaving = false
                        val message = when (result) {
                            is SaveResult.Success          -> "Settings saved."
                            is SaveResult.SuccessWithRebuild -> "Settings saved. Package rebuilt successfully."
                            is SaveResult.Error            -> "Build failed: ${result.message}"
                        }
                        scaffoldState.snackbarHostState.showSnackbar(message)
                    }
                },
                enabled = !isSaving,
                colors = ButtonDefaults.buttonColors(backgroundColor = AppColors.primary),
                shape = RoundedCornerShape(12.dp),
                modifier = Modifier.fillMaxWidth().height(50.dp)
            ) {
                Text(
                    if (isSaving) "Saving…" else "Save Settings",
                    color = Color.White, fontSize = 16.sp, fontWeight = FontWeight.SemiBold
                )
            }

            Spacer(Modifier.height(16.dp))
        }
}
}

// ─── Save Logic ──────────────────────────────────────────────────────────────

suspend fun saveSettings(simState: SimulationConfigState): SaveResult = withContext(Dispatchers.IO) {
    if (!simState.needsRebuild()) {
        simState.markSaved()
        return@withContext SaveResult.Success
    }

    // Needs rebuild
    try {
        val process = RosBridge.buildPackage()
        val stdout = StringBuilder()
        val stderr = StringBuilder()
        val t1 = Thread { stdout.append(process.inputStream.bufferedReader().readText()) }
        val t2 = Thread { stderr.append(process.errorStream.bufferedReader().readText()) }
        t1.start(); t2.start()
        t1.join(); t2.join()
        val exitCode = process.waitFor()
        if (exitCode == 0) {
            simState.markSaved()
            SaveResult.SuccessWithRebuild
        } else {
            SaveResult.Error("Exit $exitCode: ${stderr.toString().take(300)}")
        }
    } catch (e: Exception) {
        SaveResult.Error(e.message ?: "Unknown error")
    }
}

// ─── Section Title ───────────────────────────────────────────────────────────

@Composable
private fun SectionTitle(text: String) {
    Text(
        text,
        fontSize = 20.sp,
        fontWeight = FontWeight.Bold,
        color = AppColors.primary,
        modifier = Modifier.padding(bottom = 16.dp)
    )
}

// ─── Editable Settings Field (t1 – positive integer) ─────────────────────────

@Composable
private fun IntSettingsField(
    title:         String,
    description:   String,
    value:         Int,
    onValueChange: (Int) -> Unit
) {
    var textValue by remember(value) { mutableStateOf(value.toString()) }

    Card(
        modifier = Modifier.fillMaxWidth().padding(bottom = 12.dp),
        elevation = 2.dp,
        shape = RoundedCornerShape(8.dp)
    ) {
        Row(
            Modifier.padding(20.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column(Modifier.weight(1f).padding(end = 16.dp)) {
                Text(title, fontWeight = FontWeight.SemiBold, fontSize = 16.sp, color = AppColors.text)
                Text(description, fontSize = 12.sp, color = Color.Gray)
            }

            OutlinedTextField(
                value = textValue,
                onValueChange = { raw ->
                    // Accept only digits (t1 = positive integer 0..∞)
                    val cleaned = raw.filter { it.isDigit() }
                    textValue = cleaned
                    cleaned.toIntOrNull()?.let { onValueChange(it) }
                },
                singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                modifier = Modifier.width(90.dp),
                colors = TextFieldDefaults.outlinedTextFieldColors(
                    focusedBorderColor  = AppColors.accent,
                    cursorColor         = AppColors.accent,
                    unfocusedBorderColor = AppColors.grid
                )
            )
        }
    }
}

// ─── Placement Axis Selector ─────────────────────────────────────────────────

@Composable
private fun PlacementAxisField(
    title: String,
    description: String,
    current: LidarPlacementAxis,
    onSelected: (LidarPlacementAxis) -> Unit
) {
    Card(
        modifier = Modifier.fillMaxWidth().padding(bottom = 12.dp),
        elevation = 2.dp,
        shape = RoundedCornerShape(8.dp)
    ) {
        Column(Modifier.padding(20.dp)) {
            Text(title, fontWeight = FontWeight.SemiBold, fontSize = 16.sp, color = AppColors.text)
            Text(description, fontSize = 12.sp, color = Color.Gray, modifier = Modifier.padding(bottom = 12.dp))

            Row(horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                LidarPlacementAxis.values().forEach { axis ->
                    val selected = current == axis
                    Button(
                        onClick = { onSelected(axis) },
                        colors = ButtonDefaults.buttonColors(
                            backgroundColor = if (selected) AppColors.primary else Color.LightGray,
                            contentColor = if (selected) Color.White else Color.DarkGray
                        ),
                        shape = RoundedCornerShape(8.dp),
                        modifier = Modifier.weight(1f).height(40.dp)
                    ) {
                        Text(
                            text = axis.name.lowercase().replaceFirstChar { it.uppercase() },
                            fontWeight = if (selected) FontWeight.Bold else FontWeight.Normal
                        )
                    }
                }
            }
        }
    }
}
