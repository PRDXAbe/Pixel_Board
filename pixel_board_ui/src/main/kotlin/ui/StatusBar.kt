package com.pixelboard.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.pixelboard.AppUiState

@Composable
fun StatusBar(state: AppUiState) {
    HorizontalDivider(color = BorderSubtle, thickness = 1.dp)
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .height(30.dp)
            .background(SurfaceBase)
            .padding(horizontal = 16.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(24.dp),
    ) {
        val frame = state.frame

        StatusItem("Scans", "${frame.scanCount}")

        if (state.isConnected) {
            StatusItem("Rate", "${frame.rateHz} Hz")
            StatusItem("Pts",  "${frame.scanPts.size}")
            StatusItem("Touches", "${frame.touches.size}")
        }

        StatusItem("RunPts", "${state.runCaptureCount}")
        StatusItem("Interact", if (state.interactiveModeEnabled) "On" else "Off")
        state.availableDisplays.firstOrNull { it.id == state.selectedDisplayId }?.let { display ->
            StatusItem("Display", display.name)
        }
        state.activeInteractiveTouchId?.let { touchId ->
            StatusItem("Pointer", "#$touchId")
        }

        StatusItem(
            "Board",
            "X[%.2f…%.2f] Y[%.2f…%.2f]".format(
                frame.boardMinX, frame.boardMaxX, frame.boardMinY, frame.boardMaxY
            ),
        )

        Spacer(Modifier.weight(1f))

        StatusItem("Board", "${frame.boardWidthMm}×${frame.boardHeightMm} mm")
        StatusItem("Port", "/dev/ttyUSB0 · 230400")
    }
}

@Composable
private fun StatusItem(label: String, value: String) {
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
        Text(
            text      = "$label:",
            fontSize  = 10.sp,
            color     = TextMuted,
            fontFamily = FontFamily.Monospace,
        )
        Text(
            text      = value,
            fontSize  = 10.sp,
            color     = TextSecondary,
            fontFamily = FontFamily.Monospace,
        )
    }
}
