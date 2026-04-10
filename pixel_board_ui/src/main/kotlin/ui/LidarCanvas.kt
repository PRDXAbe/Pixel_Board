package com.pixelboard.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.*
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.pixelboard.BoardFrame
import kotlin.math.min

/**
 * Top-down LIDAR scan canvas. Coordinate origin (0,0) is the LIDAR itself.
 * Board sits in front (positive X) and spans laterally (Y axis).
 *
 * The view window is padded slightly beyond the board boundaries.
 */
@Composable
fun LidarCanvas(frame: BoardFrame, modifier: Modifier = Modifier) {

    Box(
        modifier = modifier
            .clip(RoundedCornerShape(12.dp))
            .background(Color(0xFF0C0C14)),
        contentAlignment = Alignment.Center,
    ) {
        if (frame.scanCount == 0) {
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                Text("Waiting for scan data…", color = TextMuted, fontSize = 14.sp)
                Spacer(Modifier.height(6.dp))
                Text("Start the driver to begin.", color = TextMuted, fontSize = 12.sp,
                    fontFamily = FontFamily.Monospace)
            }
        }

        Canvas(modifier = Modifier.fillMaxSize().padding(12.dp)) {
            val w = size.width
            val h = size.height

            // ── View window (slightly larger than board) ──────────────────────
            val padX = (frame.boardMaxX - frame.boardMinX) * 0.15f
            val padY = (frame.boardMaxY - frame.boardMinY) * 0.35f

            val viewMinX = -0.1f
            val viewMaxX = frame.boardMaxX + padX
            val viewMinY = frame.boardMinY - padY
            val viewMaxY = frame.boardMaxY + padY

            fun toCanvas(x: Float, y: Float): Offset {
                val nx = (x - viewMinX) / (viewMaxX - viewMinX)
                val ny = 1f - (y - viewMinY) / (viewMaxY - viewMinY) // flip Y
                return Offset(nx * w, ny * h)
            }

            // ── Background grid ───────────────────────────────────────────────
            drawGrid(toCanvas = ::toCanvas,
                minX = viewMinX, maxX = viewMaxX,
                minY = viewMinY, maxY = viewMaxY,
                w = w, h = h)

            // ── All scan points (dim grey) ────────────────────────────────────
            for ((x, y) in frame.scanPts) {
                val pt = toCanvas(x, y)
                if (pt.x < 0 || pt.x > w || pt.y < 0 || pt.y > h) continue
                drawCircle(
                    color  = Color(0xFF3A3A5A),
                    radius = 1.5f,
                    center = pt,
                )
            }

            // ── Board boundary ────────────────────────────────────────────────
            val tl = toCanvas(frame.boardMinX, frame.boardMaxY)
            val br = toCanvas(frame.boardMaxX, frame.boardMinY)
            drawBoardRect(tl, br)

            // ── Board-filtered scan points (white/blue) ───────────────────────
            for ((x, y) in frame.boardPts) {
                val pt = toCanvas(x, y)
                drawCircle(
                    color  = Color(0xFFBBCCFF),
                    radius = 2.5f,
                    center = pt,
                )
            }

            // ── Touch centroids ───────────────────────────────────────────────
            for (touch in frame.touches) {
                val pt = toCanvas(touch.mx, touch.my)
                // Outer ring
                drawCircle(
                    color  = AccentRed.copy(alpha = 0.25f),
                    radius = 18f,
                    center = pt,
                )
                // Middle ring
                drawCircle(
                    color  = AccentRed.copy(alpha = 0.6f),
                    radius = 10f,
                    center = pt,
                    style  = Stroke(width = 1.5f),
                )
                // Core dot
                drawCircle(
                    color  = AccentRed,
                    radius = 5f,
                    center = pt,
                )
                // Crosshair lines
                drawLine(AccentRed.copy(alpha = 0.5f), pt.copy(x = pt.x - 16f), pt.copy(x = pt.x + 16f), strokeWidth = 1f)
                drawLine(AccentRed.copy(alpha = 0.5f), pt.copy(y = pt.y - 16f), pt.copy(y = pt.y + 16f), strokeWidth = 1f)
            }

            // ── LIDAR origin marker (yellow triangle at 0,0) ──────────────────
            val origin = toCanvas(0f, 0f)
            drawLidarMarker(origin)
        }
    }
}

private fun DrawScope.drawGrid(
    toCanvas: (Float, Float) -> Offset,
    minX: Float, maxX: Float,
    minY: Float, maxY: Float,
    w: Float, h: Float,
) {
    val minorStep = 0.1f
    val majorStep = 0.5f
    val minorColor = Color(0xFF1A1A2E)
    val majorColor = Color(0xFF252540)

    var x = (minX / minorStep).toInt() * minorStep
    while (x <= maxX) {
        val isMajor = (Math.round(x / majorStep) * majorStep - x) < 0.001f
        val pt1 = toCanvas(x, minY)
        val pt2 = toCanvas(x, maxY)
        drawLine(
            color       = if (isMajor) majorColor else minorColor,
            start       = pt1,
            end         = pt2,
            strokeWidth = if (isMajor) 1f else 0.5f,
        )
        x += minorStep
    }

    var y = (minY / minorStep).toInt() * minorStep
    while (y <= maxY) {
        val isMajor = (Math.round(y / majorStep) * majorStep - y) < 0.001f
        val pt1 = toCanvas(minX, y)
        val pt2 = toCanvas(maxX, y)
        drawLine(
            color       = if (isMajor) majorColor else minorColor,
            start       = pt1,
            end         = pt2,
            strokeWidth = if (isMajor) 1f else 0.5f,
        )
        y += minorStep
    }
}

private fun DrawScope.drawBoardRect(tl: Offset, br: Offset) {
    val rect  = androidx.compose.ui.geometry.Rect(tl, br)
    val green = BoardGreen

    // Filled background
    drawRect(
        color    = green.copy(alpha = 0.04f),
        topLeft  = tl,
        size     = Size(br.x - tl.x, br.y - tl.y),
    )
    // Dashed border — approximated with a PathEffect
    drawRect(
        color    = green.copy(alpha = 0.8f),
        topLeft  = tl,
        size     = Size(br.x - tl.x, br.y - tl.y),
        style    = Stroke(
            width      = 1.5f,
            pathEffect = PathEffect.dashPathEffect(floatArrayOf(8f, 5f), 0f),
        ),
    )

    // Corner accents
    val cs = 8f // corner size
    val cc = green
    listOf(tl, Offset(br.x, tl.y), br, Offset(tl.x, br.y)).forEach { corner ->
        val dx = if (corner.x == tl.x) cs else -cs
        val dy = if (corner.y == tl.y) cs else -cs
        drawLine(cc, corner, corner.copy(x = corner.x + dx), strokeWidth = 2f)
        drawLine(cc, corner, corner.copy(y = corner.y + dy), strokeWidth = 2f)
    }
}

private fun DrawScope.drawLidarMarker(center: Offset) {
    val r = 9f
    val path = Path().apply {
        moveTo(center.x, center.y - r)                  // top
        lineTo(center.x + r * 0.866f, center.y + r * 0.5f) // bottom-right
        lineTo(center.x - r * 0.866f, center.y + r * 0.5f) // bottom-left
        close()
    }
    drawPath(path, color = AccentYellow)
    drawPath(path, color = Color.Black, style = Stroke(width = 1f))
}
