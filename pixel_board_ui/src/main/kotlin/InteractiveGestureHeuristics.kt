package com.pixelboard

import java.awt.Frame
import kotlin.math.hypot

internal const val DOUBLE_TAP_WINDOW_MS = 5_000L
internal const val DOUBLE_TAP_RADIUS_PX = 30.0
internal const val LONG_PRESS_DURATION_MS = 420L
internal const val HOLD_MAX_MOVEMENT_MM = 14.0
internal const val HOLD_STATIONARY_RADIUS_MM = 6.0
internal const val INTERACTION_TAP_CONFIRM_FRAMES = 1
internal const val INTERACTION_HOVER_ANCHOR_RADIUS_MM = 8.0
internal const val INTERACTION_HOVER_ANCHOR_CONFIRM_FRAMES = 1
internal const val INTERACTION_RELEASE_DRIFT_MAX_MM = 10.0
internal const val UI_FRAME_PUBLISH_INTERVAL_MS = 33L
internal const val INTERACTION_POINTER_TICK_MS = 16L

internal enum class TapReleaseAction {
    SINGLE_CLICK,
    SYNTHETIC_DOUBLE_CLICK,
}

internal data class TapReleaseDecision(
    val action: TapReleaseAction,
    val targetScreenX: Int,
    val targetScreenY: Int,
)

internal fun stabilizeInteractiveScreenPosition(
    previousX: Int,
    previousY: Int,
    rawX: Int,
    rawY: Int,
): Pair<Int, Int> =
    rawX to rawY

internal fun isTapFrameConfirmationSatisfied(
    seenFrames: Int,
    hoverAnchorFrames: Int,
): Boolean =
    seenFrames >= INTERACTION_TAP_CONFIRM_FRAMES &&
        hoverAnchorFrames >= INTERACTION_HOVER_ANCHOR_CONFIRM_FRAMES

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

internal fun isWithinDoubleTapRadius(
    firstScreenX: Int,
    firstScreenY: Int,
    secondScreenX: Int,
    secondScreenY: Int,
): Boolean =
    hypot(
        (secondScreenX - firstScreenX).toDouble(),
        (secondScreenY - firstScreenY).toDouble(),
    ) <= DOUBLE_TAP_RADIUS_PX

internal fun shouldTriggerSyntheticDoubleClick(
    previousClickAtMs: Long,
    firstScreenX: Int,
    firstScreenY: Int,
    currentClickAtMs: Long,
    secondScreenX: Int,
    secondScreenY: Int,
): Boolean =
    previousClickAtMs > 0L &&
        (currentClickAtMs - previousClickAtMs) <= DOUBLE_TAP_WINDOW_MS &&
        isWithinDoubleTapRadius(
            firstScreenX = firstScreenX,
            firstScreenY = firstScreenY,
            secondScreenX = secondScreenX,
            secondScreenY = secondScreenY,
        )

internal fun decideTapReleaseAction(
    previousClickAtMs: Long,
    previousClickScreenX: Int,
    previousClickScreenY: Int,
    currentClickAtMs: Long,
    currentClickScreenX: Int,
    currentClickScreenY: Int,
): TapReleaseDecision =
    if (
        shouldTriggerSyntheticDoubleClick(
            previousClickAtMs = previousClickAtMs,
            firstScreenX = previousClickScreenX,
            firstScreenY = previousClickScreenY,
            currentClickAtMs = currentClickAtMs,
            secondScreenX = currentClickScreenX,
            secondScreenY = currentClickScreenY,
        )
    ) {
        TapReleaseDecision(
            action = TapReleaseAction.SYNTHETIC_DOUBLE_CLICK,
            targetScreenX = previousClickScreenX,
            targetScreenY = previousClickScreenY,
        )
    } else {
        TapReleaseDecision(
            action = TapReleaseAction.SINGLE_CLICK,
            targetScreenX = currentClickScreenX,
            targetScreenY = currentClickScreenY,
        )
    }

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
): Pair<Int, Int> =
    measuredX to measuredY
