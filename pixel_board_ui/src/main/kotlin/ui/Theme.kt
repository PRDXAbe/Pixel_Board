package com.pixelboard.ui

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

// ── Colour tokens ─────────────────────────────────────────────────────────────

val BackgroundDeep   = Color(0xFF0A0A10)
val SurfaceBase      = Color(0xFF111118)
val SurfaceElevated  = Color(0xFF1A1A26)
val SurfaceHighlight = Color(0xFF22223A)
val BorderSubtle     = Color(0xFF2A2A45)

val AccentCyan       = Color(0xFF00E5FF)   // primary accent — scan / active
val AccentGreen      = Color(0xFF00E676)   // success / connected
val AccentYellow     = Color(0xFFFFD740)   // LIDAR origin marker
val AccentRed        = Color(0xFFFF4B6E)   // touch detections / error

val TextPrimary      = Color(0xFFE8E8F0)
val TextSecondary    = Color(0xFF8080A0)
val TextMuted        = Color(0xFF44445A)

// Board boundary colour (matches magic_board_live.py)
val BoardGreen       = Color(0xFF00E64D)

// ── Material3 dark scheme ─────────────────────────────────────────────────────

private val PixelBoardColorScheme = darkColorScheme(
    primary          = AccentCyan,
    onPrimary        = Color(0xFF001A20),
    primaryContainer = Color(0xFF003040),
    secondary        = AccentGreen,
    onSecondary      = Color(0xFF00210E),
    tertiary         = AccentYellow,
    background       = BackgroundDeep,
    surface          = SurfaceBase,
    surfaceVariant   = SurfaceElevated,
    onBackground     = TextPrimary,
    onSurface        = TextPrimary,
    onSurfaceVariant = TextSecondary,
    outline          = BorderSubtle,
    error            = AccentRed,
)

@Composable
fun PixelBoardTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = PixelBoardColorScheme,
        content     = content,
    )
}
