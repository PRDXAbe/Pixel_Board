package com.pixelboard.ui

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
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
        // ── Section: Driver control ───────────────────────────────────────────
        SectionLabel("DRIVER")
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

        Spacer(Modifier.weight(1f))

        // ── Footer ────────────────────────────────────────────────────────────
        Text(
            text       = "LD19 · /dev/ttyUSB0 · 230400",
            fontSize   = 10.sp,
            color      = TextMuted,
            fontFamily = FontFamily.Monospace,
        )
    }
}

// ── Sub-composables ────────────────────────────────────────────────────────────

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
                text      = "Pixel range: (0,0) → ($widthInt, $heightInt)",
                fontSize  = 10.sp,
                color     = AccentCyan.copy(alpha = 0.8f),
                fontFamily = FontFamily.Monospace,
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
