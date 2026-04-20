package com.pixelboard.ui

import androidx.compose.animation.core.*
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.pixelboard.AppUiState
import com.pixelboard.TouchPoint

@Composable
fun TouchPanel(state: AppUiState, modifier: Modifier = Modifier) {
    Column(
        modifier = modifier
            .fillMaxHeight()
            .background(SurfaceBase)
            .padding(16.dp),
    ) {
        // ── Header ────────────────────────────────────────────────────────────
        Text(
            text       = "TOUCH",
            fontSize   = 11.sp,
            fontWeight = FontWeight.Bold,
            color      = AccentCyan,
            letterSpacing = 3.sp,
            fontFamily = FontFamily.Monospace,
        )
        Text(
            text      = "COORDINATES",
            fontSize  = 11.sp,
            fontWeight = FontWeight.Bold,
            color     = AccentCyan,
            letterSpacing = 3.sp,
            fontFamily = FontFamily.Monospace,
        )

        Spacer(Modifier.height(4.dp))
        HorizontalDivider(color = BorderSubtle)
        Spacer(Modifier.height(12.dp))

        // ── Touch cards or empty state ────────────────────────────────────────
        if (state.frame.touches.isEmpty()) {
            Box(
                modifier = Modifier.fillMaxWidth().weight(1f),
                contentAlignment = Alignment.Center,
            ) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    // Animated idle ring
                    IdleRing()
                    Spacer(Modifier.height(16.dp))
                    Text(
                        "No touch\ndetected",
                        color     = TextMuted,
                        fontSize  = 13.sp,
                        textAlign = TextAlign.Center,
                        lineHeight = 20.sp,
                    )
                }
            }
        } else {
        LazyColumn(
                modifier           = Modifier.weight(1f),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                items(
                    items = state.frame.touches.take(4),
                    key = { it.id },
                ) { touch ->
                    TouchCard(
                        touch         = touch,
                        boardWidthMm  = state.frame.boardWidthMm,
                        boardHeightMm = state.frame.boardHeightMm,
                    )
                }
            }
        }

        Spacer(Modifier.height(12.dp))
        HorizontalDivider(color = BorderSubtle)
        Spacer(Modifier.height(8.dp))

        // ── Resolution label ──────────────────────────────────────────────────
        Text(
            text       = "Board: ${state.frame.boardWidthMm}×${state.frame.boardHeightMm} mm",
            fontSize   = 11.sp,
            color      = TextMuted,
            fontFamily = FontFamily.Monospace,
        )
    }
}

@Composable
private fun TouchCard(touch: TouchPoint, boardWidthMm: Int, boardHeightMm: Int) {
    val shape = RoundedCornerShape(10.dp)
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .clip(shape)
            .background(SurfaceElevated)
            .border(1.dp, AccentRed.copy(alpha = 0.35f), shape)
            .padding(12.dp),
    ) {
        Text(
            text = "Touch #${touch.id}",
            fontSize = 10.sp,
            color = TextMuted,
            fontFamily = FontFamily.Monospace,
        )
        Spacer(Modifier.height(4.dp))

        // Large pixel coordinate
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                text       = "(",
                fontSize   = 11.sp,
                color      = TextMuted,
                fontFamily = FontFamily.Monospace,
            )
            Text(
                text       = "${touch.px}",
                fontSize   = 28.sp,
                fontWeight = FontWeight.Bold,
                color      = AccentRed,
                fontFamily = FontFamily.Monospace,
            )
            Text(
                text       = ", ",
                fontSize   = 11.sp,
                color      = TextMuted,
                fontFamily = FontFamily.Monospace,
            )
            Text(
                text       = "${touch.py}",
                fontSize   = 28.sp,
                fontWeight = FontWeight.Bold,
                color      = AccentRed,
                fontFamily = FontFamily.Monospace,
            )
            Text(
                text       = ")",
                fontSize   = 11.sp,
                color      = TextMuted,
                fontFamily = FontFamily.Monospace,
            )
        }

        Spacer(Modifier.height(6.dp))

        // Physical coordinates
        Row(
            modifier            = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            LabelValue("X", "${touch.mx} m")
            LabelValue("Y", "${touch.my} m")
        }

        Spacer(Modifier.height(4.dp))

        // Normalised position bar
        PositionBar(nx = touch.px.toFloat() / boardWidthMm, ny = touch.py.toFloat() / boardHeightMm)
    }
}

@Composable
private fun LabelValue(label: String, value: String) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Text(
            text      = "$label ",
            fontSize  = 10.sp,
            color     = TextMuted,
            fontFamily = FontFamily.Monospace,
        )
        Text(
            text      = value,
            fontSize  = 12.sp,
            color     = TextSecondary,
            fontFamily = FontFamily.Monospace,
        )
    }
}

@Composable
private fun PositionBar(nx: Float, ny: Float) {
    // Tiny 2D dot indicator showing normalised position on a mini rectangle
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .height(36.dp)
            .clip(RoundedCornerShape(4.dp))
            .background(SurfaceHighlight)
            .drawBehind {
                val dotX = nx.coerceIn(0f, 1f) * size.width
                val dotY = ny.coerceIn(0f, 1f) * size.height
                // Crosshair
                drawLine(AccentRed.copy(alpha = 0.4f), start = androidx.compose.ui.geometry.Offset(dotX, 0f), end = androidx.compose.ui.geometry.Offset(dotX, size.height), strokeWidth = 1f)
                drawLine(AccentRed.copy(alpha = 0.4f), start = androidx.compose.ui.geometry.Offset(0f, dotY), end = androidx.compose.ui.geometry.Offset(size.width, dotY), strokeWidth = 1f)
                // Dot
                drawCircle(AccentRed, radius = 4f, center = androidx.compose.ui.geometry.Offset(dotX, dotY))
            },
    )
}

@Composable
private fun IdleRing() {
    val transition = rememberInfiniteTransition(label = "idle")
    val scale by transition.animateFloat(
        initialValue  = 0.6f,
        targetValue   = 1f,
        animationSpec = infiniteRepeatable(
            animation  = tween(1400, easing = EaseInOutSine),
            repeatMode = RepeatMode.Reverse,
        ),
        label = "scale",
    )
    Box(
        modifier = Modifier
            .size(56.dp)
            .drawBehind {
                val r = (size.minDimension / 2f) * scale
                drawCircle(AccentCyan.copy(alpha = 0.15f * scale), radius = r)
                drawCircle(AccentCyan.copy(alpha = 0.6f * scale), radius = r, style = Stroke(1.5f))
            },
    )
}
