package com.pixelboard.ui

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Save
import androidx.compose.material.icons.filled.Stop
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.Alignment
import com.pixelboard.AppUiState
import com.pixelboard.AppViewModel
import com.pixelboard.DisplayTarget
import com.pixelboard.LidarModel
import com.pixelboard.MountMode
import java.io.File

@Composable
fun ControlPanel(
    state:     AppUiState,
    viewModel: AppViewModel,
    modifier:  Modifier = Modifier,
) {
    Column(
        modifier = modifier
            .fillMaxHeight()
            .background(SurfaceBase)
            .padding(16.dp),
    ) {
        Column(
            modifier = Modifier
                .weight(1f)
                .fillMaxWidth()
                .verticalScroll(rememberScrollState()),
        ) {
        // ── Section: Driver control ───────────────────────────────────────────
        SectionLabel("DRIVER")
        Spacer(Modifier.height(8.dp))

        LidarModelSelector(
            selected  = state.boardConfig.lidarModel,
            enabled   = !state.isDriverRunning,
            onSelect  = { viewModel.setLidarModel(it) },
        )

        Spacer(Modifier.height(8.dp))

        StartStopButton(
            isRunning = state.isDriverRunning,
            onStart   = { viewModel.start() },
            onStop    = { viewModel.stop() },
        )

        Spacer(Modifier.height(6.dp))

        val (chipColor, chipText) = when {
            state.isConnected     -> AccentGreen  to "● Live"
            state.isDriverRunning -> AccentYellow to "◌ Initialising"
            else                  -> TextMuted    to "○ Stopped"
        }
        Text(
            text       = chipText,
            fontSize   = 11.sp,
            color      = chipColor,
            fontFamily = FontFamily.Monospace,
            modifier   = Modifier.align(Alignment.CenterHorizontally),
        )

        PanelDivider()

        // ── Section: Board dimensions ─────────────────────────────────────────
        SectionLabel("BOARD DIMENSIONS")
        Spacer(Modifier.height(4.dp))
        Text(
            text     = "Physical size of your board in mm.\nThis defines both the scan boundary\nand the pixel coordinate range.",
            fontSize = 10.sp,
            color    = TextMuted,
            lineHeight = 15.sp,
        )
        Spacer(Modifier.height(10.dp))

        BoardDimensionEditor(
            currentWidthMm  = state.boardConfig.widthMm,
            currentHeightMm = state.boardConfig.heightMm,
            onSave          = { w, h -> viewModel.saveBoardConfig(w, h) },
        )

        if (
            state.isDriverRunning &&
            (
                state.frame.boardWidthMm != state.boardConfig.widthMm ||
                state.frame.boardHeightMm != state.boardConfig.heightMm
            )
        ) {
            Spacer(Modifier.height(8.dp))
            Text(
                text = "Live scan is still using ${state.frame.boardWidthMm}×${state.frame.boardHeightMm} mm. Restart the driver to apply the saved board size.",
                fontSize = 9.sp,
                color = AccentYellow,
                lineHeight = 14.sp,
            )
        }

        PanelDivider()

        // ── Section: Mount + persisted geometry ──────────────────────────────
        SectionLabel("MOUNT")
        Spacer(Modifier.height(4.dp))
        Text(
            text = "Saved to board_config.json and applied on the next driver start.",
            fontSize = 10.sp,
            color = TextMuted,
            lineHeight = 15.sp,
        )
        Spacer(Modifier.height(10.dp))

        MountModeSelector(
            selected = state.boardConfig.mountMode,
            enabled = !state.isDriverRunning,
            onSelect = { viewModel.setMountMode(it) },
        )

        Spacer(Modifier.height(10.dp))

        val geometry = state.boardConfig.geometry
        InfoRow("Saved mount", mountModeLabel(state.boardConfig.mountModeKey))
        InfoRow("Saved X", "[%.3f … %.3f] m".format(geometry.minX, geometry.maxX))
        InfoRow("Saved Y", "[%.3f … %.3f] m".format(geometry.minY, geometry.maxY))

        if (state.isDriverRunning && !state.frame.mountMode.equals(state.boardConfig.mountModeKey, ignoreCase = true)) {
            Spacer(Modifier.height(6.dp))
            Text(
                text = "Live scan is still using ${mountModeLabel(state.frame.mountMode)}. Restart the driver to apply the saved mount.",
                fontSize = 9.sp,
                color = AccentYellow,
                lineHeight = 14.sp,
            )
        }

        PanelDivider()

        // ── Section: Live board info from scan ────────────────────────────────
        val frame = state.frame
        if (frame.boardMaxX > frame.boardMinX) {
            SectionLabel("LIDAR BOUNDARY")
            Spacer(Modifier.height(6.dp))
            InfoRow("X range", "[%.3f … %.3f] m".format(frame.boardMinX, frame.boardMaxX))
            InfoRow("Y range", "[%.3f … %.3f] m".format(frame.boardMinY, frame.boardMaxY))
            PanelDivider()
        }

        SectionLabel("RUN CAPTURE")
        Spacer(Modifier.height(6.dp))
        InfoRow("Saved points", "${state.runCaptureCount}")
        InfoRow("Live touches", "${state.frame.touches.size}")
        Spacer(Modifier.height(8.dp))

        val canSaveRunCapture = state.runCaptureCount > 0 || state.frame.touches.isNotEmpty()

        Button(
            onClick = { viewModel.saveRunCapture() },
            enabled = canSaveRunCapture,
            modifier = Modifier.fillMaxWidth().height(36.dp),
            shape = RoundedCornerShape(8.dp),
            colors = ButtonDefaults.buttonColors(
                containerColor = if (canSaveRunCapture) AccentCyan else TextMuted,
                contentColor = Color.Black,
                disabledContainerColor = TextMuted,
                disabledContentColor = Color.Black.copy(alpha = 0.5f),
            ),
        ) {
            Icon(Icons.Filled.Save, contentDescription = null, modifier = Modifier.size(14.dp))
            Spacer(Modifier.width(4.dp))
            Text("Save run points", fontSize = 11.sp, fontWeight = FontWeight.SemiBold)
        }

        if (!canSaveRunCapture) {
            Spacer(Modifier.height(6.dp))
            Text(
                text = "A new run starts when you start the driver. Registered touch points will be recorded for this run.",
                fontSize = 9.sp,
                color = TextMuted,
                lineHeight = 14.sp,
            )
        } else {
            Spacer(Modifier.height(6.dp))
            Text(
                text = "Each touch lifecycle is saved once, on release. Saving during an active touch includes its latest stabilized point.",
                fontSize = 9.sp,
                color = TextMuted,
                lineHeight = 14.sp,
            )
        }

        state.lastSavedRunPath?.let { path ->
            Spacer(Modifier.height(8.dp))
            Text(
                text = "Saved: ${File(path).name}",
                fontSize = 9.sp,
                color = AccentGreen,
                lineHeight = 14.sp,
            )
            Text(
                text = path,
                fontSize = 9.sp,
                color = TextMuted,
                lineHeight = 14.sp,
                fontFamily = FontFamily.Monospace,
            )
        }

        PanelDivider()

        SectionLabel("INTERACTION")
        Spacer(Modifier.height(4.dp))
        Text(
            text = "Project your screen onto the board, then map the detected board touch onto a selected display. X11 only in this version.",
            fontSize = 10.sp,
            color = TextMuted,
            lineHeight = 15.sp,
        )
        Spacer(Modifier.height(10.dp))

        InteractiveModeToggle(
            enabled = state.availableDisplays.isNotEmpty(),
            checked = state.interactiveModeEnabled,
            onCheckedChange = { viewModel.setInteractiveModeEnabled(it) },
        )

        Spacer(Modifier.height(10.dp))

        DisplaySelector(
            displays = state.availableDisplays,
            selectedDisplayId = state.selectedDisplayId,
            enabled = state.availableDisplays.isNotEmpty(),
            onSelect = { viewModel.selectDisplay(it) },
        )

        Spacer(Modifier.height(10.dp))
        val standardWidth = state.boardConfig.standardScreenWidthPx
        val standardHeight = state.boardConfig.standardScreenHeightPx
        InfoRow(
            "Standard screen",
            if (standardWidth != null && standardHeight != null) {
                "${standardWidth}x${standardHeight}"
            } else {
                "Not set"
            },
        )
        Spacer(Modifier.height(6.dp))
        InfoRow(
            "Pointer",
            state.activeInteractiveTouchId?.let { "Touch #$it" } ?: "Idle",
        )
        Spacer(Modifier.height(6.dp))
        Text(
            text = state.desktopInjectionMessage ?: "Projected interaction is unavailable.",
            fontSize = 9.sp,
            color = if (state.desktopInjectionAvailable) TextMuted else AccentYellow,
            lineHeight = 14.sp,
        )
        }

        Spacer(Modifier.height(12.dp))

        // ── Footer ────────────────────────────────────────────────────────────
        val model = state.boardConfig.lidarModel
        Text(
            text       = "${model.displayName} · /dev/ttyUSB0 · ${model.baudRate}",
            fontSize   = 10.sp,
            color      = TextMuted,
            fontFamily = FontFamily.Monospace,
        )
    }
}

@Composable
private fun InteractiveModeToggle(
    enabled: Boolean,
    checked: Boolean,
    onCheckedChange: (Boolean) -> Unit,
) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        Column(modifier = Modifier.weight(1f)) {
            Text(
                text = "Interactive Mode",
                fontSize = 12.sp,
                color = TextPrimary,
                fontWeight = FontWeight.SemiBold,
            )
            Spacer(Modifier.height(2.dp))
            Text(
                text = if (checked) {
                    "Board touch drives single click, double click, drag, and hold."
                } else {
                    "Desktop injection is armed only when this is enabled."
                },
                fontSize = 9.sp,
                color = TextMuted,
                lineHeight = 14.sp,
            )
        }
        Spacer(Modifier.width(10.dp))
        Switch(
            checked = checked,
            onCheckedChange = onCheckedChange,
            enabled = enabled,
            colors = SwitchDefaults.colors(
                checkedThumbColor = Color.Black,
                checkedTrackColor = AccentCyan,
                uncheckedThumbColor = TextSecondary,
                uncheckedTrackColor = SurfaceElevated,
            ),
        )
    }
}

@Composable
private fun DisplaySelector(
    displays: List<DisplayTarget>,
    selectedDisplayId: String?,
    enabled: Boolean,
    onSelect: (String) -> Unit,
) {
    var expanded by remember(selectedDisplayId, displays) { mutableStateOf(false) }
    val selectedDisplay = displays.firstOrNull { it.id == selectedDisplayId }

    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text(
            text = "Target display",
            fontSize = 11.sp,
            color = TextMuted,
            fontFamily = FontFamily.Monospace,
        )

        Box(modifier = Modifier.fillMaxWidth()) {
            OutlinedButton(
                onClick = { expanded = true },
                enabled = enabled,
                modifier = Modifier.fillMaxWidth().height(36.dp),
                shape = RoundedCornerShape(8.dp),
                border = BorderStroke(1.dp, if (enabled) BorderSubtle else BorderSubtle.copy(alpha = 0.4f)),
                colors = ButtonDefaults.outlinedButtonColors(
                    containerColor = SurfaceElevated,
                    contentColor = TextSecondary,
                    disabledContainerColor = SurfaceElevated,
                    disabledContentColor = TextMuted,
                ),
            ) {
                Text(
                    text = selectedDisplay?.label ?: "No display detected",
                    fontSize = 10.sp,
                    fontFamily = FontFamily.Monospace,
                    maxLines = 1,
                )
            }

            DropdownMenu(
                expanded = expanded,
                onDismissRequest = { expanded = false },
                modifier = Modifier.fillMaxWidth(0.95f).background(SurfaceElevated),
            ) {
                displays.forEach { display ->
                    DropdownMenuItem(
                        text = {
                            Text(
                                text = display.label,
                                fontSize = 10.sp,
                                fontFamily = FontFamily.Monospace,
                            )
                        },
                        onClick = {
                            expanded = false
                            onSelect(display.id)
                        },
                    )
                }
            }
        }
    }
}

// ── Sub-composables ────────────────────────────────────────────────────────────

@Composable
private fun LidarModelSelector(
    selected: LidarModel,
    enabled:  Boolean,
    onSelect: (LidarModel) -> Unit,
) {
    Row(
        modifier              = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        LidarModel.entries.forEach { model ->
            val isSelected = model == selected
            Button(
                onClick  = { onSelect(model) },
                enabled  = enabled,
                modifier = Modifier.weight(1f).height(34.dp),
                shape    = RoundedCornerShape(8.dp),
                colors   = ButtonDefaults.buttonColors(
                    containerColor         = if (isSelected) AccentCyan       else SurfaceElevated,
                    contentColor           = if (isSelected) Color.Black      else TextSecondary,
                    disabledContainerColor = if (isSelected) AccentCyan.copy(alpha = 0.35f) else SurfaceElevated,
                    disabledContentColor   = if (isSelected) Color.Black.copy(alpha = 0.45f) else TextMuted,
                ),
            ) {
                Text(
                    text       = model.displayName,
                    fontSize   = 12.sp,
                    fontWeight = FontWeight.SemiBold,
                    fontFamily = FontFamily.Monospace,
                )
            }
        }
    }
    if (!enabled) {
        Spacer(Modifier.height(2.dp))
        Text(
            text     = "Stop driver to switch model",
            fontSize = 9.sp,
            color    = TextMuted,
        )
    }
}

@Composable
private fun MountModeSelector(
    selected: MountMode,
    enabled: Boolean,
    onSelect: (MountMode) -> Unit,
) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        MountMode.entries
            .filter { it.uiSelectable }
            .forEach { mode ->
                val isSelected = mode == selected
                OutlinedButton(
                    onClick = { onSelect(mode) },
                    enabled = enabled,
                    modifier = Modifier.weight(1f).height(34.dp),
                    shape = RoundedCornerShape(8.dp),
                    border = BorderStroke(1.dp, if (isSelected) AccentCyan else BorderSubtle),
                    colors = ButtonDefaults.outlinedButtonColors(
                        containerColor = if (isSelected) AccentCyan.copy(alpha = 0.14f) else SurfaceElevated,
                        contentColor = if (isSelected) AccentCyan else TextSecondary,
                        disabledContainerColor = SurfaceElevated,
                        disabledContentColor = TextMuted,
                    ),
                ) {
                    Text(
                        text = mode.displayName,
                        fontSize = 11.sp,
                        fontWeight = FontWeight.SemiBold,
                        fontFamily = FontFamily.Monospace,
                    )
                }
            }
    }
    if (!enabled) {
        Spacer(Modifier.height(2.dp))
        Text(
            text = "Stop driver to switch mount",
            fontSize = 9.sp,
            color = TextMuted,
        )
    }
}

@Composable
private fun BoardDimensionEditor(
    currentWidthMm:  Int,
    currentHeightMm: Int,
    onSave: (Int, Int) -> Unit,
) {
    var widthText  by remember(currentWidthMm)  { mutableStateOf(currentWidthMm.toString())  }
    var heightText by remember(currentHeightMm) { mutableStateOf(currentHeightMm.toString()) }
    var hasError   by remember { mutableStateOf(false) }

    val widthInt  = widthText.toIntOrNull()
    val heightInt = heightText.toIntOrNull()
    val valid = widthInt != null && heightInt != null && widthInt > 0 && heightInt > 0
    val hasPendingChanges = widthText != currentWidthMm.toString() || heightText != currentHeightMm.toString()

    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        // Width field
        DimTextField(
            label    = "Width (mm)",
            value    = widthText,
            onValue  = { widthText = it; hasError = false },
            isError  = hasError && widthInt == null,
        )

        // Height field
        DimTextField(
            label    = "Height (mm)",
            value    = heightText,
            onValue  = { heightText = it; hasError = false },
            isError  = hasError && heightInt == null,
        )

        // Preview line
        if (valid) {
            Text(
                text      = if (hasPendingChanges) {
                    "Pending pixel range: (0,0) → ($widthInt, $heightInt)"
                } else {
                    "Pixel range: (0,0) → ($widthInt, $heightInt)"
                },
                fontSize  = 10.sp,
                color     = if (hasPendingChanges) AccentYellow else AccentCyan.copy(alpha = 0.8f),
                fontFamily = FontFamily.Monospace,
            )
        }

        if (hasPendingChanges) {
            Text(
                text = "Fields edited but not saved yet.",
                fontSize = 9.sp,
                color = AccentYellow,
                lineHeight = 14.sp,
            )
        }

        // Save button
        Button(
            onClick  = {
                if (valid) onSave(widthInt!!, heightInt!!)
                else hasError = true
            },
            modifier = Modifier.fillMaxWidth().height(36.dp),
            shape    = RoundedCornerShape(8.dp),
            colors   = ButtonDefaults.buttonColors(
                containerColor = if (valid) AccentCyan else TextMuted,
                contentColor   = Color.Black,
            ),
        ) {
            Icon(Icons.Filled.Save, contentDescription = null, modifier = Modifier.size(14.dp))
            Spacer(Modifier.width(4.dp))
            Text("Save to board_config.json", fontSize = 11.sp, fontWeight = FontWeight.SemiBold)
        }
    }
}

@Composable
private fun DimTextField(
    label:   String,
    value:   String,
    onValue: (String) -> Unit,
    isError: Boolean,
) {
    OutlinedTextField(
        value         = value,
        onValueChange = onValue,
        label         = { Text(label, fontSize = 11.sp) },
        singleLine    = true,
        isError       = isError,
        modifier      = Modifier.fillMaxWidth(),
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
        colors        = OutlinedTextFieldDefaults.colors(
            focusedBorderColor   = AccentCyan,
            unfocusedBorderColor = BorderSubtle,
            focusedTextColor     = TextPrimary,
            unfocusedTextColor   = TextSecondary,
            focusedLabelColor    = AccentCyan,
            unfocusedLabelColor  = TextMuted,
            errorBorderColor     = AccentRed,
        ),
        textStyle = LocalTextStyle.current.copy(
            fontFamily = FontFamily.Monospace,
            fontSize   = 13.sp,
        ),
    )
}

@Composable
private fun StartStopButton(isRunning: Boolean, onStart: () -> Unit, onStop: () -> Unit) {
    val icon  = if (isRunning) Icons.Filled.Stop      else Icons.Filled.PlayArrow
    val label = if (isRunning) "Stop Driver"           else "Start Driver"
    val bg    = if (isRunning) AccentRed               else AccentGreen
    val fg    = if (isRunning) Color.White             else Color.Black

    Button(
        onClick  = if (isRunning) onStop else onStart,
        modifier = Modifier.fillMaxWidth().height(44.dp),
        shape    = RoundedCornerShape(10.dp),
        colors   = ButtonDefaults.buttonColors(containerColor = bg, contentColor = fg),
    ) {
        Icon(imageVector = icon, contentDescription = null, modifier = Modifier.size(18.dp))
        Spacer(Modifier.width(6.dp))
        Text(text = label, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
    }
}

@Composable
private fun InfoRow(label: String, value: String) {
    Row(
        modifier              = Modifier.fillMaxWidth().padding(vertical = 2.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        Text(label, fontSize = 11.sp, color = TextMuted)
        Text(value, fontSize = 11.sp, color = TextSecondary, fontFamily = FontFamily.Monospace)
    }
}

@Composable
private fun SectionLabel(text: String) {
    Text(
        text         = text,
        fontSize     = 10.sp,
        fontWeight   = FontWeight.Bold,
        color        = AccentCyan,
        letterSpacing = 2.sp,
        fontFamily   = FontFamily.Monospace,
    )
}

@Composable
private fun PanelDivider() {
    Spacer(Modifier.height(12.dp))
    HorizontalDivider(color = BorderSubtle)
    Spacer(Modifier.height(12.dp))
}

private fun mountModeLabel(rawValue: String): String =
    MountMode.entries.firstOrNull { it.configValue.equals(rawValue, ignoreCase = true) }?.displayName
        ?: rawValue
