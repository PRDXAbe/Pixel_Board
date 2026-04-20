package com.pixelboard.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Circle
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.pixelboard.AppUiState
import androidx.compose.animation.core.*

@Composable
fun TopBar(state: AppUiState) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .height(52.dp)
            .background(SurfaceBase)
            .padding(horizontal = 20.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        // ── Logo + title ──────────────────────────────────────────────────────
        Text(
            text       = "Pixel",
            fontSize   = 20.sp,
            fontWeight = FontWeight.ExtraBold,
            color      = AccentCyan,
            fontFamily = FontFamily.Monospace,
        )
        Text(
            text       = "Board",
            fontSize   = 20.sp,
            fontWeight = FontWeight.Light,
            color      = TextPrimary,
            fontFamily = FontFamily.Monospace,
        )

        Spacer(Modifier.weight(1f))

        // ── Connection indicator ──────────────────────────────────────────────
        ConnectionDot(isConnected = state.isConnected)

        Spacer(Modifier.width(10.dp))

        Text(
            text     = if (state.isConnected) "Live" else if (state.isDriverRunning) "Connecting…" else "Offline",
            fontSize = 13.sp,
            color    = if (state.isConnected) AccentGreen else TextSecondary,
            fontWeight = FontWeight.Medium,
        )

        Spacer(Modifier.width(28.dp))

        // ── Scan rate ─────────────────────────────────────────────────────────
        if (state.isConnected) {
            Text(
                text     = "${state.frame.rateHz} Hz",
                fontSize = 13.sp,
                color    = AccentCyan,
                fontFamily = FontFamily.Monospace,
            )
            Spacer(Modifier.width(28.dp))
        }

        // ── Board dimensions ──────────────────────────────────────────────────
        val liveWidthMm = state.frame.boardWidthMm
        val liveHeightMm = state.frame.boardHeightMm
        val showLiveBoardDims = state.isConnected && liveWidthMm > 0 && liveHeightMm > 0
        val wCm = if (showLiveBoardDims) liveWidthMm / 10 else state.boardConfig.widthMm / 10
        val hCm = if (showLiveBoardDims) liveHeightMm / 10 else state.boardConfig.heightMm / 10
        Text(
            text     = "${wCm}×${hCm} cm",
            fontSize = 12.sp,
            color    = TextSecondary,
            fontFamily = FontFamily.Monospace,
        )
    }

    HorizontalDivider(color = BorderSubtle, thickness = 1.dp)
}

@Composable
private fun ConnectionDot(isConnected: Boolean) {
    if (isConnected) {
        // Pulsing green dot when connected
        val transition = rememberInfiniteTransition(label = "pulse")
        val alpha by transition.animateFloat(
            initialValue = 1f,
            targetValue  = 0.3f,
            animationSpec = infiniteRepeatable(
                animation  = tween(900, easing = FastOutSlowInEasing),
                repeatMode = RepeatMode.Reverse,
            ),
            label = "alpha",
        )
        Box(
            modifier = Modifier
                .size(10.dp)
                .clip(CircleShape)
                .background(AccentGreen.copy(alpha = alpha))
        )
    } else {
        Box(
            modifier = Modifier
                .size(10.dp)
                .clip(CircleShape)
                .background(TextMuted)
        )
    }
}
