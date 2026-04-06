import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.gestures.awaitTouchSlopOrCancellation
import androidx.compose.foundation.gestures.drag
import androidx.compose.foundation.gestures.waitForUpOrCancellation
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.PointerInputChange
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.IntSize
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay
import kotlinx.coroutines.withTimeoutOrNull
import kotlin.math.roundToInt

// ─── Lidar State ─────────────────────────────────────────────────────────────

data class LidarState(
    val x: Float       = -1f,
    val y: Float       = -1f,
    val radius: Float  = 26f,
    val range: Float   = 3.5f,
    val isLocked: Boolean = true
) {
    fun worldCoords(canvasWidth: Float, canvasHeight: Float): Pair<Float, Float> {
        // Origin = top-left of the dashed support rectangle
        val supportLeft = canvasWidth  * (1f - 0.56f) / 2f
        val supportTop  = canvasHeight * (1f - 0.60f) / 2f
        val wx = x - supportLeft
        val wy = y - supportTop
        return Pair(wx, wy)
    }
}

// ─── Gap Clamping ────────────────────────────────────────────────────────────

fun clampToGap(
    px: Float, py: Float,
    cw: Float, ch: Float,
    dotR: Float,
    placementAxis: LidarPlacementAxis,
    supportWFrac: Float = 0.56f,
    supportHFrac: Float = 0.60f,
    boardWFrac: Float   = 0.38f,
    boardHFrac: Float   = 0.40f
): Pair<Float, Float> {
    val cx = cw / 2f; val cy = ch / 2f

    // We still have the outer margin limit space and inner board boundary space.
    // We want the Lidar to "snap" to the horizontal midpoint or vertical midpoint
    // of the gap *between* the board edge and margin edge.
    // The gap midpoints are:
    val gapMidX = cw * ((supportWFrac + boardWFrac) / 4f)
    val gapMidY = ch * ((supportHFrac + boardHFrac) / 4f)

    val outerHW = cw * (supportWFrac / 2f) - dotR
    val outerHH = ch * (supportHFrac / 2f) - dotR

    if (placementAxis == LidarPlacementAxis.VERTICAL) {
        // Locked to Top Gap or Bottom Gap, can slide freely left/right
        val x = px.coerceIn(cx - outerHW, cx + outerHW)
        // Snap y to either top gap mid or bottom gap mid
        val snapToTop = py < cy
        val y = if (snapToTop) cy - gapMidY else cy + gapMidY
        return Pair(x, y)
    } else {
        // Locked to Left Gap or Right Gap, can slide freely up/down
        val y = py.coerceIn(cy - outerHH, cy + outerHH)
        // Snap x to either left gap mid or right gap mid
        val snapToLeft = px < cx
        val x = if (snapToLeft) cx - gapMidX else cx + gapMidX
        return Pair(x, y)
    }
}

// ─── Lidar Dot Composable ────────────────────────────────────────────────────
//
// Architecture note: The visual dot and the gesture handler are SEPARATE siblings.
// The visual dot moves via Modifier.offset, while the gesture overlay is a fixed
// fillMaxSize Box using parent-space coordinates. This avoids the stale-position
// bug where positionChange() returns near-zero deltas because the composable
// moves with the pointer.

@Composable
fun LidarDot(
    state: LidarState,
    canvasSize: IntSize,
    placementAxis: LidarPlacementAxis,
    onMove: (newX: Float, newY: Float) -> Unit,
    onToggleLock: () -> Unit,
    supportWFrac: Float = 0.56f,
    supportHFrac: Float = 0.60f,
    boardWFrac: Float   = 0.38f,
    boardHFrac: Float   = 0.40f
) {
    if (canvasSize.width <= 0 || state.x < 0f) return

    // Refs so the fixed pointerInput lambda always reads the latest values
    val stateRef        = rememberUpdatedState(state)
    val placementAxisRef = rememberUpdatedState(placementAxis)
    val onMoveRef       = rememberUpdatedState(onMove)
    val onToggleLockRef = rememberUpdatedState(onToggleLock)

    var showLockIcon    by remember { mutableStateOf(false) }
    var lockIconIsLocked by remember { mutableStateOf(state.isLocked) }

    LaunchedEffect(showLockIcon) {
        if (showLockIcon) {
            delay(900)
            showLockIcon = false
        }
    }

    // Pre-compute hit-test radius in px (generous touch target = 1.5× visual radius)
    val hitRadiusSq = with(LocalDensity.current) {
        val r = 26.dp.toPx() * 1.5f
        r * r
    }

    // ── 1) Visual dot (moves via offset, NO pointer handling) ────────────────
    Box(
        Modifier.offset {
            val halfDotPx = 26.dp.roundToPx()
            IntOffset(
                state.x.roundToInt() - halfDotPx,
                state.y.roundToInt() - halfDotPx
            )
        }
    ) {
        Box(
            Modifier.size(52.dp)
                .background(Color.Gray.copy(alpha = 0.45f), CircleShape),
            contentAlignment = Alignment.Center
        ) {
            // Inner dark circle
            Box(
                Modifier.size(34.dp).background(AppColors.text, CircleShape),
                contentAlignment = Alignment.Center
            ) {
                AnimatedVisibility(
                    visible = showLockIcon,
                    enter = fadeIn(),
                    exit = fadeOut()
                ) {
                    Canvas(Modifier.size(16.dp)) {
                        if (lockIconIsLocked) drawLockIcon(Color.White)
                        else drawUnlockIcon(AppColors.accent)
                    }
                }
            }
        }

        // Pointer line
        Canvas(Modifier.fillMaxSize()) {
            drawLine(
                AppColors.dashedLine,
                Offset(26.dp.toPx(), 0f),
                Offset(110.dp.toPx(), -55.dp.toPx()),
                strokeWidth = 1.5f
            )
        }

        // Label
        Column(Modifier.offset(x = 114.dp, y = (-72).dp)) {
            Text(
                "black dot (lidar)", color = AppColors.text,
                fontWeight = FontWeight.SemiBold, fontSize = 12.sp
            )
            Text(
                if (state.isLocked) "● locked · double-click to unlock" else "○ movable · drag to move",
                color = if (state.isLocked) AppColors.danger else AppColors.accent,
                fontSize = 11.sp
            )
        }
    }

    // ── 2) Gesture overlay (fixed, fills parent – stable coordinate space) ───
    Box(
        Modifier.fillMaxSize()
            .pointerInput(canvasSize) {
                awaitEachGesture {
                    val down = awaitFirstDown(requireUnconsumed = false)
                    val current = stateRef.value

                    // ── Hit test: is the pointer near the dot centre? ────
                    val dx = down.position.x - current.x
                    val dy = down.position.y - current.y
                    if (dx * dx + dy * dy > hitRadiusSq) {
                        // Not on the dot → let the event pass through
                        return@awaitEachGesture
                    }

                    val downTime = System.currentTimeMillis()

                    // Grab offset = distance from dot center to the exact click point
                    val grabOffsetX = down.position.x - current.x
                    val grabOffsetY = down.position.y - current.y
                    var dragHandled = false

                    // ── Drag (only when unlocked) ────────────────────────
                    if (!current.isLocked) {
                        val slopResult = awaitTouchSlopOrCancellation(down.id) {
                            change: PointerInputChange, _: Offset ->
                            change.consume()
                            // position is in PARENT space (overlay is fillMaxSize, unmoved)
                            val (nx, ny) = clampToGap(
                                change.position.x - grabOffsetX,
                                change.position.y - grabOffsetY,
                                canvasSize.width.toFloat(),
                                canvasSize.height.toFloat(),
                                stateRef.value.radius,
                                placementAxisRef.value,
                                supportWFrac, supportHFrac,
                                boardWFrac, boardHFrac
                            )
                            onMoveRef.value(nx, ny)
                            dragHandled = true
                        }
                        if (slopResult != null) {
                            drag(slopResult.id) { dragChange: PointerInputChange ->
                                dragChange.consume()
                                val (nx, ny) = clampToGap(
                                    dragChange.position.x - grabOffsetX,
                                    dragChange.position.y - grabOffsetY,
                                    canvasSize.width.toFloat(),
                                    canvasSize.height.toFloat(),
                                    stateRef.value.radius,
                                    placementAxisRef.value,
                                    supportWFrac, supportHFrac,
                                    boardWFrac, boardHFrac
                                )
                                onMoveRef.value(nx, ny)
                            }
                            return@awaitEachGesture
                        }
                    }

                    // ── Double-tap → toggle lock ─────────────────────────
                    if (!dragHandled) {
                        val up = waitForUpOrCancellation()
                        if (up != null) {
                            val tapDuration = System.currentTimeMillis() - downTime
                            if (tapDuration < 500) {
                                val secondDown = withTimeoutOrNull(300L) {
                                    awaitFirstDown(requireUnconsumed = false)
                                }
                                if (secondDown != null) {
                                    waitForUpOrCancellation()
                                    lockIconIsLocked = !stateRef.value.isLocked
                                    showLockIcon = true
                                    onToggleLockRef.value()
                                }
                            }
                        }
                    }
                }
            }
    )
}

// ─── Minimalistic Padlock Icons ──────────────────────────────────────────────

/**
 * Draws a tiny closed-padlock icon centred in the current DrawScope.
 * Shackle = arc stroke, body = filled rounded rect.
 */
private fun DrawScope.drawLockIcon(color: Color) {
    val w = size.width
    val h = size.height
    val strokeW = w * 0.14f

    // Body (lower 55% of the icon)
    val bodyTop = h * 0.42f
    val bodyRect = androidx.compose.ui.geometry.Rect(
        w * 0.18f, bodyTop, w * 0.82f, h * 0.95f
    )
    drawRoundRect(
        color, bodyRect.topLeft,
        androidx.compose.ui.geometry.Size(bodyRect.width, bodyRect.height),
        cornerRadius = androidx.compose.ui.geometry.CornerRadius(w * 0.08f)
    )

    // Shackle (closed arc above body)
    val shackleRect = androidx.compose.ui.geometry.Rect(
        w * 0.25f, h * 0.05f, w * 0.75f, bodyTop + h * 0.1f
    )
    drawArc(
        color, startAngle = 180f, sweepAngle = 180f,
        useCenter = false, topLeft = shackleRect.topLeft,
        size = androidx.compose.ui.geometry.Size(shackleRect.width, shackleRect.height),
        style = Stroke(strokeW)
    )
}

/**
 * Draws a tiny open-padlock icon (shackle raised & shifted right).
 */
private fun DrawScope.drawUnlockIcon(color: Color) {
    val w = size.width
    val h = size.height
    val strokeW = w * 0.14f

    // Body
    val bodyTop = h * 0.42f
    val bodyRect = androidx.compose.ui.geometry.Rect(
        w * 0.18f, bodyTop, w * 0.82f, h * 0.95f
    )
    drawRoundRect(
        color, bodyRect.topLeft,
        androidx.compose.ui.geometry.Size(bodyRect.width, bodyRect.height),
        cornerRadius = androidx.compose.ui.geometry.CornerRadius(w * 0.08f)
    )

    // Shackle (open – raised higher and only the right leg connects)
    val shackleRect = androidx.compose.ui.geometry.Rect(
        w * 0.25f, h * -0.15f, w * 0.75f, bodyTop - h * 0.1f
    )
    drawArc(
        color, startAngle = 180f, sweepAngle = 160f,
        useCenter = false, topLeft = shackleRect.topLeft,
        size = androidx.compose.ui.geometry.Size(shackleRect.width, shackleRect.height),
        style = Stroke(strokeW)
    )
}
