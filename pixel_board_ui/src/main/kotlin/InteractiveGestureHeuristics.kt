package com.pixelboard

import java.awt.Frame
import kotlin.math.abs
import kotlin.math.hypot
import kotlin.math.roundToInt

internal const val SINGLE_CLICK_DELAY_MS = 1_000L
internal const val DWELL_DOUBLE_CLICK_DURATION_MS = 2_000L
internal const val DWELL_DOUBLE_CLICK_RADIUS_PX = 8.0
internal const val LONG_PRESS_DURATION_MS = 420L
internal const val HOLD_MAX_MOVEMENT_MM = 14.0
internal const val HOLD_STATIONARY_RADIUS_MM = 6.0
internal const val INTERACTION_TAP_CONFIRM_FRAMES = 1
internal const val INTERACTION_HOVER_ANCHOR_RADIUS_MM = 8.0
internal const val INTERACTION_HOVER_ANCHOR_CONFIRM_FRAMES = 1
internal const val INTERACTION_RELEASE_DRIFT_MAX_MM = 10.0
internal const val UI_FRAME_PUBLISH_INTERVAL_MS = 33L
internal const val INTERACTION_POINTER_TICK_MS = 16L

private const val INTERACTION_POINTER_DEADBAND_X_PX = 8
private const val INTERACTION_POINTER_DEADBAND_Y_PX = 6
private const val INTERACTION_POINTER_PREDICTION_HORIZON_MS = 50L
private const val INTERACTION_POINTER_MAX_LEAD_PX = 48

internal fun stabilizeInteractiveScreenPosition(
    previousX: Int,
    previousY: Int,
    rawX: Int,
    rawY: Int,
): Pair<Int, Int> {
    val keepX = abs(rawX - previousX) <= INTERACTION_POINTER_DEADBAND_X_PX
    val keepY = abs(rawY - previousY) <= INTERACTION_POINTER_DEADBAND_Y_PX
    return (if (keepX) previousX else rawX) to (if (keepY) previousY else rawY)
}

internal fun isTapFrameConfirmationSatisfied(
    seenFrames: Int,
    hoverAnchorFrames: Int,
): Boolean =
    seenFrames >= INTERACTION_TAP_CONFIRM_FRAMES &&
        hoverAnchorFrames >= INTERACTION_HOVER_ANCHOR_CONFIRM_FRAMES

internal fun isSingleClickDelayElapsed(elapsedMs: Long): Boolean =
    elapsedMs >= SINGLE_CLICK_DELAY_MS

internal fun shouldUsePixelBoardWindowSuppression(
    title: String,
    isShowing: Boolean,
    extendedState: Int,
    isActive: Boolean,
): Boolean =
    title == "PixelBoard" &&
        isShowing &&
        (extendedState and Frame.ICONIFIED) == 0 &&
        isActive

internal fun isWithinDwellDoubleClickRadius(
    anchorScreenX: Int,
    anchorScreenY: Int,
    currentScreenX: Int,
    currentScreenY: Int,
): Boolean =
    hypot(
        (currentScreenX - anchorScreenX).toDouble(),
        (currentScreenY - anchorScreenY).toDouble(),
    ) <= DWELL_DOUBLE_CLICK_RADIUS_PX

internal fun shouldTriggerDwellDoubleClick(
    anchorScreenX: Int,
    anchorScreenY: Int,
    currentScreenX: Int,
    currentScreenY: Int,
    stableElapsedMs: Long,
): Boolean =
    stableElapsedMs >= DWELL_DOUBLE_CLICK_DURATION_MS &&
        isWithinDwellDoubleClickRadius(
            anchorScreenX = anchorScreenX,
            anchorScreenY = anchorScreenY,
            currentScreenX = currentScreenX,
            currentScreenY = currentScreenY,
        )

internal fun computeInteractivePointerVelocity(
    previousMeasuredX: Int,
    previousMeasuredY: Int,
    previousMeasuredAtMs: Long,
    currentMeasuredX: Int,
    currentMeasuredY: Int,
    currentMeasuredAtMs: Long,
): Pair<Double, Double> {
    val dtMs = (currentMeasuredAtMs - previousMeasuredAtMs).coerceAtLeast(1L).toDouble()
    return (
        (currentMeasuredX - previousMeasuredX).toDouble() / dtMs
        ) to (
        (currentMeasuredY - previousMeasuredY).toDouble() / dtMs
        )
}

internal fun predictInteractiveScreenPosition(
    measuredX: Int,
    measuredY: Int,
    velocityXPxPerMs: Double,
    velocityYPxPerMs: Double,
    elapsedSinceMeasurementMs: Long,
): Pair<Int, Int> {
    val leadMs = elapsedSinceMeasurementMs
        .coerceAtLeast(0L)
        .coerceAtMost(INTERACTION_POINTER_PREDICTION_HORIZON_MS)
        .toDouble()
    val leadX = (velocityXPxPerMs * leadMs)
        .roundToInt()
        .coerceIn(-INTERACTION_POINTER_MAX_LEAD_PX, INTERACTION_POINTER_MAX_LEAD_PX)
    val leadY = (velocityYPxPerMs * leadMs)
        .roundToInt()
        .coerceIn(-INTERACTION_POINTER_MAX_LEAD_PX, INTERACTION_POINTER_MAX_LEAD_PX)
    return (measuredX + leadX) to (measuredY + leadY)
}
